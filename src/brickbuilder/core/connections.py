"""Which parts are connected: a stud of one sitting in an antistud slot of another.

It's fully determined by where the parts are, so it's worked out on demand rather than stored
(see docs/part_format.md). Positions are world space, so it works across frames; a stud must be
on the slot and point the way the slot expects (side studs, tilted frames). Studs are bucketed by
cell-sized world boxes, so each slot only looks at the studs right around it.
"""
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Set, Tuple

import glm

from brickbuilder.core.profile import Profile

TOLERANCE = 1e-3  # mm: a stud "is in" a slot if its centre is this close to the slot's line


@dataclass(frozen=True)
class Contact:
    stud: glm.vec3                   # world position of the stud's base
    slot: Tuple[glm.vec3, glm.vec3]  # the antistud slot it's in (a == b for a point)
    stud_part: int
    slot_part: int
    axis: glm.vec3 = glm.vec3(0, 0, 1)  # which way the stud points (world)

AXIS_TOLERANCE = 1e-4  # 1 - cos(angle) between a stud's axis and its slot's: about 0.8 degrees


def on_slot(p: glm.vec3, a: glm.vec3, b: glm.vec3, tolerance: float = TOLERANCE) -> bool:
    """Is point `p` on the slot from `a` to `b` (a point slot when a == b)?"""
    ab = b - a
    length2 = glm.dot(ab, ab)
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, glm.dot(p - a, ab) / length2))
    return glm.distance(p, a + ab * t) <= tolerance


def iter_contacts(profile: Profile, stud_parts: Iterable, slot_parts: Iterable) -> Iterator[Contact]:
    """Every stud of `stud_parts` sitting in a slot of a different part in `slot_parts`, pointing
    the way the slot expects. A stud holds if at least half its height is in: its base on the
    slot's plane or up to half a stud height below it (undersides are hollow along slots)."""
    size = profile.cell.x
    sink = profile.stud.height / 2  # how far below the slot's plane a stud's base may be
    buckets: Dict[Tuple[int, int, int], List[Tuple[glm.vec3, glm.vec3, int]]] = defaultdict(list)
    for placed in stud_parts:
        for s, axis in zip(placed.studs, placed.stud_axes):
            buckets[(math.floor(s.x / size), math.floor(s.y / size), math.floor(s.z / size))].append(
                (s, axis, placed.id))
    for placed in slot_parts:
        for (a, b), slot_axis in zip(placed.antistuds, placed.antistud_axes):
            # Buckets the slot passes through (a stud on a bucket edge sits in either)
            lo = [math.floor((min(a[k], b[k]) - TOLERANCE - sink) / size) for k in range(3)]
            hi = [math.floor((max(a[k], b[k]) + TOLERANCE + sink) / size) for k in range(3)]
            for i in range(lo[0], hi[0] + 1):
                for j in range(lo[1], hi[1] + 1):
                    for k in range(lo[2], hi[2] + 1):
                        for stud, axis, other in buckets.get((i, j, k), ()):
                            if other == placed.id or glm.dot(axis, slot_axis) <= 1 - AXIS_TOLERANCE:
                                continue
                            t = glm.dot(stud - a, slot_axis)  # base above (+) or below (-) the slot's plane
                            if -sink - TOLERANCE <= t <= TOLERANCE and on_slot(stud - slot_axis * t, a, b):
                                yield Contact(stud, (a, b), other, placed.id, axis)


@dataclass(frozen=True)
class JointContact:
    pivot: glm.vec3      # world position of the ball's centre (= the cup's pivot)
    ball_part: int
    cup_part: int
    ball_axis: glm.vec3  # the ball's arm direction (world)
    cup_axis: glm.vec3   # out of the cup
    cup_slot: glm.vec3   # the way the cup's slot opens


def joint_limits(profile: Profile) -> Tuple[float, float]:
    """(cone, slot) in degrees for a cup, from the profile's socket types."""
    cup = profile.socket_types.get("cup", {})
    return float(cup.get("cone", 0.0)), float(cup.get("slot", 0.0))


def within_limits(ball_axis: glm.vec3, cup_axis: glm.vec3, cup_slot: glm.vec3, cone: float, slot: float) -> bool:
    """Is the arm direction allowed: within the cone of straight (the arm pointing into the cup),
    or in the slot's plane within the slot's range."""
    straight = -glm.normalize(cup_axis)
    d = glm.normalize(ball_axis)
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, glm.dot(d, straight)))))
    if tilt <= cone + 1e-3:
        return True
    across = glm.normalize(glm.cross(cup_axis, cup_slot))  # out of the slot's plane
    return abs(glm.dot(d, across)) < 1e-3 and tilt <= slot + 1e-3


def joint_contacts(profile: Profile, parts_a: Iterable, parts_b: Iterable) -> List[JointContact]:
    """Balls of one set sitting in cups of the other (either way round): centre on the pivot and
    the arm within the cup's limits."""
    cone, slot = joint_limits(profile)
    a, b = list(parts_a), list(parts_b)
    out = []
    for xs, ys in ((a, b), (b, a)):
        for p in xs:
            for kind, point, axis, _ in getattr(p, "joints", ()):
                if kind != "ball":
                    continue
                for q in ys:
                    if q.id == p.id:
                        continue
                    for kind2, point2, axis2, slot2 in getattr(q, "joints", ()):
                        if kind2 == "cup" and glm.distance(point, point2) <= TOLERANCE \
                                and within_limits(axis, axis2, slot2, cone, slot):
                            out.append(JointContact(point, p.id, q.id, axis, axis2, slot2))
    return out


def find_connections(profile: Profile, parts: Iterable) -> Dict[int, Set[int]]:
    parts = list(parts)
    links: Dict[int, Set[int]] = {placed.id: set() for placed in parts}
    for c in iter_contacts(profile, parts, parts):
        links[c.slot_part].add(c.stud_part)
        links[c.stud_part].add(c.slot_part)
    jointed = [p for p in parts if getattr(p, "joints", ())]
    for j in joint_contacts(profile, jointed, jointed):
        links[j.ball_part].add(j.cup_part)
        links[j.cup_part].add(j.ball_part)
    return links


def contacts_between(profile: Profile, a: Iterable, b: Iterable) -> List[Contact]:
    """Contacts between two sets of parts, either way round."""
    a, b = list(a), list(b)
    return list(iter_contacts(profile, a, b)) + list(iter_contacts(profile, b, a))


def groups(links: Dict[int, Set[int]]) -> List[Set[int]]:
    """Connected groups of parts, largest first."""
    seen: Set[int] = set()
    out: List[Set[int]] = []
    for start in links:
        if start in seen:
            continue
        group, todo = set(), [start]
        while todo:
            pid = todo.pop()
            if pid in group:
                continue
            group.add(pid)
            todo.extend(links[pid] - group)
        seen |= group
        out.append(group)
    out.sort(key=len, reverse=True)
    return out
