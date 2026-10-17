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
    the way the slot expects."""
    size = profile.cell.x
    buckets: Dict[Tuple[int, int, int], List[Tuple[glm.vec3, glm.vec3, int]]] = defaultdict(list)
    for placed in stud_parts:
        for s, axis in zip(placed.studs, placed.stud_axes):
            buckets[(math.floor(s.x / size), math.floor(s.y / size), math.floor(s.z / size))].append(
                (s, axis, placed.id))
    for placed in slot_parts:
        for (a, b), slot_axis in zip(placed.antistuds, placed.antistud_axes):
            # Buckets the slot passes through (a stud on a bucket edge sits in either)
            lo = [math.floor((min(a[k], b[k]) - TOLERANCE) / size) for k in range(3)]
            hi = [math.floor((max(a[k], b[k]) + TOLERANCE) / size) for k in range(3)]
            for i in range(lo[0], hi[0] + 1):
                for j in range(lo[1], hi[1] + 1):
                    for k in range(lo[2], hi[2] + 1):
                        for stud, axis, other in buckets.get((i, j, k), ()):
                            if other != placed.id and glm.dot(axis, slot_axis) > 1 - AXIS_TOLERANCE \
                                    and on_slot(stud, a, b):
                                yield Contact(stud, (a, b), other, placed.id, axis)


def find_connections(profile: Profile, parts: Iterable) -> Dict[int, Set[int]]:
    parts = list(parts)
    links: Dict[int, Set[int]] = {placed.id: set() for placed in parts}
    for c in iter_contacts(profile, parts, parts):
        links[c.slot_part].add(c.stud_part)
        links[c.stud_part].add(c.slot_part)
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
