"""What a turn moves and how it may turn (step B: turning about Z).

Moving set: the selection always moves, plus whatever hangs only off it; the rest of its connected
component stays if it's pinned (grounded: a part on the root grid's layer 0), otherwise the
largest piece of the rest stays (docs/part_format.md, "Pins").

Free motion: the contacts between the moving and the staying parts, linearised. Each stud in a
slot is an error that must stay zero (the stud's distance from the slot's line; both directions
for a point antistud). The moving set's motion is (angle, x, y); the motions that keep every
error at zero are the null space of the errors' Jacobian. A turn about a contact stud that's in
that null space is the turn the tool offers (it keeps the contact exactly, not just to first
order). No null space with a turn in it: locked.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Set

import glm
import numpy as np

from brickbuilder.core.connections import Contact, contacts_between

RANK_TOL = 1e-6


@dataclass
class TurnPlan:
    kind: str                       # "free" (not held), "turn" (about pivot) or "locked"
    moving: Set[int]
    fixed: Set[int] = field(default_factory=set)
    pivot: Optional[glm.vec3] = None  # a point on the vertical axis to turn about ("turn")
    reason: str = ""
    contacts: List[Contact] = field(default_factory=list)


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


def _jacobian_rows(contact: Contact, centre: glm.vec3) -> List[List[float]]:
    """Rows d(error)/d(angle, x, y) for one contact, turning about `centre`. The stud and the
    slot move relative to each other, so it doesn't matter which one is on the moving side."""
    r = contact.stud - centre
    j = np.array([[-r.y, 1.0, 0.0],   # d(stud.x)
                  [r.x, 0.0, 1.0]])   # d(stud.y)
    a, b = contact.slot
    u = glm.vec2(b.x - a.x, b.y - a.y)
    if glm.length(u) < 1e-9:
        return j.tolist()             # a point antistud: both directions
    u = glm.normalize(u)
    n = np.array([-u.y, u.x])         # across the slot
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
    centre = contacts[0].stud
    a = np.array([row for c in contacts for row in _jacobian_rows(c, centre)])
    s = np.linalg.svd(a, compute_uv=False)
    rank = int(np.sum(s > RANK_TOL * max(1.0, s[0])))
    if rank >= 3:
        return TurnPlan("locked", moving, fixed, reason="held by studs on different axes", contacts=contacts)

    def turns_freely_about(p: glm.vec3) -> bool:
        r = p - centre
        q = np.array([1.0, r.y, -r.x])  # turning about p: velocity at the centre = -ez x (p - centre)
        return float(np.linalg.norm(a @ q)) < 1e-6 * max(1.0, float(np.linalg.norm(q)))

    studs = sorted({(round(c.stud.x, 4), round(c.stud.y, 4)) for c in contacts},
                   key=lambda xy: (xy[0] - hint.x) ** 2 + (xy[1] - hint.y) ** 2 if hint else 0.0)
    for x, y in studs:
        p = glm.vec3(x, y, centre.z)
        if turns_freely_about(p):
            return TurnPlan("turn", moving, fixed, pivot=p, contacts=contacts)
    return TurnPlan("locked", moving, fixed, reason="the contacts only allow sliding, not turning",
                    contacts=contacts)
