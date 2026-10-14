from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
import OpenGL.GL as gl
import glm
import math
from typing import Optional, Tuple
from brickbuilder.core.renderer import Renderer
from brickbuilder.core.camera import Camera
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
        self.hover_pos = None # last mouse position over the viewport, for refreshing the ghost
        # Half-offset placement: snap to half-cells in XY, plus a keyboard nudge (in sub-cells)
        # that's kept until the cursor moves to a different target
        self.half_snap = False
        self.nudge = (0, 0)
        self._nudge_base = None

        self.selected_part_id: Optional[int] = None

        # Enable mouse tracking for hover effects if needed later
        self.setMouseTracking(True)

        # Timer for continuous update if needed (or just update on events)
        # For smooth camera, might need timer or requestUpdate

        self.last_mouse_pos = None

    def initializeGL(self):
        self.renderer.initialize()

    def resizeGL(self, w, h):
        self.camera.set_aspect_ratio(w / h)
        gl.glViewport(0, 0, w, h)

    def paintGL(self):
        pixel_ratio = self.devicePixelRatio()
        ghost = None
        if self.ghost_pos is not None:
            ghost = (self.model.placement_solids(self.current_part, self.ghost_pos, self.current_turns),
                     self.model.placement_studs(self.current_part, self.ghost_pos, self.current_turns),
                     self.ghost_valid)
        selected = self.model.parts.get(self.selected_part_id) if self.selected_part_id is not None else None
        self.renderer.render(self.camera, self.model, self.profile, ghost,
                             int(self.width() * pixel_ratio), int(self.height() * pixel_ratio),
                             selected.solids if selected else None)

    def set_tool(self, tool: Tool):
        self.current_tool = tool
        self.ghost_pos = None
        self.selected_part_id = None
        self.update()

    def reset_scene(self):
        self.model.clear()
        self.history.reset()
        self.camera.reset()
        self.ghost_pos = None
        self.selected_part_id = None
        self.update()
        self.edited.emit()

    def model_replaced(self):
        # After loading a file: drop references into the old contents
        self.history.reset()
        self.ghost_pos = None
        self.selected_part_id = None
        self.update()
        self.edited.emit()

    def undo(self):
        if self.history.undo():
            self._after_history_step()

    def redo(self):
        if self.history.redo():
            self._after_history_step()

    def _after_history_step(self):
        if self.selected_part_id not in self.model.parts:
            self.selected_part_id = None
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
        # If in Paint mode and something selected, paint it?
        if self.current_tool == Tool.SELECT and self.selected_part_id is not None:
             pass

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle_left_click(event)
            self.update()
            self.edited.emit()

    def _handle_left_click(self, event: QMouseEvent):
        ray = picking.get_mouse_ray(event.position().x(), event.position().y(), self.width(), self.height(), self.camera)

        if self.current_tool == Tool.PLACE:
            self._handle_place_tool(event, ray)
        elif self.current_tool == Tool.SELECT:
            self._handle_select_tool(ray)
        elif self.current_tool == Tool.PAINT:
            self._handle_paint_tool(ray)
        elif self.current_tool == Tool.ERASE:
            self._handle_erase_tool(ray)

    def _handle_place_tool(self, event: QMouseEvent, ray):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Quick erase override in Place mode
            self._handle_erase_tool(ray)
        elif self.ghost_pos is not None and self.ghost_valid:
            self.history.add_part(self.current_part, self.ghost_pos, self.current_turns, self.current_color)
        # Refresh ghost immediately
        self.update_ghost(event.position().x(), event.position().y())

    def _handle_select_tool(self, ray):
        hit, _, _ = picking.intersect_model(ray, self.model)
        self.selected_part_id = hit.id if hit else None

    def _handle_paint_tool(self, ray):
        hit, _, _ = picking.intersect_model(ray, self.model)
        if hit:
            self.history.set_color(hit.id, self.current_color)

    def _handle_erase_tool(self, ray):
        hit, _, _ = picking.intersect_model(ray, self.model)
        if hit:
            self.history.remove_part(hit.id)
            if hit.id == self.selected_part_id:
                self.selected_part_id = None

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos = event.position()
        self.hover_pos = current_pos

        # Tool-specific hover logic
        if self.current_tool == Tool.PLACE:
             self.update_ghost(current_pos.x(), current_pos.y())
        else:
            self.ghost_pos = None

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
        if hit:
            # Snap to the cell against the hit face
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
            self.ghost_valid = self.model.can_place(self.current_part, self.ghost_pos, self.current_turns)

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
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self.camera.zoom(delta * 0.005)
        self.update()
