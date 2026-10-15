"""Which parts are connected: a stud of one sitting in an antistud slot of another.

On a single grid this is fully determined by where the parts are, so it's worked out on demand
rather than stored (see docs/part_format.md). Studs are bucketed by height and cell column, so
each slot only looks at the studs right around it.
"""
import math
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

import glm

from brickbuilder.core.profile import Profile

TOLERANCE = 1e-4  # mm: a stud "is in" a slot if its centre is this close to the slot's line


def _on_segment(p: glm.vec3, a: glm.vec3, b: glm.vec3) -> bool:
    ab = b - a
    length2 = glm.dot(ab, ab)
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, glm.dot(p - a, ab) / length2))
    return glm.distance(p, a + ab * t) <= TOLERANCE


def find_connections(profile: Profile, parts: Iterable) -> Dict[int, Set[int]]:
    parts = list(parts)
    cx, cy = profile.cell.x, profile.cell.y
    buckets: Dict[Tuple[int, int, int], List[Tuple[glm.vec3, int]]] = defaultdict(list)
    for placed in parts:
        for s in placed.studs:
            buckets[(round(s.z / TOLERANCE), math.floor(s.x / cx), math.floor(s.y / cy))].append((s, placed.id))
    links: Dict[int, Set[int]] = {placed.id: set() for placed in parts}
    for placed in parts:
        for a, b in placed.antistuds:
            z = round(a.z / TOLERANCE)
            # Cell columns the slot passes over (a stud on a column boundary sits in either)
            x0, x1 = math.floor((min(a.x, b.x) - TOLERANCE) / cx), math.floor((max(a.x, b.x) + TOLERANCE) / cx)
            y0, y1 = math.floor((min(a.y, b.y) - TOLERANCE) / cy), math.floor((max(a.y, b.y) + TOLERANCE) / cy)
            for i in range(x0, x1 + 1):
                for j in range(y0, y1 + 1):
                    for stud, other in buckets.get((z, i, j), ()):
                        if other != placed.id and _on_segment(stud, a, b):
                            links[placed.id].add(other)
                            links[other].add(placed.id)
    return links


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
