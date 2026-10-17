"""Selection, groups and moving the selection (Select tool), plus the Paint and Erase tools.

A click selects a part's outermost group (double-click drills in, Alt: one part); a drag of a
selected part picks the selection up and puts it down on any face, grid, side stud or joint; arrow
keys / PgUp / PgDown nudge it along its own grid. See docs/design.md "Moving the selection".
"""
from PySide6.QtCore import Qt
import glm
import math
from typing import Optional
from brickbuilder.core.connections import groups
from brickbuilder.core import picking
from brickbuilder.core.tools import Tool


class SelectionMixin:
    """Mixed into ui.viewport.Viewport: uses its state (model, history, camera, ...)."""

    def set_current_color(self, color: str):
        self.current_color = color
        # Picking a colour in the Select tool recolours the selection (one undo step)
        if self.current_tool == Tool.SELECT and self.selection:
            self.history.set_colors(self.selection, color)
            self.update()
            self.edited.emit()

    def select_all(self):
        self.selection = set(self.model.parts)
        self.update()
        self.edited.emit()

    def clear_selection(self):
        if self.turning or self.dragging:  # Esc while turning or dragging cancels it
            self._cancel_moves()
            self.update()
            self.edited.emit()
            return
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

    def _home_frame(self, part_ids) -> int:
        """The frame most of the given parts are in (ties: the lower id)."""
        counts = {}
        for pid in part_ids:
            f = self.model.parts[pid].frame
            counts[f] = counts.get(f, 0) + 1
        return min(counts, key=lambda f: (-counts[f], f))

    def nudge_keys(self, screen_dx: int, screen_dy: int):
        """Arrow keys: move the selection (Select / Turn tool) or nudge the placement preview."""
        if self.current_tool in (Tool.SELECT, Tool.TURN) and self.selection and not self.dragging:
            self.nudge_selection(screen_dx, screen_dy, 0)
        elif self.current_tool == Tool.PLACE:
            self.nudge_ghost(screen_dx, screen_dy)

    def nudge_selection(self, screen_dx: int, screen_dy: int, layers: int) -> bool:
        """Move the selection along its own grid (never changing frames): half a cell (H on) or
        a whole cell along the grid axis nearest the screen direction, or `layers` layers up."""
        if not self.selection:
            return False
        frame = self._home_frame(self.selection)
        nx, ny, nz = self.profile.subdiv
        right, up = self._grid_axes(self.model.frame_matrix(frame))
        dx = (right[0] * screen_dx + up[0] * screen_dy) * (1 if self.half_snap else nx)
        dy = (right[1] * screen_dx + up[1] * screen_dy) * (1 if self.half_snap else ny)
        offset = self.profile.sub_to_world((dx, dy, layers * nz)) - self.profile.sub_to_world((0, 0, 0))
        world = glm.vec3(self.model.frame_matrix(frame) * glm.vec4(offset, 0.0))
        reason = self.history.move_parts(self.selection, glm.translate(glm.mat4(1.0), world))
        self.notice = f"can't move: {reason}" if reason else ""
        self.update()
        self.edited.emit()
        return reason is None

    def _start_drag(self, part, point, normal):
        """Pick up the selection by `part`: its bottom-layer cell under the cursor is the anchor,
        which goes where a placed part's anchor cell would."""
        frame = part.frame
        local, n = self.model.to_frame(frame, point, normal)
        s = self.profile.world_to_sub(local - n * 0.01)  # just inside the face that was hit
        nx, ny, _ = self.profile.subdiv
        cell = (part.pos[0] + math.floor((s[0] - part.pos[0]) / nx) * nx,
                part.pos[1] + math.floor((s[1] - part.pos[1]) / ny) * ny,
                part.pos[2])
        self.dragging = {"moving": set(self.selection), "frame": frame, "anchor": self._cell_centre(cell),
                         "grab": part.id, "turns": 0, "angle": 0.0, "target": None, "transform": None,
                         "valid": False, "joint_grid": None}
        self.select_rect = None

    def _update_drag(self, pos=None):
        d = self.dragging
        if pos is not None:
            d["pos"] = pos
            grab = self.model.parts[d["grab"]]
            # Onto a joint the grabbed part has the mate for: straight on (Space: rolled 180°)
            on_joint = self._joint_target(pos.x(), pos.y(), grab.part, grab.turns, d["moving"], d["turns"] % 2 == 1)
            if on_joint is not None:
                d["target"], d["joint_grid"] = (on_joint[0], None, None), on_joint[2]
            else:
                d["joint_grid"] = None
                frame, target, grid = self._target_under(pos.x(), pos.y(), d["moving"])
                if target is not None:
                    d["target"] = (frame, target, grid)
        if d["target"] is None:
            return
        if d["joint_grid"] is not None:
            # The grabbed part at pos 0 on that grid; everything moves with it
            grab = self.model.parts[d["grab"]]
            offset = self.profile.sub_to_world(grab.pos) - self.profile.sub_to_world((0, 0, 0))
            placed = self.model.frame_matrix(grab.frame) * glm.translate(glm.mat4(1.0), offset)
            d["transform"] = d["joint_grid"] * glm.inverse(placed)
            d["valid"] = self.model.moved_overlaps(d["moving"], d["transform"]) is None
            self.notice = ("onto the joint" + (", rolled 180°" if d["turns"] % 2 else " (Space: roll 180°)")
                           + ("" if d["valid"] else " (overlaps)"))
            self.update()
            self.edited.emit()
            return
        # On a side stud the target grid may not be a frame yet (`grid`, in `frame`'s space):
        # move_parts then makes it, as a child of `frame`
        frame, target, on_grid = d["target"]
        c_t = self._cell_centre(target)
        # The anchor's grid onto the target's grid: anchor cell centre onto the target cell centre,
        # turned by whole quarter turns, then any fine turn about that centre
        grid = (glm.translate(glm.mat4(1.0), c_t)
                * glm.mat4_cast(glm.angleAxis(math.radians(d["turns"] * 90 + d["angle"]), glm.vec3(0, 0, 1)))
                * glm.translate(glm.mat4(1.0), -d["anchor"]))
        if on_grid is not None:
            grid = on_grid * grid
        d["transform"] = self.model.frame_matrix(frame) * grid * glm.inverse(self.model.frame_matrix(d["frame"]))
        d["valid"] = self.model.moved_overlaps(d["moving"], d["transform"]) is None
        turned = d["turns"] * 90 + d["angle"]
        self.notice = (f"moving {len(d['moving'])} part{'s' if len(d['moving']) != 1 else ''}"
                       + (f", turned {turned:g}°" if turned else "") + ("" if d["valid"] else " (overlaps)"))
        self.update()
        self.edited.emit()

    def _finish_drag(self):
        d, self.dragging = self.dragging, None
        if d["transform"] is None:
            self.notice = ""
        else:
            reason = self.history.move_parts(d["moving"], d["transform"], d["target"][0])
            self.notice = f"can't move: {reason}" if reason else ""
        self.update()
        self.edited.emit()

    def delete_selection(self):
        self._cancel_moves()
        if self.selection:
            self.history.remove_parts(self.selection)
            self.selection = set()
            self.update()
            self.edited.emit()

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
