"""The Turn tool: turning about the holding studs, sliding along a slot, posing ball joints.

Plans come from motion.plan_turn; previews are drawn from the parts' own display lists under the
move's matrix; commits go through History.move_parts. How it's checked: docs/turning.md.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
import glm
import math
from typing import Optional
from brickbuilder.core.model import angle_about, plane_basis, turn_about
from brickbuilder.core import picking
from brickbuilder.core.connections import joint_limits
from brickbuilder.core.motion import clamp_arm, joint_angles, min_rotation, plan_turn
from brickbuilder.core.tools import Tool


class TurningMixin:
    """Mixed into ui.viewport.Viewport: uses its state (model, history, camera, ...)."""

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

    def reset_joint(self) -> bool:
        """Ctrl+Shift+R: like Shift+R, but a joint also loses its roll: back the way it was placed
        (straight, tops the same way)."""
        return self.realign_selection(reset_roll=True)

    def realign_selection(self, reset_roll: bool = False) -> bool:
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
        if plan.kind == "pose":  # straighten the joint (the roll stays, unless reset_roll)
            j = plan.joint
            ball_moves = j.ball_part in plan.moving
            if reset_roll:
                # Turn the moving part's arm (or cup) straight and its up onto the other part's up
                def up(pid):
                    return glm.vec3(self.model.frame_matrix(self.model.parts[pid].frame) * glm.vec4(0, 0, 1, 0))
                mine, other = (j.ball_part, j.cup_part) if ball_moves else (j.cup_part, j.ball_part)
                axis, target = (j.ball_axis, -j.cup_axis) if ball_moves else (j.cup_axis, -j.ball_axis)

                def basis(x, z):
                    x = glm.normalize(x)
                    z = glm.normalize(z - x * glm.dot(z, x))
                    return glm.mat3(x, z, glm.cross(x, z))
                q = glm.quat_cast(basis(target, up(other)) * glm.transpose(basis(axis, up(mine))))
            else:
                q = min_rotation(j.ball_axis, -j.cup_axis) if ball_moves else min_rotation(j.cup_axis, -j.ball_axis)
            if glm.length(glm.vec3(q.x, q.y, q.z)) < 1e-6:
                self.notice = "the joint is already " + ("as placed" if reset_roll else "straight")
                self.edited.emit()
                return False
            return self._commit_turn(plan.moving, self._about(pivot, q))
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

    @staticmethod
    def _about(pivot: glm.vec3, q: glm.quat) -> glm.mat4:
        """A rotation `q` about `pivot`, as a world transform."""
        return glm.translate(glm.mat4(1.0), pivot) * glm.mat4_cast(q) * glm.translate(glm.mat4(1.0), -pivot)

    def _commit_turn(self, moving, transform) -> bool:
        if not self.model.joints_within_limits(moving, transform):
            self.notice = "can't turn: a joint can't bend that far"
            self.update()
            self.edited.emit()
            return False
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
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl and plan_turn(self.model, self.selection, point).kind != "pose":
            self._start_slide(event, point)
            return
        plan, pivot = self._turn_plan(point)
        if plan is not None and plan.kind == "pose":
            j = plan.joint
            arm = glm.normalize(j.ball_axis)
            self.turning = {"moving": plan.moving, "pivot": pivot, "axis": arm, "joint": j,
                            "mode": "roll" if ctrl else "pose", "ball_moves": j.ball_part in plan.moving,
                            "last": self._turn_angle(event.position(), pivot, arm) or 0.0, "raw": 0.0,
                            "angle": 0.0, "transform": glm.mat4(1.0), "valid": True, "moved": False}
            theta, phi = joint_angles(j.ball_axis, j.cup_axis, j.cup_slot)
            self.notice = f"joint: tilt {theta:.3g}°, direction {phi:.3g}°" if not ctrl else "rolling 0°"
            self.update()
            self.edited.emit()
            return
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
                            "range": self._slide_range(plan), "distance": 0.0, "angle": 0.0,
                            "transform": glm.mat4(1.0), "valid": True}
            self.notice = "sliding 0 mm"
        self.update()
        self.edited.emit()

    @staticmethod
    def _slide_range(plan) -> tuple:
        """How far (mm, both ways along plan.slide) the selection can slide and stay held: while at
        least one of its studs is still in its slot."""
        intervals = []
        for c in plan.contacts:
            a, b = c.slot
            along = b - a
            length2 = glm.dot(along, along)
            if length2 < 1e-9:
                continue  # a point antistud: it doesn't slide
            # The stud's place along the slot, as the selection slides t mm (the stud moves with it if
            # it's on the moving side, else the slot does, the other way)
            sign = 1.0 if c.stud_part in plan.moving else -1.0
            u0 = glm.dot(c.stud - a, along) / length2
            du = sign * glm.dot(plan.slide, along) / length2
            if abs(du) < 1e-12:
                continue
            lo, hi = sorted(((0.0 - u0) / du, (1.0 - u0) / du))
            intervals.append((lo, hi))
        lo = hi = 0.0
        for a, b in sorted(intervals):  # grow the stretch around 0 through overlapping intervals
            if a <= hi + 1e-6 and b >= lo - 1e-6:
                lo, hi = min(lo, a), max(hi, b)
        return lo, hi

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
        lo, hi = t["range"]  # stay held: stop where the last stud would leave its slot
        if free:
            distance = max(lo, min(hi, raw))
        else:
            distance = max(math.ceil(lo / step - 1e-6), min(math.floor(hi / step + 1e-6), round(raw / step))) * step
        at_end = abs(distance - raw) > step / 2 and (abs(distance - lo) < 1e-6 or abs(distance - hi) < 1e-6)
        if distance != t["distance"]:
            t["distance"] = distance
            t["transform"] = glm.translate(glm.mat4(1.0), t["slide"] * distance)
            t["valid"] = self.model.moved_overlaps(t["moving"], t["transform"]) is None
        self.notice = (f"sliding {t['distance']:.3g} mm" + (" (end of the slot)" if at_end else "")
                       + ("" if t["valid"] else " (overlaps)"))
        self.edited.emit()

    def _pose_valid(self, t) -> bool:
        return (self.model.moved_overlaps(t["moving"], t["transform"]) is None
                and self.model.joints_within_limits(t["moving"], t["transform"]))

    def _drag_pose(self, event: QMouseEvent):
        """Drag on a ball joint: the part points at the cursor (the cursor's spot on the plane facing
        the camera through the joint's centre), snapped as tilt and direction and kept inside the
        cup's cone, or else in its slot."""
        t, j = self.turning, self.turning["joint"]
        view = self.camera.get_view_matrix()
        facing = glm.vec3(view[0][2], view[1][2], view[2][2])  # toward the viewer
        ray = picking.get_mouse_ray(event.position().x(), event.position().y(), self.width(), self.height(), self.camera)
        hit = picking.intersect_plane(ray, facing, t["pivot"])
        if hit is None:
            return
        towards = ray.origin + ray.direction * hit - t["pivot"]
        if glm.length(towards) < 0.5:
            return  # too close to the centre to tell a direction
        towards = glm.normalize(towards)
        cone, slot = joint_limits(self.profile)
        step = None if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.rotation_snap
        if t["ball_moves"]:
            # The ball part hangs on the far side of its arm: the arm points away from the cursor
            arm, theta, phi = clamp_arm(-towards, j.cup_axis, j.cup_slot, cone, slot, step)
            q = min_rotation(j.ball_axis, arm)
        else:
            # The cup part moves: its body is behind the cup. Turn it, see where the (still) arm
            # would sit in it, clamp that, and turn the cup so the arm sits there
            s = min_rotation(-j.cup_axis, towards)
            relative, theta, phi = clamp_arm(glm.inverse(s) * j.ball_axis, j.cup_axis, j.cup_slot, cone, slot, step)
            q = min_rotation(relative, j.ball_axis)
        t["transform"] = self._about(t["pivot"], q)
        t["moved"] = True
        t["valid"] = self._pose_valid(t)
        self.notice = f"joint: tilt {theta:.3g}°, direction {phi:.3g}°" + ("" if t["valid"] else " (overlaps)")
        self.update()
        self.edited.emit()

    def _drag_roll(self, event: QMouseEvent):
        """Ctrl+drag on a ball joint: roll about the arm."""
        t = self.turning
        a = self._turn_angle(event.position(), t["pivot"], t["axis"])
        if a is None:
            return
        t["raw"] += (a - t["last"] + 180) % 360 - 180
        t["last"] = a
        free = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        angle = t["raw"] if free else round(t["raw"] / self.rotation_snap) * self.rotation_snap
        if angle != t["angle"]:
            t["angle"] = angle
            t["transform"] = turn_about(t["pivot"], t["axis"], angle)
            t["moved"] = abs(angle) > 1e-9
            t["valid"] = self._pose_valid(t)
            self.notice = f"rolling {angle:.4g}°" + ("" if t["valid"] else " (blocked)")
            self.edited.emit()

    def _drag_turn(self, event: QMouseEvent):
        t = self.turning
        if t.get("slide") is not None:
            self._drag_slide(event)
            return
        if t.get("mode") == "pose":
            self._drag_pose(event)
            return
        if t.get("mode") == "roll":
            self._drag_roll(event)
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
            t["valid"] = self._pose_valid(t)  # no clash, and any joints within their limits
            self.notice = f"turning {angle:.4g}°" + ("" if t["valid"] else " (blocked)")
            self.edited.emit()

    def _finish_turn(self):
        t, self.turning = self.turning, None
        if abs(t["angle"]) > 1e-9 or abs(t.get("distance", 0.0)) > 1e-9 or t.get("moved"):
            self._commit_turn(t["moving"], t["transform"])
        else:
            self.notice = ""
            self.update()
            self.edited.emit()

    def _moving_preview(self):
        """(part ids, world transform, valid) for whatever is being turned or dragged, or None."""
        for state in (self.turning, self.dragging):
            if state and state.get("transform") is not None:
                return state["moving"], state["transform"], state["valid"]
        return None
