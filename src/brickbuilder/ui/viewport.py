"""The 3D view: the widget shell. Owns the scene state (model, history, camera, tool, selection,
preview) and dispatches input; the behaviour lives in mixins: placing (the Place tool preview),
selecting (selection, groups, moving, Paint / Erase), turning (the Turn tool) and view_controls
(camera presets). See docs/architecture.md.
"""
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
import OpenGL.GL as gl
import glm
from typing import Optional
from brickbuilder.core.renderer import Renderer
from brickbuilder.core.camera import Camera
from brickbuilder.core.connections import groups
from brickbuilder.core.history import History
from brickbuilder.core.model import Model, Sub, default_anchor_index
from brickbuilder.core.parts import PartDef, load_builtin_library
from brickbuilder.core.profile import load_builtin_profile
from brickbuilder.core import picking
from brickbuilder.core.tools import Tool
from brickbuilder.ui.placing import PlacingMixin
from brickbuilder.ui.selecting import SelectionMixin
from brickbuilder.ui.turning import TurningMixin
from brickbuilder.ui.view_controls import ViewControlsMixin

DEFAULT_PART = "brick_1x1"
DEFAULT_COLOR = "red"

class Viewport(PlacingMixin, SelectionMixin, TurningMixin, ViewControlsMixin, QOpenGLWidget):
    # Emitted after anything that may have changed the model (edits, undo/redo, load, new)
    edited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = Renderer()
        self.camera = Camera()
        self.profile = load_builtin_profile()
        self.library = load_builtin_library(self.profile)
        self.model = Model(self.profile, self.library)
        # All edits go through the history so they can be undone
        self.history = History(self.model)

        self.current_tool = Tool.PLACE
        self.current_part: PartDef = self.library[f"{self.profile.id}:{DEFAULT_PART}"]
        self.current_turns = 0
        self.current_anchor = default_anchor_index(self.current_part) # index into anchor_cells(current_part)
        self.current_color = DEFAULT_COLOR if DEFAULT_COLOR in self.profile.palette else next(iter(self.profile.palette))

        # Where the current part would go: sub-grid position of its origin, or None.
        # ghost_valid is False when it would overlap another part (drawn red, can't place).
        self.ghost_pos: Optional[Sub] = None
        self.ghost_valid = False
        self.ghost_frame = 0
        self.hover_pos = None # last mouse position over the viewport, for refreshing the ghost
        # Half-offset placement: snap to half-cells in XY, plus a keyboard nudge of the preview (in
        # sub-cells) that's kept until the cursor moves to a different target
        self.half_snap = False
        self.ghost_nudge = (0, 0)
        self._nudge_base = None
        # View > Highlight Unconnected Parts (outside the largest connected group) / Colliding Parts
        self.highlight_unconnected = False
        self.highlight_collisions = False

        # Selected part ids (Select tool), and the box being dragged: (x0, y0, x1, y1) widget px
        self.selection: set = set()
        self.select_rect = None
        self._press = None  # (position, modifiers, hit part, hit point, normal) of a left press, Select tool
        # A drag of the selection (pick up, put down): see _start_drag
        self.dragging: Optional[dict] = None
        # The group double-click drilled into: clicks inside it select one level below it.
        # None = top level (clicks select whole outermost groups)
        self.select_context: Optional[int] = None
        self.hovered: set = set()  # what a click would select, outlined while hovering
        # Turn tool: the turn being dragged (moving ids, pivot, angles, transform, valid)
        self.turning: Optional[dict] = None
        self.rotation_snap = 7.5  # degrees; an editor setting (TODO(preferences))
        self.notice = ""  # a short message for the status bar (why a turn can't happen, ...)
        # Place tool: the preview turned off its grid by this many degrees (0 <= angle < 90) about
        # the centre of its anchor cell; placing it then gives the part a grid of its own
        self.ghost_angle = 0.0
        self._ghost_pivot = None  # that centre, in the ghost's grid space
        # A grid the preview is on that isn't a frame yet (built on a side stud): its transform in
        # ghost_frame's space, or None. Placing creates the frame.
        self._ghost_grid: Optional[glm.mat4] = None
        # Working frame: whose grid empty space and the ground use when placing (F toggles it)
        self.working_frame = 0

        # Mouse moves without a button pressed too: the ghost and hover outlines follow the cursor
        self.setMouseTracking(True)
        self.last_mouse_pos = None

    def initializeGL(self):
        self.renderer.initialize()

    def resizeGL(self, w, h):
        self.camera.set_aspect_ratio(w / max(h, 1))  # the widget can be squeezed to 0 px high
        gl.glViewport(0, 0, w, h)

    def paintGL(self):
        pixel_ratio = self.devicePixelRatio()
        ghost = None
        if self.ghost_pos is not None:
            geo = self.model.placement_geometry(self.current_part, self.ghost_pos, self.current_turns,
                                                self.ghost_matrix())
            # Show where its studs fit, and what's in the way when it's red
            blocking = () if self.ghost_valid else self.model.blocking_studs(self.model.shape(geo))
            ghost = (geo["solids"], geo["studs"], self.ghost_valid, geo["stud_axes"], [(a, b, n) for (a, b), n in zip(geo["antistuds"], geo["antistud_axes"])], blocking,
                     geo["hollows"])
        rect = None
        if self.select_rect:
            rect = tuple(v * pixel_ratio for v in self.select_rect)
        moving = self._moving_preview()
        selected = []
        for pid in self.selection:
            if pid not in self.model.parts:
                continue
            edges = self.model.parts[pid].edges
            if moving and pid in moving[0]:  # outline it where it's being moved to
                m = moving[1]
                edges = [(glm.vec3(m * glm.vec4(a, 1.0)), glm.vec3(m * glm.vec4(b, 1.0))) for a, b in edges]
            selected.append(edges)
        self.renderer.render(self.camera, self.model, self.profile, ghost,
                             int(self.width() * pixel_ratio), int(self.height() * pixel_ratio),
                             selected,
                             select_rect=rect,
                             hovered_edges=[self.model.parts[pid].edges for pid in self.hovered - self.selection
                                            if pid in self.model.parts],
                             highlighted=[self.model.parts[pid].edges for pid in self.unconnected_parts()]
                             if self.highlight_unconnected else (),
                             collided=[self.model.parts[pid].edges for pid in self.model.collisions()]
                             if self.highlight_collisions else (),
                             turning=moving,
                             pivot=(self.turning["pivot"], self.turning["axis"])
                             if self.turning and self.turning["pivot"] is not None else None,
                             grid_matrix=self.model.frame_matrix(self.working_frame) if self.working_frame else None)

    def set_tool(self, tool: Tool):
        self.current_tool = tool
        self.ghost_pos = None
        self._cancel_moves()
        self.notice = ""
        if tool not in (Tool.SELECT, Tool.TURN):
            self._clear_selection_state()
        self.update()
        self.edited.emit()

    def _cancel_moves(self):
        """Drop a turn or drag in progress (e.g. the parts it refers to may be gone)."""
        if self.turning or self.dragging:
            self.turning = self.dragging = None
            self._press = None
            self.notice = ""

    def _clear_selection_state(self):
        self.selection = set()
        self.select_context = None
        self.hovered = set()

    def _forget_document(self):
        """After New or Open: drop everything that refers to the old contents."""
        self.history.reset()
        self.ghost_pos = None
        self._cancel_moves()
        self._clear_selection_state()
        self.working_frame = 0
        self.notice = ""
        self.update()
        self.edited.emit()

    def reset_scene(self):
        self.model.clear()
        self.camera.reset()
        self._forget_document()

    def model_replaced(self):
        # After loading a file
        self._forget_document()

    def undo(self):
        if self.history.undo():
            self._after_history_step()

    def redo(self):
        if self.history.redo():
            self._after_history_step()

    def _after_history_step(self):
        self._cancel_moves()
        if self.working_frame not in self.model.frames:
            self.working_frame = 0
        self.selection &= set(self.model.parts)
        self.hovered &= set(self.model.parts)
        if self.select_context not in self.model.groups:
            self.select_context = None
        self.refresh_ghost()
        self.edited.emit()

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()

        # Clicking an axis of the corner gizmo looks along it (from that side; again: the other side)
        if event.button() == Qt.MouseButton.LeftButton:
            axis = self._gizmo_axis_at(event.position())
            if axis is not None:
                near, far = {"x": ("right", "left"), "y": ("back", "front"), "z": ("top", "bottom")}[axis]
                self.set_view(far if self.camera.is_view(near) else near)
                self.edited.emit()
                return

        if event.button() == Qt.MouseButton.LeftButton and self.current_tool == Tool.SELECT:
            # Click, box or drag: decided on release (or once the mouse moves far enough)
            ray = picking.get_mouse_ray(event.position().x(), event.position().y(), self.width(), self.height(),
                                        self.camera)
            hit, normal, point = picking.intersect_model(ray, self.model)
            self._press = (event.position(), event.modifiers(), hit, point, normal)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.current_tool == Tool.TURN:
            self._start_turn(event)
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle_left_click(event)
            self.update()
            self.edited.emit()

    def _handle_left_click(self, event: QMouseEvent):
        ray = picking.get_mouse_ray(event.position().x(), event.position().y(), self.width(), self.height(), self.camera)

        if self.current_tool == Tool.PLACE:
            self._handle_place_tool(event, ray)
        elif self.current_tool == Tool.PAINT:
            self._handle_paint_tool(ray)
        elif self.current_tool == Tool.ERASE:
            self._handle_erase_tool(ray)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.turning is not None:
            self._finish_turn()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.dragging is not None:
            self._press = None
            self._finish_drag()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        start, modifiers = self._press[:2]
        add = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        single = bool(modifiers & Qt.KeyboardModifier.AltModifier)  # Alt: one part, ignoring groups
        self._press = None
        if self.select_rect:
            x0, y0, x1, y1 = self.select_rect
            found = set()
            for pid in picking.parts_in_rect(self.model, self.camera, x0, y0, x1, y1, self.width(), self.height()):
                found |= self._unit(pid, single)
            self.selection = (self.selection | found) if add else found
            self.select_rect = None
        else:
            hit = self._hit(start)
            unit = self._unit(hit.id, single) if hit else set()
            if add:
                self.selection = (self.selection - unit) if unit and unit <= self.selection else (self.selection | unit)
            else:
                self.selection = unit
                if not hit:
                    self.select_context = None
        self.update()
        self.edited.emit()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # Double-click in the Select tool drills into the group under the cursor: selects the
        # next level down (a child group, or the part itself)
        if event.button() == Qt.MouseButton.LeftButton and self.current_tool == Tool.SELECT:
            self._press = None
            hit = self._hit(event.position())
            if hit and not event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._unit(hit.id)  # drops a context the part isn't in
                _, group = self.model.selection_unit(hit.id, self.select_context)
                if group is not None:
                    self.select_context = group
                    self.selection = self._unit(hit.id)
                    self.hovered = set(self.selection)
                    self.update()
                    self.edited.emit()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos = event.position()
        self.hover_pos = current_pos

        # Dragging in the Select tool, once it's more than a few pixels: from a selected part it
        # moves the selection, from anywhere else it draws a selection box
        if self.dragging is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._update_drag(current_pos)
        elif self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            start, modifiers, hit, point, normal = self._press
            if self.select_rect or (current_pos - start).manhattanLength() > 4:
                plain = not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
                if not self.select_rect and plain and hit is not None and hit.id in self.selection:
                    self._start_drag(hit, point, normal)
                    self._update_drag(current_pos)
                else:
                    self.select_rect = (start.x(), start.y(), current_pos.x(), current_pos.y())

        # Tool-specific hover logic
        if self.current_tool == Tool.PLACE:
             self.update_ghost(current_pos.x(), current_pos.y())
        else:
            self.ghost_pos = None
        if self.current_tool in (Tool.SELECT, Tool.TURN) and not event.buttons():
            self._update_hover(current_pos, event.modifiers())
        if self.turning is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._drag_turn(event)

        if self.last_mouse_pos is not None:
             # Navigation stays same
            delta = current_pos - self.last_mouse_pos
            self.last_mouse_pos = current_pos

            if event.buttons() & Qt.MouseButton.MiddleButton:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Pan
                    sensitivity = 0.005
                    self.camera.pan(delta.x() * sensitivity, -delta.y() * sensitivity)
                else:
                    # Rotate
                    sensitivity = 0.01
                    self.camera.orbit(-delta.x() * sensitivity, -delta.y() * sensitivity)

        self.update()

    def unconnected_parts(self):
        """Ids of parts outside the largest connected group (empty when everything is one group)."""
        found = groups(self.model.connections())
        return set().union(*found[1:]) if len(found) > 1 else set()

    def set_highlight_unconnected(self, on: bool):
        self.highlight_unconnected = on
        self.update()

    def set_highlight_collisions(self, on: bool):
        self.highlight_collisions = on
        self.update()

    def leaveEvent(self, event):
        self.hover_pos = None
        self.ghost_pos = None
        self.hovered = set()
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self.camera.zoom(delta * 0.005)
        self.update()
