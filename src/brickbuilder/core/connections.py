"""Which parts are connected: a stud of one sitting in an antistud slot of another.

On a single grid this is fully determined by where the parts are, so it's worked out on demand
rather than stored (see docs/part_format.md). Studs are bucketed by height and cell column, so
each slot only looks at the studs right around it.
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


def on_slot(p: glm.vec3, a: glm.vec3, b: glm.vec3, tolerance: float = TOLERANCE) -> bool:
    """Is point `p` on the slot from `a` to `b` (a point slot when a == b)?"""
    ab = b - a
    length2 = glm.dot(ab, ab)
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, glm.dot(p - a, ab) / length2))
    return glm.distance(p, a + ab * t) <= tolerance


def _bucket_z(z: float) -> int:
    return round(z / TOLERANCE)


def iter_contacts(profile: Profile, stud_parts: Iterable, slot_parts: Iterable) -> Iterator[Contact]:
    """Every stud of `stud_parts` sitting in a slot of a different part in `slot_parts`."""
    cx, cy = profile.cell.x, profile.cell.y
    buckets: Dict[Tuple[int, int, int], List[Tuple[glm.vec3, int]]] = defaultdict(list)
    for placed in stud_parts:
        for s in placed.studs:
            buckets[(_bucket_z(s.z), math.floor(s.x / cx), math.floor(s.y / cy))].append((s, placed.id))
    for placed in slot_parts:
        for a, b in placed.antistuds:
            z = _bucket_z(a.z)
            # Cell columns the slot passes over (a stud on a column boundary sits in either)
            x0, x1 = math.floor((min(a.x, b.x) - TOLERANCE) / cx), math.floor((max(a.x, b.x) + TOLERANCE) / cx)
            y0, y1 = math.floor((min(a.y, b.y) - TOLERANCE) / cy), math.floor((max(a.y, b.y) + TOLERANCE) / cy)
            for zz in (z - 1, z, z + 1):  # float noise can put a height just across a bucket edge
                for i in range(x0, x1 + 1):
                    for j in range(y0, y1 + 1):
                        for stud, other in buckets.get((zz, i, j), ()):
                            if other != placed.id and abs(stud.z - a.z) <= TOLERANCE and on_slot(stud, a, b):
                                yield Contact(stud, (a, b), other, placed.id)


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
