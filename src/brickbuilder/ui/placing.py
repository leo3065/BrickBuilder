"""The placement preview (Place tool): where a part would go and how it's turned.

Targets: the face under the cursor (on that part's frame), a side stud's grid, a joint (straight
on, Space: rolled 180°), else the working grid's ground. The anchor cell goes on the target; the
preview can be nudged, turned 90° or off the grid. See docs/architecture.md "Features".
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
import glm
import math
from brickbuilder.core.model import (anchor_cells, decompose, default_anchor_index, origin_for_anchor, placement_target, turn_about_z)
from brickbuilder.core.parts import PartDef
from brickbuilder.core import picking
from brickbuilder.core.tools import Tool


class PlacingMixin:
    """Mixed into ui.viewport.Viewport: uses its state (model, history, camera, ...)."""

    def set_current_part(self, part: PartDef):
        self.current_part = part
        self.current_anchor = default_anchor_index(part)
        self.refresh_ghost()

    def rotate_current_part(self, quarter_turns: int):
        if self.dragging:  # Space while dragging the selection turns it (on a joint: rolls it 180°)
            self.dragging["turns"] = (self.dragging["turns"] + quarter_turns) % 4
            self._update_drag(self.dragging.get("pos"))
            return
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

    def turn_ghost(self, degrees: float):
        """Turn the placement preview off its grid. Whole quarter turns go into current_turns,
        which turns it about the same cell (the anchor stays put)."""
        self.current_turns, self.ghost_angle = self._add_angle(self.current_turns, self.ghost_angle, degrees)
        self.refresh_ghost()
        self.edited.emit()

    def ghost_local_turn(self) -> glm.mat4:
        """The preview's turn off its frame's grid, in that grid's space."""
        if not self.ghost_angle or self._ghost_pivot is None:
            return glm.mat4(1.0)
        return turn_about_z(self._ghost_pivot, self.ghost_angle)

    def ghost_matrix(self) -> glm.mat4:
        """Grid space of the preview -> world."""
        grid = self._ghost_grid if self._ghost_grid is not None else glm.mat4(1.0)
        return self.model.frame_matrix(self.ghost_frame) * grid * self.ghost_local_turn()

    def toggle_working_frame(self):
        """F: use the grid of the part under the cursor for empty space and the ground (again
        over empty space or the same grid: back to the root grid)."""
        hit = None
        if self.hover_pos is not None:
            hit = self._hit(self.hover_pos)
        if hit is not None and hit.frame != self.working_frame:
            self.working_frame = hit.frame
        else:
            self.working_frame = 0
        self.notice = f"working grid: frame {self.working_frame}" if self.working_frame else "working grid: root"
        self.refresh_ghost()
        self.update()
        self.edited.emit()

    def _target_under(self, x, y, ignore=(), side_studs=True):
        """Where something placed under the cursor goes: (frame, target sub-cell, new grid). Against
        the face under the cursor, on that part's grid; on a face with a side stud, on the stud's
        grid (an existing frame that lines up with it, or a new grid: its transform in `frame`'s
        space, else None); else on the working grid's ground, when looking down at it. The target is
        None when there's nowhere to put it."""
        ray = picking.get_mouse_ray(x, y, self.width(), self.height(), self.camera)
        hit, normal, point = picking.intersect_model(ray, self.model, ignore)
        if hit:
            if side_studs:
                on_stud = self._side_stud_target(hit, point, normal)
                if on_stud is not None:
                    return on_stud
            point, normal = self.model.to_frame(hit.frame, point, normal)
            return hit.frame, placement_target(self.profile, point, normal, self.half_snap), None
        frame = self.working_frame
        m = self.model.frame_matrix(frame)
        up = glm.normalize(glm.vec3(m * glm.vec4(0, 0, 1, 0)))
        if glm.dot(ray.direction, up) < -1e-6:
            t = picking.intersect_plane(ray, up, glm.vec3(m * glm.vec4(0, 0, 0, 1)))
            if t:
                point, _ = self.model.to_frame(frame, ray.origin + ray.direction * t, up)
                return frame, placement_target(self.profile, point, glm.vec3(0, 0, 1), self.half_snap), None
        return frame, None, None

    def _side_stud_target(self, part, point, normal):
        """If the face under the cursor has a side stud (one not along the part's own up), the
        target on that stud's grid; else None."""
        up = glm.vec3(self.model.frame_matrix(part.frame) * glm.vec4(0, 0, 1, 0))
        best = None
        for i, (stud, axis) in enumerate(zip(part.studs, part.stud_axes)):
            if abs(glm.dot(axis, up)) > 0.999 or glm.dot(axis, normal) < 0.999:
                continue  # a top (or bottom) stud, or not on this face
            if abs(glm.dot(point - stud, axis)) > 0.05:
                continue
            d = glm.distance(point, stud)
            if best is None or d < best[0]:
                best = (d, i)
        if best is None:
            return None
        grid = self.model.side_stud_grid(part.id, best[1])
        found = self.model.find_grid(grid)
        if found is not None:
            return found[0], found[1], None
        return part.frame, (0, 0, 0), glm.inverse(self.model.frame_matrix(part.frame)) * grid

    def _cell_centre(self, sub) -> glm.vec3:
        """Centre of the bottom of the cell whose min-corner sub-cell is `sub` (grid space)."""
        nx, ny, _ = self.profile.subdiv
        return self.profile.sub_to_world((sub[0] + nx / 2, sub[1] + ny / 2, sub[2]))

    def _handle_place_tool(self, event: QMouseEvent, ray):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Quick erase override in Place mode
            self._handle_erase_tool(ray)
        elif self.ghost_pos is not None and self.ghost_valid:
            if self.ghost_angle or self._ghost_grid is not None:
                grid = self._ghost_grid if self._ghost_grid is not None else glm.mat4(1.0)
                origin, rotation = decompose(grid * self.ghost_local_turn())
                self.history.add_part_in_new_frame(self.current_part, self.ghost_pos, self.current_turns,
                                                   self.current_color, self.ghost_frame, origin, rotation)
            else:
                self.history.add_part(self.current_part, self.ghost_pos, self.current_turns, self.current_color,
                                      self.ghost_frame)
        # Refresh ghost immediately
        self.update_ghost(event.position().x(), event.position().y())

    def _joint_target(self, mouse_x, mouse_y, part=None, turns=None, ignore=(), flip=False):
        """If the cursor is on a joint that `part` (default: the current part, at `turns`) has the
        mate for (a cup for its ball, a ball for its cup): (frame, the part's grid in that frame's
        space, the grid in world space) putting it on the joint straight, its top the same way as the
        other part's (`flip`: rolled 180°, tops swapped: the joint is at mid-height, so it lines up
        too); else None. Parts in `ignore` are looked through."""
        part = part or self.current_part
        turns = self.current_turns if turns is None else turns
        mates = range(len(part.joints))
        if not mates:
            return None
        ray = picking.get_mouse_ray(mouse_x, mouse_y, self.width(), self.height(), self.camera)
        hit, _, point = picking.intersect_model(ray, self.model, ignore)
        if hit is None or not hit.joints:
            return None
        best = None
        for target in hit.joints:
            for i in mates:
                if {part.joints[i].kind, target[0]} != {"ball", "cup"}:
                    continue
                d = glm.distance(point, target[1])
                if d < 6.0 and (best is None or d < best[0]):  # on or near the ball / cup
                    best = (d, i, target)
        if best is None:
            return None
        up = glm.vec3(self.model.frame_matrix(hit.frame) * glm.vec4(0, 0, 1, 0))
        grid = self.model.joint_grid(part, turns, best[1], best[2], -up if flip else up)
        return hit.frame, glm.inverse(self.model.frame_matrix(hit.frame)) * grid, grid

    def update_ghost(self, mouse_x, mouse_y):
        # On a joint, Space (an odd number of quarter turns) puts the part on rolled 180°
        on_joint = self._joint_target(mouse_x, mouse_y, flip=self.current_turns % 2 == 1)
        if on_joint is not None:
            # Straight onto the joint: the part's own position is fixed by the joint
            self.ghost_frame, self._ghost_grid, _ = on_joint
            self.ghost_pos = (0, 0, 0)
            self._ghost_pivot = None  # no fine turn on a joint (posing comes later)
            problem = self.model.turned_placement_problem(self.current_part, self.ghost_pos, self.current_turns,
                                                          self.ghost_matrix())
            self.ghost_valid = problem is None
            self.notice = f"can't place: {problem}" if problem else (
                "on the joint, rolled 180° (Space)" if self.current_turns % 2 else "on the joint (Space: roll 180°)")
            return
        if self.notice.startswith("on the joint"):
            self.notice = ""
        # Parts placed against a part go on that part's grid (its frame), so building on a turned
        # part follows its turn; in empty space, the working grid's ground
        frame, target, grid = self._target_under(mouse_x, mouse_y)

        # A keyboard nudge applies to the spot it was made at; moving elsewhere drops it
        if target != self._nudge_base:
            self._nudge_base = target
            self.ghost_nudge = (0, 0)

        # The target cell is where the part's anchor cell goes
        self.ghost_pos = None
        self.ghost_valid = False
        if self.notice.startswith("can't place"):
            self.notice = ""
        if target is not None:
            target = (target[0] + self.ghost_nudge[0], target[1] + self.ghost_nudge[1], target[2])
            anchor = anchor_cells(self.current_part)[self.current_anchor]
            self.ghost_pos = origin_for_anchor(self.profile, anchor, self.current_turns, target)
            self.ghost_frame = frame
            self._ghost_grid = grid
            self._ghost_pivot = self._cell_centre(target)
            if self.ghost_angle or grid is not None:  # on a grid of its own: no frame to check against
                problem = self.model.turned_placement_problem(self.current_part, self.ghost_pos,
                                                              self.current_turns, self.ghost_matrix())
                self.ghost_valid = problem is None
                if problem:
                    self.notice = f"can't place: {problem}"
            else:
                self.ghost_valid = self.model.can_place(self.current_part, self.ghost_pos, self.current_turns, frame)

    def set_half_snap(self, on: bool):
        self.half_snap = on
        self.refresh_ghost()

    def nudge_ghost(self, screen_dx: int, screen_dy: int):
        """Move the preview one sub-cell (half a cell) along the axis of its grid that best matches
        the screen direction (right = +screen_dx, up = +screen_dy) from the current view."""
        right_axis, up_axis = self._grid_axes(self.ghost_matrix() if self.ghost_pos is not None else glm.mat4(1.0))
        dx = right_axis[0] * screen_dx + up_axis[0] * screen_dy
        dy = right_axis[1] * screen_dx + up_axis[1] * screen_dy
        self.ghost_nudge = (self.ghost_nudge[0] + dx, self.ghost_nudge[1] + dy)
        self.refresh_ghost()

    def _grid_axes(self, matrix: glm.mat4):
        """Grid X / Y axes (as (x, y) steps) of a grid (grid space -> world `matrix`) that best match
        screen right and screen up from the current view: right gets the closer one (X on a tie),
        up the other. "Up" also counts "away from the viewer", so on a grid seen from above or the
        side, Up moves away."""
        view = self.camera.get_view_matrix()
        right = glm.vec3(view[0][0], view[1][0], view[2][0])
        up = glm.vec3(view[0][1], view[1][1], view[2][1])
        forward = -glm.vec3(view[0][2], view[1][2], view[2][2])
        x = glm.vec3(matrix * glm.vec4(1, 0, 0, 0))
        y = glm.vec3(matrix * glm.vec4(0, 1, 0, 0))
        away = up + forward
        if abs(glm.dot(x, right)) >= abs(glm.dot(y, right)):
            return (int(math.copysign(1, glm.dot(x, right))), 0), (0, int(math.copysign(1, glm.dot(y, away))))
        return (0, int(math.copysign(1, glm.dot(y, right)))), (int(math.copysign(1, glm.dot(x, away))), 0)
