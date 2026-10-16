from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
import OpenGL.GL as gl
import glm
import math
from typing import Optional, Tuple
from brickbuilder.core.renderer import Renderer
from brickbuilder.core.camera import Camera
from brickbuilder.core.connections import groups
from brickbuilder.core.history import History
from brickbuilder.core.model import Model, Sub, anchor_cells, default_anchor_index, origin_for_anchor, placement_target
from brickbuilder.core.parts import PartDef, load_builtin_library
from brickbuilder.core.profile import load_builtin_profile
from brickbuilder.core import picking
from brickbuilder.core.tools import Tool

DEFAULT_PART = "brick_1x1"
DEFAULT_COLOR = "red"

class Viewport(QOpenGLWidget):
    # Emitted after anything that may have changed the model (edits, undo/redo, load, new)
    edited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = Renderer()
        self.camera = Camera()
        self.profile = load_builtin_profile()
        self.library = load_builtin_library(self.profile.id)
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
        # Half-offset placement: snap to half-cells in XY, plus a keyboard nudge (in sub-cells)
        # that's kept until the cursor moves to a different target
        self.half_snap = False
        # Mark parts outside the largest connected group (View > Highlight Unconnected Parts)
        self.highlight_unconnected = False
        self.highlight_collisions = False
        self.nudge = (0, 0)
        self._nudge_base = None

        # Selected part ids (Select tool), and the box being dragged: (x0, y0, x1, y1) widget px
        self.selection: set = set()
        self.select_rect = None
        self._press = None  # (position, modifiers) of a left press in the Select tool
        # The group double-click drilled into: clicks inside it select one level below it.
        # None = top level (clicks select whole outermost groups)
        self.select_context: Optional[int] = None
        self.hovered: set = set()  # what a click would select, outlined while hovering

        # Enable mouse tracking for hover effects if needed later
        self.setMouseTracking(True)

        # Timer for continuous update if needed (or just update on events)
        # For smooth camera, might need timer or requestUpdate

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
            ghost = (self.model.placement_solids(self.current_part, self.ghost_pos, self.current_turns, self.ghost_frame),
                     self.model.placement_studs(self.current_part, self.ghost_pos, self.current_turns, self.ghost_frame),
                     self.ghost_valid)
        rect = None
        if self.select_rect:
            rect = tuple(v * pixel_ratio for v in self.select_rect)
        self.renderer.render(self.camera, self.model, self.profile, ghost,
                             int(self.width() * pixel_ratio), int(self.height() * pixel_ratio),
                             [self.model.parts[pid].edges for pid in self.selection if pid in self.model.parts],
                             select_rect=rect,
                             hovered_edges=[self.model.parts[pid].edges for pid in self.hovered - self.selection
                                            if pid in self.model.parts],
                             highlighted=[self.model.parts[pid].edges for pid in self.unconnected_parts()]
                             if self.highlight_unconnected else (),
                             collided=[self.model.parts[pid].edges for pid in self.model.collisions()]
                             if self.highlight_collisions else ())

    def set_tool(self, tool: Tool):
        self.current_tool = tool
        self.ghost_pos = None
        if tool != Tool.SELECT:
            self.selection = set()
            self.select_context = None
            self.hovered = set()
        self.update()
        self.edited.emit()

    def reset_scene(self):
        self.model.clear()
        self.history.reset()
        self.camera.reset()
        self.ghost_pos = None
        self.selection = set()
        self.select_context = None
        self.hovered = set()
        self.update()
        self.edited.emit()

    def model_replaced(self):
        # After loading a file: drop references into the old contents
        self.history.reset()
        self.ghost_pos = None
        self.selection = set()
        self.select_context = None
        self.hovered = set()
        self.update()
        self.edited.emit()

    def undo(self):
        if self.history.undo():
            self._after_history_step()

    def redo(self):
        if self.history.redo():
            self._after_history_step()

    def _after_history_step(self):
        self.selection &= set(self.model.parts)
        self.hovered &= set(self.model.parts)
        if self.select_context not in self.model.groups:
            self.select_context = None
        self.refresh_ghost()
        self.edited.emit()

    def set_current_part(self, part: PartDef):
        self.current_part = part
        self.current_anchor = default_anchor_index(part)
        self.refresh_ghost()

    def rotate_current_part(self, quarter_turns: int):
        # The anchor cell stays on the cell under the cursor, so the part turns around it
        self.current_turns = (self.current_turns + quarter_turns) % 4
        self.refresh_ghost()

    def cycle_anchor(self, step: int):
        # Choose which cell of the part sits under the cursor (e.g. end / middle / end of a 1x3)
        self.current_anchor = (self.current_anchor + step) % len(anchor_cells(self.current_part))
        self.refresh_ghost()

    def refresh_ghost(self):
        if self.current_tool == Tool.PLACE and self.hover_pos is not None:
            self.update_ghost(self.hover_pos.x(), self.hover_pos.y())
        self.update()

    def set_current_color(self, color: str):
        self.current_color = color
        # Picking a colour in the Select tool recolours the selection (one undo step)
        if self.current_tool == Tool.SELECT and self.selection:
            self.history.set_colors(self.selection, color)
            self.update()
            self.edited.emit()

    # --- selection ---------------------------------------------------------------------

    def select_all(self):
        self.selection = set(self.model.parts)
        self.update()
        self.edited.emit()

    def clear_selection(self):
        self.selection = set()
        self.select_context = None
        self.update()
        self.edited.emit()

    def select_connected(self):
        """Grow the selection to the whole connected subassemblies it touches."""
        for group in groups(self.model.connections()):
            if group & self.selection:
                self.selection |= group
        self.update()
        self.edited.emit()

    def _unit(self, part_id: int, single: bool = False) -> set:
        """What clicking a part selects at the current drill level (just the part if single)."""
        if single:
            return {part_id}
        if self.select_context not in self.model.group_chain(part_id):
            self.select_context = None  # clicked outside the group we were in
        return self.model.selection_unit(part_id, self.select_context)[0]

    def selected_group(self) -> Optional[int]:
        """The group the selection is exactly, if it is one."""
        groups, loose = self.model.top_units(self.selection)
        if len(groups) == 1 and not loose:
            return next(iter(groups))
        return None

    def select_group(self, group_id: int):
        self.selection = self.model.group_parts(group_id)
        self.select_context = self.model.groups[group_id].parent
        self.update()
        self.edited.emit()

    def group_selection(self) -> Optional[int]:
        """Ctrl+G: put the selection into a new group (one undo step)."""
        if not self.selection:
            return None
        n = len(self.model.groups) + 1
        names = {g.name for g in self.model.groups.values()}
        while f"Group {n}" in names:
            n += 1
        gid = self.history.group(self.selection, f"Group {n}")
        self.select_context = self.model.groups[gid].parent
        self.update()
        self.edited.emit()
        return gid

    def ungroup_selection(self):
        """Ctrl+Shift+G: dissolve the whole groups in the selection, one level."""
        groups, _ = self.model.top_units(self.selection)
        if not groups:
            return
        if self.select_context in groups:
            self.select_context = self.model.groups[self.select_context].parent
        self.history.ungroup(groups)
        self.update()
        self.edited.emit()

    def rename_group(self, group_id: int, name: str):
        if group_id in self.model.groups and name:
            self.history.rename_group(group_id, name)
            self.edited.emit()

    def delete_selection(self):
        if self.selection:
            self.history.remove_parts(self.selection)
            self.selection = set()
            self.update()
            self.edited.emit()

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()

        if event.button() == Qt.MouseButton.LeftButton and self.current_tool == Tool.SELECT:
            # Click or box: decided on release (or once the mouse moves far enough)
            self._press = (event.position(), event.modifiers())
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

    def _handle_place_tool(self, event: QMouseEvent, ray):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Quick erase override in Place mode
            self._handle_erase_tool(ray)
        elif self.ghost_pos is not None and self.ghost_valid:
            self.history.add_part(self.current_part, self.ghost_pos, self.current_turns, self.current_color,
                                  self.ghost_frame)
        # Refresh ghost immediately
        self.update_ghost(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        start, modifiers = self._press
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

    def _hit(self, pos):
        ray = picking.get_mouse_ray(pos.x(), pos.y(), self.width(), self.height(), self.camera)
        return picking.intersect_model(ray, self.model)[0]

    def _update_hover(self, pos, modifiers):
        hit = self._hit(pos) if pos is not None else None
        self.hovered = self._unit(hit.id, bool(modifiers & Qt.KeyboardModifier.AltModifier)) if hit else set()

    def _handle_paint_tool(self, ray):
        hit, _, _ = picking.intersect_model(ray, self.model)
        if hit:
            self.history.set_color(hit.id, self.current_color)

    def _handle_erase_tool(self, ray):
        hit, _, _ = picking.intersect_model(ray, self.model)
        if hit:
            self.history.remove_part(hit.id)
            self.selection.discard(hit.id)

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos = event.position()
        self.hover_pos = current_pos

        # Dragging in the Select tool draws a selection box once it's more than a few pixels
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            start = self._press[0]
            if self.select_rect or (current_pos - start).manhattanLength() > 4:
                self.select_rect = (start.x(), start.y(), current_pos.x(), current_pos.y())

        # Tool-specific hover logic
        if self.current_tool == Tool.PLACE:
             self.update_ghost(current_pos.x(), current_pos.y())
        else:
            self.ghost_pos = None
        if self.current_tool == Tool.SELECT and not event.buttons():
            self._update_hover(current_pos, event.modifiers())

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

    def update_ghost(self, mouse_x, mouse_y):
        ray = picking.get_mouse_ray(mouse_x, mouse_y, self.width(), self.height(), self.camera)

        # Check model intersection first
        hit, normal, point = picking.intersect_model(ray, self.model)

        target = None
        frame = 0
        if hit:
            # Snap to the cell against the hit face. Parts placed against a part go on that
            # part's grid (its frame), so building on a turned part follows its turn.
            frame = hit.frame
            point, normal = self.model.to_frame(frame, point, normal)
            target = placement_target(self.profile, point, normal, self.half_snap)
        elif ray.direction.z < -1e-6:
            # Check ground plane (Z=0) intersection ONLY if looking down
            # Normal (0,0,1), Point (0,0,0)
            t = picking.intersect_plane(ray, glm.vec3(0, 0, 1), glm.vec3(0, 0, 0))
            if t:
                # Layer 0 sits on the Z=0 grid
                target = placement_target(self.profile, ray.origin + ray.direction * t,
                                          glm.vec3(0, 0, 1), self.half_snap)

        # A keyboard nudge applies to the spot it was made at; moving elsewhere drops it
        if target != self._nudge_base:
            self._nudge_base = target
            self.nudge = (0, 0)

        # The target cell is where the part's anchor cell goes
        self.ghost_pos = None
        self.ghost_valid = False
        if target is not None:
            target = (target[0] + self.nudge[0], target[1] + self.nudge[1], target[2])
            anchor = anchor_cells(self.current_part)[self.current_anchor]
            self.ghost_pos = origin_for_anchor(self.profile, anchor, self.current_turns, target)
            self.ghost_frame = frame
            self.ghost_valid = self.model.can_place(self.current_part, self.ghost_pos, self.current_turns, frame)

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

    def set_half_snap(self, on: bool):
        self.half_snap = on
        self.refresh_ghost()

    def nudge_ghost(self, screen_dx: int, screen_dy: int):
        """Move the preview one sub-cell (half a cell) along the world axis that best matches the
        screen direction (right = +screen_dx, up = +screen_dy) from the current view."""
        # Screen-right and screen-up (away from the viewer) projected onto the ground plane
        right = glm.vec2(-math.sin(self.camera.yaw), math.cos(self.camera.yaw))
        up = glm.vec2(-math.cos(self.camera.yaw), -math.sin(self.camera.yaw))
        # Right gets the closer world axis (X on a tie), up gets the other one
        if abs(right.x) >= abs(right.y):
            right_axis, up_axis = (int(math.copysign(1, right.x)), 0), (0, int(math.copysign(1, up.y)))
        else:
            right_axis, up_axis = (0, int(math.copysign(1, right.y))), (int(math.copysign(1, up.x)), 0)
        dx = right_axis[0] * screen_dx + up_axis[0] * screen_dy
        dy = right_axis[1] * screen_dx + up_axis[1] * screen_dy
        self.nudge = (self.nudge[0] + dx, self.nudge[1] + dy)
        self.refresh_ghost()

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
