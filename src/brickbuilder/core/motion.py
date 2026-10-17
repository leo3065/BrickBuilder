"""What a turn moves and how it may turn: about the axis its holding studs share.

Moving set: the selection always moves, plus whatever hangs only off it; the rest of its connected
component stays if it's pinned (grounded: a part on the root grid's layer 0), otherwise the
largest piece of the rest stays (docs/part_format.md, "Pins").

Free motion: the contacts between the moving and the staying parts, linearised. Each stud in a
slot is an error that must stay zero (the stud's distance from the slot's line; both directions
for a point antistud), measured in the plane across the studs' shared axis (vertical for top
studs, horizontal for a side stud). The moving set's motion in that plane is (angle, x, y); the
motions that keep every error at zero are the null space of the errors' Jacobian. A turn about a contact stud that's in
that null space is the turn the tool offers (it keeps the contact exactly, not just to first
order). No null space with a turn in it: locked.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Set

import glm
import numpy as np

from brickbuilder.core.connections import AXIS_TOLERANCE, Contact, contacts_between
from brickbuilder.core.model import plane_basis

# Errors are in mm, from float32 positions: a turned frame puts studs ~1e-6 mm off, so anything
# below this counts as zero (well under connections.TOLERANCE)
EPS = 1e-4


@dataclass
class TurnPlan:
    kind: str                       # "free" (not held), "turn" (about pivot) or "locked"
    moving: Set[int]
    fixed: Set[int] = field(default_factory=set)
    pivot: Optional[glm.vec3] = None  # a point on the line to turn about ("turn")
    axis: glm.vec3 = field(default_factory=lambda: glm.vec3(0, 0, 1))  # its direction
    reason: str = ""
    contacts: List[Contact] = field(default_factory=list)
    slide: Optional[glm.vec3] = None  # a direction it can slide along without turning (a slot), if any


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


def _jacobian_rows(contact: Contact, centre: glm.vec3, basis) -> List[List[float]]:
    """Rows d(error)/d(angle, x, y) for one contact, turning about `centre` in the plane spanned by
    `basis` (u, v). The stud and the slot move relative to each other, so it doesn't matter which
    one is on the moving side."""
    bu, bv = basis
    d = contact.stud - centre
    rx, ry = glm.dot(d, bu), glm.dot(d, bv)
    j = np.array([[-ry, 1.0, 0.0],    # d(stud.u)
                  [rx, 0.0, 1.0]])    # d(stud.v)
    a, b = contact.slot
    s = glm.vec2(glm.dot(b - a, bu), glm.dot(b - a, bv))
    if glm.length(s) < 1e-9:
        return j.tolist()             # a point antistud: both directions
    s = glm.normalize(s)
    n = np.array([-s.y, s.x])         # across the slot
    return [list(n @ j)]


def plan_turn(model, selection, hint: Optional[glm.vec3] = None) -> TurnPlan:
    """How the selection may turn. `hint` (a world point, e.g. under the cursor) picks the pivot
    when more than one contact would do."""
    moving, fixed = moving_set(model, selection)
    if not moving:
        return TurnPlan("locked", moving, fixed, reason="nothing selected")
    if not fixed:
        return TurnPlan("free", moving, reason="not held by anything else")
    contacts = contacts_between(model.profile, [model.parts[p] for p in moving], [model.parts[p] for p in fixed])
    if not contacts:  # connected through the selection but no contact between the two sides
        return TurnPlan("free", moving, fixed, reason="not held by anything else")
    axis = contacts[0].axis
    if any(abs(glm.dot(c.axis, axis)) < 1 - AXIS_TOLERANCE for c in contacts):
        return TurnPlan("locked", moving, fixed, reason="held by studs pointing different ways", contacts=contacts)
    basis = plane_basis(axis)
    bu, bv = basis
    centre = contacts[0].stud
    a = np.array([row for c in contacts for row in _jacobian_rows(c, centre, basis)])
    _, s, vh = np.linalg.svd(a)
    rank = int(np.sum(s > EPS))
    if rank >= 3:
        return TurnPlan("locked", moving, fixed, reason="held by studs on different axes", contacts=contacts)
    slide = _slide(vh[rank:], bu, bv)

    def in_plane(p: glm.vec3):
        d = p - centre
        return round(glm.dot(d, bu), 4), round(glm.dot(d, bv), 4)

    def turns_freely_about(x: float, y: float) -> bool:
        q = np.array([1.0, y, -x])  # turning about (x, y): velocity at the centre = -n x (p - centre)
        return float(np.linalg.norm(a @ q)) < EPS * float(np.linalg.norm(q))

    hint_xy = in_plane(hint) if hint is not None else None
    studs = sorted({in_plane(c.stud) for c in contacts},
                   key=lambda xy: (xy[0] - hint_xy[0]) ** 2 + (xy[1] - hint_xy[1]) ** 2 if hint_xy else 0.0)
    for x, y in studs:
        if turns_freely_about(x, y):
            return TurnPlan("turn", moving, fixed, pivot=centre + bu * x + bv * y, axis=glm.vec3(axis),
                            contacts=contacts, slide=slide)
    return TurnPlan("locked", moving, fixed, reason="the contacts only allow sliding, not turning",
                    axis=glm.vec3(axis), contacts=contacts, slide=slide)


def _slide(null: np.ndarray, bu: glm.vec3, bv: glm.vec3) -> Optional[glm.vec3]:
    """A motion in the null space (rows: angle, x, y) with no turning in it, as a world
    direction; None if every free motion turns."""
    if len(null) == 0:
        return None
    if len(null) == 1:
        q = null[0] if abs(null[0][0]) < EPS else None
    else:  # two free motions: the combination whose angle part cancels
        q = null[1][0] * null[0] - null[0][0] * null[1]
    if q is None or float(np.hypot(q[1], q[2])) < EPS:
        return None
    return glm.normalize(bu * float(q[1]) + bv * float(q[2]))
