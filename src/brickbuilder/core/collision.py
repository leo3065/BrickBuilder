"""The clash test: do two parts get in each other's way (see docs/turning.md).

On one grid the sub-cell occupancy decides overlap exactly when placing. Across grids, and for
anything moved or turned, the world-space solids are compared instead. Every body is convex
(boxes, rounded boxes, wedges), so two bodies are apart iff some axis separates them: a face
normal of either, or the cross product of an edge direction from each. Studs are checked too:
they may only go into another part's body on one of its slots.
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import glm
import numpy as np

from brickbuilder.core.connections import on_slot

# mm: two solids overlapping by less than this along some axis only touch (faces in contact, the
# round ends of a stud hinge, float noise from turned frames)
PENETRATION = 0.05

Hull = Tuple[np.ndarray, np.ndarray, np.ndarray]  # vertices (n, 3), face normals (m, 3), edge directions (k, 3)


def _unique_directions(dirs: np.ndarray) -> np.ndarray:
    """Unit directions with opposite and repeated ones merged."""
    if len(dirs) == 0:
        return dirs.reshape(0, 3)
    dirs = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    # Point each one into the same half-space so d and -d coincide
    first = np.argmax(np.abs(dirs) > 1e-9, axis=1)
    sign = np.sign(dirs[np.arange(len(dirs)), first])
    dirs = dirs * sign[:, None]
    _, keep = np.unique(np.round(dirs, 6), axis=0, return_index=True)
    return dirs[np.sort(keep)]


def hull(solid: Sequence[Sequence[glm.vec3]]) -> Hull:
    """Precompute what the separating axis test needs from a convex solid (outward faces)."""
    verts, normals, edges = [], [], []
    for face in solid:
        pts = np.array([(p.x, p.y, p.z) for p in face], dtype=float)
        verts.append(pts)
        nxt = np.roll(pts, -1, axis=0)
        # Newell's method: robust for any planar polygon
        n = np.array([np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2])),
                      np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0])),
                      np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1]))])
        if np.linalg.norm(n) > 1e-12:
            normals.append(n)
        e = nxt - pts
        edges.append(e[np.linalg.norm(e, axis=1) > 1e-9])
    v = np.unique(np.round(np.vstack(verts), 9), axis=0)
    return v, _unique_directions(np.array(normals)), _unique_directions(np.vstack(edges))


def overlap(a: Hull, b: Hull, penetration: float = PENETRATION) -> bool:
    """True if two convex solids overlap by more than `penetration` along every axis."""
    va, na, ea = a
    vb, nb, eb = b
    cross = np.cross(ea[:, None, :], eb[None, :, :]).reshape(-1, 3)
    length = np.linalg.norm(cross, axis=1)
    cross = cross[length > 1e-6] / length[length > 1e-6, None]
    axes = np.vstack([na, nb, cross])
    pa, pb = va @ axes.T, vb @ axes.T
    depth = np.minimum(pa.max(0), pb.max(0)) - np.maximum(pa.min(0), pb.min(0))
    return bool(np.all(depth > penetration))


def boxes_overlap(a: Tuple[glm.vec3, glm.vec3], b: Tuple[glm.vec3, glm.vec3],
                  penetration: float = PENETRATION) -> bool:
    return all(min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]) > penetration for i in range(3))


def solids_box(solids) -> Tuple[glm.vec3, glm.vec3]:
    pts = [p for solid in solids for face in solid for p in face]
    return (glm.vec3(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            glm.vec3(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))


def hulls_overlap(a: List[Hull], b: List[Hull], penetration: float = PENETRATION) -> bool:
    return any(overlap(x, y, penetration) for x in a for y in b)


# --- whole parts: bodies plus studs -------------------------------------------------------
#
# Bodies are solid here, though real undersides are hollow: a stud may go into another part's
# body only where that part has an antistud slot for it. Anywhere else (e.g. a part turned on a
# brick with several studs, the others poking into it) the stud blocks.

STUD_SIDES = 8


@dataclass
class Shape:
    hulls: List[Hull]                            # the bodies
    studs: List[Tuple[glm.vec3, Hull]]           # stud base and its prism
    slots: Tuple[Tuple[glm.vec3, glm.vec3], ...]  # antistud slots (world)
    box: Tuple[glm.vec3, glm.vec3]               # around bodies and studs


def stud_hull(base: glm.vec3, axis: glm.vec3, radius: float, height: float) -> Hull:
    """A stud as an octagonal prism standing on `base` along `axis`."""
    axis = glm.normalize(axis)
    u = glm.normalize(glm.cross(axis, glm.vec3(1, 0, 0) if abs(axis.x) < 0.9 else glm.vec3(0, 1, 0)))
    v = glm.cross(axis, u)
    ring = [u * math.cos(2 * math.pi * i / STUD_SIDES) + v * math.sin(2 * math.pi * i / STUD_SIDES)
            for i in range(STUD_SIDES)]
    bottom = [base + radius * r for r in ring]
    top = [p + axis * height for p in bottom]
    faces = [top, bottom[::-1]] + [[bottom[i], bottom[(i + 1) % STUD_SIDES], top[(i + 1) % STUD_SIDES], top[i]]
                                   for i in range(STUD_SIDES)]
    return hull(faces)


def make_shape(solids, studs, slots, stud_radius: float, stud_height: float,
               up: glm.vec3 = glm.vec3(0, 0, 1)) -> Shape:
    stud_hulls = [(s, stud_hull(s, up, stud_radius, stud_height)) for s in studs]
    lo, hi = solids_box(solids)
    for s in studs:
        top = s + up * stud_height
        for p in (s, top):
            lo = glm.vec3(min(lo.x, p.x - stud_radius), min(lo.y, p.y - stud_radius), min(lo.z, p.z))
            hi = glm.vec3(max(hi.x, p.x + stud_radius), max(hi.y, p.y + stud_radius), max(hi.z, p.z))
    return Shape([hull(s) for s in solids], stud_hulls, tuple(slots), (lo, hi))


def clash(a: Shape, b: Shape) -> Optional[str]:
    """How two parts get in each other's way, or None: "bodies" overlapping, or a "stud" of one
    inside the other's body other than in one of its slots."""
    if not boxes_overlap(a.box, b.box):
        return None
    if hulls_overlap(a.hulls, b.hulls):
        return "bodies"
    for x, y in ((a, b), (b, a)):
        for base, h in x.studs:
            if hulls_overlap([h], y.hulls) and not any(on_slot(base, s0, s1) for s0, s1 in y.slots):
                return "stud"
    return None
