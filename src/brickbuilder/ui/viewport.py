from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
import OpenGL.GL as gl
import glm
import math
from typing import Optional
from brickbuilder.core.renderer import Renderer
from brickbuilder.core.camera import Camera
from brickbuilder.core.connections import groups
from brickbuilder.core.history import History
from brickbuilder.core.model import (Model, Sub, anchor_cells, decompose, default_anchor_index, origin_for_anchor,
                                     angle_about, placement_target, plane_basis, turn_about, turn_about_z)
from brickbuilder.core.parts import PartDef, load_builtin_library
from brickbuilder.core.profile import load_builtin_profile
from brickbuilder.core import picking
from brickbuilder.core.motion import plan_turn
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
            ghost = (geo["solids"], geo["studs"], self.ghost_valid, geo["stud_axes"], [(a, b, n) for (a, b), n in zip(geo["antistuds"], geo["antistud_axes"])], blocking)
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

    def set_current_part(self, part: PartDef):
        self.current_part = part
        self.current_anchor = default_anchor_index(part)
        self.refresh_ghost()

    def rotate_current_part(self, quarter_turns: int):
        if self.dragging:  # Space while dragging the selection turns it
            self.dragging["turns"] = (self.dragging["turns"] + quarter_turns) % 4
            self._update_drag()
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

    # --- turning (Turn tool) ------------------------------------------------------------------

    def _turn_plan(self, hint=None):
        """Plan a turn of the selection; returns (plan, pivot) or (None, None) with a notice."""
        if not self.selection:
            self.notice = "select something to turn"
            return None, None
        plan = plan_turn(self.model, self.selection, hint)
        if plan.kind == "locked":
            self.notice = f"can't turn: {plan.reason}"
            return None, None
        if plan.kind == "free":  # not held: turn about the middle of what moves
            lo = glm.vec3(min(self.model.parts[p].box[0].x for p in plan.moving),
                          min(self.model.parts[p].box[0].y for p in plan.moving),
                          min(self.model.parts[p].box[0].z for p in plan.moving))
            hi = glm.vec3(max(self.model.parts[p].box[1].x for p in plan.moving),
                          max(self.model.parts[p].box[1].y for p in plan.moving),
                          max(self.model.parts[p].box[1].z for p in plan.moving))
            return plan, glm.vec3((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
        return plan, plan.pivot

    def turn_selection(self, degrees: float) -> bool:
        """Turn the selection (and what hangs off it) by an angle, as one undo step."""
        plan, pivot = self._turn_plan()
        if plan is None:
            self.edited.emit()
            return False
        return self._commit_turn(plan.moving, turn_about(pivot, plan.axis, degrees))

    @staticmethod
    def _add_angle(turns: int, angle: float, degrees: float):
        """(quarter turns, fine angle 0 <= a < 90) after turning by `degrees` more."""
        total = angle + degrees
        quarters = math.floor(total / 90 + 1e-9)
        rest = total - 90 * quarters
        return (turns + quarters) % 4, (0.0 if abs(rest) < 1e-9 or abs(rest - 90) < 1e-9 else rest)

    def turn_step(self, sign: int):
        if self.dragging:
            d = self.dragging
            d["turns"], d["angle"] = self._add_angle(d["turns"], d["angle"], sign * self.rotation_snap)
            self._update_drag()
            return
        if self.current_tool == Tool.PLACE:
            self.turn_ghost(sign * self.rotation_snap)
        else:
            self.turn_selection(sign * self.rotation_snap)

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

    def realign_selection(self) -> bool:
        """Shift+R: turn the selection to the nearest quarter turn of the grid it's held on (the
        root grid if it isn't held), which puts it back on that grid. In the Place tool: the
        preview back onto its grid."""
        if self.dragging:
            d = self.dragging
            if d["angle"] > 45:
                d["turns"] = (d["turns"] + 1) % 4
            d["angle"] = 0.0
            self._update_drag()
            return True
        if self.current_tool == Tool.PLACE:
            if self.ghost_angle:
                self.turn_ghost(90 - self.ghost_angle if self.ghost_angle > 45 else -self.ghost_angle)
            return True
        plan, pivot = self._turn_plan()
        if plan is None:
            self.edited.emit()
            return False
        held = plan.contacts[0] if plan.contacts else None
        if held is not None:
            mine, other = ((held.stud_part, held.slot_part) if held.stud_part in plan.moving
                           else (held.slot_part, held.stud_part))
            base = glm.mat3(self.model.frame_matrix(self.model.parts[other].frame))
        else:
            mine = min(plan.moving)
            base = glm.mat3(1.0)
        own = glm.mat3(self.model.frame_matrix(self.model.parts[mine].frame))

        def across(m):  # the grid axis of `m` that lies most across the turning axis
            return max((m[0], m[1], m[2]), key=lambda v: glm.length(glm.cross(v, plan.axis)))
        angle = angle_about(plan.axis, across(base), across(own))
        delta = round(angle / 90) * 90 - angle
        if abs(delta) < 1e-4:
            self.notice = "already lined up with the grid"
            self.edited.emit()
            return False
        return self._commit_turn(plan.moving, turn_about(pivot, plan.axis, delta))

    def _commit_turn(self, moving, transform) -> bool:
        reason = self.history.move_parts(moving, transform)
        self.notice = f"can't turn: {reason}" if reason else ""
        self.update()
        self.edited.emit()
        return reason is None

    def _turn_angle(self, pos, pivot: glm.vec3, axis: glm.vec3) -> Optional[float]:
        """Angle (degrees) of the point under the cursor around the pivot, on the plane across the
        turning axis."""
        ray = picking.get_mouse_ray(pos.x(), pos.y(), self.width(), self.height(), self.camera)
        t = picking.intersect_plane(ray, axis, pivot)
        if t is None:
            return None
        p = ray.origin + ray.direction * t - pivot
        u, v = plane_basis(axis)
        return math.degrees(math.atan2(glm.dot(p, v), glm.dot(p, u)))

    def _start_turn(self, event: QMouseEvent):
        hit, _, point = picking.intersect_model(
            picking.get_mouse_ray(event.position().x(), event.position().y(), self.width(), self.height(), self.camera),
            self.model)
        if hit is None:  # empty space: deselect, like the Select tool
            self._clear_selection_state()
            self.update()
            self.edited.emit()
            return
        if hit.id not in self.selection:
            self.selection = self._unit(hit.id, bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._start_slide(event, point)
            return
        plan, pivot = self._turn_plan(point)
        if plan is not None:
            start = self._turn_angle(event.position(), pivot, plan.axis)
            self.turning = {"moving": plan.moving, "pivot": pivot, "axis": plan.axis, "last": start or 0.0,
                            "raw": 0.0, "angle": 0.0, "transform": glm.mat4(1.0), "valid": True}
            self.notice = "turning 0°"
        self.update()
        self.edited.emit()

    def _start_slide(self, event: QMouseEvent, point: glm.vec3):
        """Ctrl+drag in the Turn tool: slide along the slot the selection is held in."""
        plan = plan_turn(self.model, self.selection, point)
        if plan.slide is None:
            self.notice = "can't slide: " + ("not held by anything else" if plan.kind == "free"
                                             else "nothing to slide along")
        else:
            start = self._slide_point(event.position(), point, plan.axis)
            self.turning = {"moving": plan.moving, "slide": plan.slide, "axis": plan.axis, "origin": point,
                            "start": start if start is not None else point, "pivot": None,
                            "distance": 0.0, "angle": 0.0, "transform": glm.mat4(1.0), "valid": True}
            self.notice = "sliding 0 mm"
        self.update()
        self.edited.emit()

    def _slide_point(self, pos, through: glm.vec3, axis: glm.vec3) -> Optional[glm.vec3]:
        """The point under the cursor on the plane across `axis` through `through`."""
        ray = picking.get_mouse_ray(pos.x(), pos.y(), self.width(), self.height(), self.camera)
        t = picking.intersect_plane(ray, axis, through)
        return None if t is None else ray.origin + ray.direction * t

    def _drag_slide(self, event: QMouseEvent):
        t = self.turning
        p = self._slide_point(event.position(), t["origin"], t["axis"])
        if p is None:
            return
        raw = glm.dot(p - t["start"], t["slide"])
        step = self.profile.cell.x / self.profile.subdiv[0]  # half a cell
        free = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        distance = raw if free else round(raw / step) * step
        if distance != t["distance"]:
            t["distance"] = distance
            t["transform"] = glm.translate(glm.mat4(1.0), t["slide"] * distance)
            t["valid"] = self.model.moved_overlaps(t["moving"], t["transform"]) is None
            self.notice = f"sliding {distance:.3g} mm" + ("" if t["valid"] else " (overlaps)")
            self.edited.emit()

    def _drag_turn(self, event: QMouseEvent):
        t = self.turning
        if t.get("slide") is not None:
            self._drag_slide(event)
            return
        a = self._turn_angle(event.position(), t["pivot"], t["axis"])
        if a is None:
            return
        step = (a - t["last"] + 180) % 360 - 180  # unwrapped, so it can go round more than once
        t["last"] = a
        t["raw"] += step
        free = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        angle = t["raw"] if free else round(t["raw"] / self.rotation_snap) * self.rotation_snap
        if angle != t["angle"]:
            t["angle"] = angle
            t["transform"] = turn_about(t["pivot"], t["axis"], angle)
            t["valid"] = self.model.moved_overlaps(t["moving"], t["transform"]) is None
            self.notice = f"turning {angle:.4g}°" + ("" if t["valid"] else " (overlaps)")
            self.edited.emit()

    def _finish_turn(self):
        t, self.turning = self.turning, None
        if abs(t["angle"]) > 1e-9 or abs(t.get("distance", 0.0)) > 1e-9:
            self._commit_turn(t["moving"], t["transform"])
        else:
            self.notice = ""
            self.update()
            self.edited.emit()

    # --- moving the selection -------------------------------------------------------------------

    def _moving_preview(self):
        """(part ids, world transform, valid) for whatever is being turned or dragged, or None."""
        for state in (self.turning, self.dragging):
            if state and state.get("transform") is not None:
                return state["moving"], state["transform"], state["valid"]
        return None

    def _home_frame(self, part_ids) -> int:
        """The frame most of the given parts are in (ties: the lower id)."""
        counts = {}
        for pid in part_ids:
            f = self.model.parts[pid].frame
            counts[f] = counts.get(f, 0) + 1
        return min(counts, key=lambda f: (-counts[f], f))

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
                         "turns": 0, "angle": 0.0, "target": None, "transform": None, "valid": False}
        self.select_rect = None

    def _update_drag(self, pos=None):
        d = self.dragging
        if pos is not None:
            frame, target, grid = self._target_under(pos.x(), pos.y(), d["moving"])
            if target is not None:
                d["target"] = (frame, target, grid)
        if d["target"] is None:
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

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()

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

    def update_ghost(self, mouse_x, mouse_y):
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
        """Move the preview one sub-cell (half a cell) along the axis of its grid that best matches
        the screen direction (right = +screen_dx, up = +screen_dy) from the current view."""
        right_axis, up_axis = self._grid_axes(self.ghost_matrix() if self.ghost_pos is not None else glm.mat4(1.0))
        dx = right_axis[0] * screen_dx + up_axis[0] * screen_dy
        dy = right_axis[1] * screen_dx + up_axis[1] * screen_dy
        self.ghost_nudge = (self.ghost_nudge[0] + dx, self.ghost_nudge[1] + dy)
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
