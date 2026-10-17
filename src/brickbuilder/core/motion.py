"""What a turn moves and how it may move: the free motions its contacts leave.

Moving set: the selection always moves, plus whatever hangs only off it; the rest of its connected
component stays if it's pinned (grounded: a part on the root grid's layer 0), otherwise the
largest piece of the rest stays (docs/part_format.md, "Pins").

Free motion: the moving set's motion is a turn w (about any axis) plus a shift v of a reference
point, six numbers. Each contact, linearised, is a set of rows that must stay zero: a stud in a slot
keeps its base on the slot's line and at its depth, and doesn't tilt off the slot's axis; a ball in
a cup keeps its centre still. The free motions are the null space of those rows. What's left:
one turning axis -> "turn" about it (studs, a side stud, two joints on a line: a hinge); turning
every way about a joint's centre -> "pose"; only shifting -> a slide; nothing -> locked.
A pivot on a contact (a stud, a joint's centre) is preferred: turning about it keeps that contact
exactly, not just to first order. See docs/turning.md.
"""
from dataclasses import dataclass, field
import math
from typing import List, Optional, Set, Tuple

import glm
import numpy as np

from brickbuilder.core.connections import Contact, JointContact, contacts_between, joint_contacts
from brickbuilder.core.model import plane_basis

# Errors are in mm, from float32 positions: a turned frame puts studs ~1e-6 mm off, so anything
# below this counts as zero (well under connections.TOLERANCE)
EPS = 1e-4
ROT_EPS = 1e-6  # turning parts of the free motions are unit-less: below this, no turning


@dataclass
class TurnPlan:
    kind: str                       # "free" (not held), "turn" (about pivot), "pose" (a ball joint) or "locked"
    moving: Set[int]
    fixed: Set[int] = field(default_factory=set)
    pivot: Optional[glm.vec3] = None  # a point on the line to turn about ("turn")
    axis: glm.vec3 = field(default_factory=lambda: glm.vec3(0, 0, 1))  # its direction
    reason: str = ""
    contacts: List[Contact] = field(default_factory=list)
    slide: Optional[glm.vec3] = None  # a direction it can slide along without turning (a slot), if any
    joints: List[JointContact] = field(default_factory=list)
    joint: Optional[JointContact] = None  # "pose": the joint it turns about (its pivot is `pivot`)


def grounded(placed) -> bool:
    return placed.frame == 0 and placed.pos[2] == 0


def moving_set(model, selection) -> (Set[int], Set[int]):
    """(moving, fixed) for turning `selection`: see the module docstring."""
    links = model.connections()
    selection = set(selection) & set(model.parts)
    component, todo = set(), list(selection)
    while todo:
        pid = todo.pop()
        if pid not in component:
            component.add(pid)
            todo.extend(links[pid] - component)
    rest = component - selection
    pieces, seen = [], set()
    for start in sorted(rest):
        if start in seen:
            continue
        piece, todo = set(), [start]
        while todo:
            pid = todo.pop()
            if pid not in piece:
                piece.add(pid)
                todo.extend((links[pid] & rest) - piece)
        seen |= piece
        pieces.append(piece)
    if not pieces:
        return component, set()
    stay = [p for p in pieces if any(grounded(model.parts[pid]) for pid in p)]
    if not stay:
        stay = [max(pieces, key=lambda p: (len(p), -min(p)))]
    fixed = set().union(*stay)
    return component - fixed, fixed


def _skew_rows(r: glm.vec3, directions) -> List[List[float]]:
    """Rows keeping the point at `r` (from the reference point) still along each direction: the
    velocity there is v + w x r, so along d it's d.v + w.(r x d)."""
    rows = []
    for d in directions:
        rd = glm.cross(r, d)
        rows.append([rd.x, rd.y, rd.z, d.x, d.y, d.z])
    return rows


def _stud_rows(contact: Contact, centre: glm.vec3) -> List[List[float]]:
    """A stud in a slot: its base stays on the slot's line (and at its depth), and it can't tilt
    off the slot's axis. Free: turning about the stud, and sliding along a long slot."""
    n = glm.normalize(contact.axis)
    u, v = plane_basis(n)
    a, b = contact.slot
    t = b - a
    if glm.length(t) < 1e-9:
        directions = [n, u, v]                                   # a point: held every way
    else:
        directions = [n, glm.normalize(glm.cross(glm.normalize(t), n))]  # free along the slot
    tilt = [[u.x, u.y, u.z, 0.0, 0.0, 0.0], [v.x, v.y, v.z, 0.0, 0.0, 0.0]]
    return _skew_rows(contact.stud - centre, directions) + tilt


def _joint_rows(joint: JointContact, centre: glm.vec3) -> List[List[float]]:
    """A ball in a cup: its centre stays put. Free: turning any way about it."""
    return _skew_rows(joint.pivot - centre, [glm.vec3(1, 0, 0), glm.vec3(0, 1, 0), glm.vec3(0, 0, 1)])


def plan_turn(model, selection, hint: Optional[glm.vec3] = None) -> TurnPlan:
    """How the selection may turn. `hint` (a world point, e.g. under the cursor) picks the pivot
    when more than one contact would do."""
    moving, fixed = moving_set(model, selection)
    if not moving:
        return TurnPlan("locked", moving, fixed, reason="nothing selected")
    if not fixed:
        return TurnPlan("free", moving, reason="not held by anything else")
    moving_parts, fixed_parts = [model.parts[p] for p in moving], [model.parts[p] for p in fixed]
    contacts = contacts_between(model.profile, moving_parts, fixed_parts)
    joints = joint_contacts(model.profile, moving_parts, fixed_parts)
    if not contacts and not joints:  # connected through the selection but no contact between the sides
        return TurnPlan("free", moving, fixed, reason="not held by anything else")
    centre = contacts[0].stud if contacts else joints[0].pivot
    a = np.array([row for c in contacts for row in _stud_rows(c, centre)]
                 + [row for j in joints for row in _joint_rows(j, centre)])
    _, s, vh = np.linalg.svd(a)
    rank = int(np.sum(s > EPS))
    null = vh[rank:]                                  # free motions (w, v)
    plan = TurnPlan("locked", moving, fixed, contacts=contacts, joints=joints)
    if len(null) == 0:
        plan.reason = "held by studs on different axes"
        return plan

    def free(w: glm.vec3, p: glm.vec3) -> bool:
        """Is turning about the line through p along w a free motion?"""
        vel = glm.cross(w, centre - p)  # velocity of the reference point
        q = np.array([w.x, w.y, w.z, vel.x, vel.y, vel.z])
        return float(np.linalg.norm(a @ q)) < EPS * float(np.linalg.norm(q))

    turning = null[:, :3]
    tu, ts, tvh = np.linalg.svd(turning)
    turn_rank = int(np.sum(ts > ROT_EPS))
    # Sliding: free motions with no turning in them
    shifts = tu[:, turn_rank:].T @ null[:, 3:] if turn_rank < len(null) else np.zeros((0, 3))
    shifts = [glm.vec3(*map(float, x)) for x in shifts if np.linalg.norm(x) > EPS]
    if len(shifts) == 1:
        plan.slide = glm.normalize(shifts[0])

    candidates = [c.stud for c in contacts] + [j.pivot for j in joints]
    if hint is not None:
        candidates.sort(key=lambda p: glm.distance(p, hint))
    if turn_rank == 1:
        w = glm.normalize(glm.vec3(*map(float, tvh[0])))
        if contacts and glm.dot(w, contacts[0].axis) < 0:
            w = -w  # point it the way the studs do
        elif not contacts and w.z < -1e-6:
            w = -w
        pivot = next((p for p in candidates if free(w, p)), None)
        if pivot is None:  # a line through none of the contacts: from the free motion itself
            coeffs = np.linalg.lstsq(turning.T, np.array([w.x, w.y, w.z]), rcond=None)[0]
            q = coeffs @ null
            vel = glm.vec3(*map(float, q[3:]))
            pivot = centre + glm.cross(w, vel - w * glm.dot(vel, w))
        plan.kind, plan.pivot, plan.axis = "turn", pivot, w
        return plan
    if turn_rank == 3:
        for j in joints:
            if all(free(glm.vec3(*e), j.pivot) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))):
                plan.kind, plan.pivot, plan.joint = "pose", j.pivot, j
                plan.axis = glm.normalize(j.ball_axis)
                return plan
    if turn_rank == 0:
        plan.reason = "the contacts only allow sliding, not turning" if plan.slide else "held by studs on different axes"
    else:
        plan.reason = "it can turn more than one way here, which can't be posed yet"
    return plan


# --- posing a ball joint -------------------------------------------------------------------

def min_rotation(a: glm.vec3, b: glm.vec3) -> glm.quat:
    """The smallest rotation taking direction a onto direction b."""
    a, b = glm.normalize(a), glm.normalize(b)
    axis = glm.cross(a, b)
    d = max(-1.0, min(1.0, glm.dot(a, b)))
    if glm.length(axis) < 1e-9:
        if d > 0:
            return glm.quat()
        u, _ = plane_basis(a)
        return glm.angleAxis(math.pi, u)
    return glm.angleAxis(math.acos(d), glm.normalize(axis))


def joint_angles(arm: glm.vec3, cup_axis: glm.vec3, cup_slot: glm.vec3) -> Tuple[float, float]:
    """(tilt θ, direction φ) in degrees of an arm direction relative to a cup: θ from straight (the
    arm pointing into the cup), φ around it from the slot direction."""
    straight = -glm.normalize(cup_axis)
    e1 = glm.normalize(cup_slot - straight * glm.dot(cup_slot, straight))
    e2 = glm.cross(straight, e1)
    d = glm.normalize(arm)
    theta = math.degrees(math.acos(max(-1.0, min(1.0, glm.dot(d, straight)))))
    phi = math.degrees(math.atan2(glm.dot(d, e2), glm.dot(d, e1)))
    return theta, phi


def clamp_arm(arm: glm.vec3, cup_axis: glm.vec3, cup_slot: glm.vec3, cone: float, slot: float,
              step: Optional[float]) -> Tuple[glm.vec3, float, float]:
    """The allowed arm direction nearest `arm`: θ and φ snapped to `step` (None: free), inside the
    cone, else in the slot's plane (φ = 0 or 180) up to the slot's range. Returns (arm, θ, φ)."""
    theta, phi = joint_angles(arm, cup_axis, cup_slot)
    if step:
        theta, phi = round(theta / step) * step, round(phi / step) * step
    if theta > cone + 1e-6:
        phi = 0.0 if abs(phi) <= 90 else 180.0
        theta = min(theta, slot)
    straight = -glm.normalize(cup_axis)
    e1 = glm.normalize(cup_slot - straight * glm.dot(cup_slot, straight))
    e2 = glm.cross(straight, e1)
    t, p = math.radians(theta), math.radians(phi)
    return straight * math.cos(t) + (e1 * math.cos(p) + e2 * math.sin(p)) * math.sin(t), theta, phi
