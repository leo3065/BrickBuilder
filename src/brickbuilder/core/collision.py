"""The clash test: do two parts get in each other's way (see docs/turning.md).

On one grid the sub-cell occupancy decides overlap exactly when placing. Across grids, and for
anything moved or turned, the world-space solids are compared instead. Every body is convex
(boxes, rounded boxes, wedges), so two bodies are apart iff some axis separates them: a face
normal of either, or the cross product of an edge direction from each. Studs are checked too:
they may only go into another part's body through one of its slots (undersides are hollow along
them, so a stud whose base is lower than the slot just goes in less deep).
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import glm
import numpy as np

from brickbuilder.core.connections import AXIS_TOLERANCE, TOLERANCE, on_slot

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
    studs: List[Tuple[glm.vec3, glm.vec3, Hull]]  # stud base, its axis and its prism
    slots: List[Tuple[glm.vec3, glm.vec3, glm.vec3]]  # antistud slots (world): ends and stud axis
    box: Tuple[glm.vec3, glm.vec3]                # around bodies and studs
    joint_hulls: Tuple[bool, ...] = ()            # per hull: part of a joint (ball, arm, cup)
    joints: Tuple = ()                            # (kind, pivot, axis, slot) per joint socket
    hollows: Tuple = ()                           # (corner, side end, other side end, axis): studs fit, no grip


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


def make_shape(solids, studs, stud_axes, slots, slot_axes, stud_radius: float, stud_height: float,
               joint_solids=(), joints=(), hollows=()) -> Shape:
    stud_hulls = [(s, axis, stud_hull(s, axis, stud_radius, stud_height)) for s, axis in zip(studs, stud_axes)]
    lo, hi = solids_box(solids)
    for s, axis in zip(studs, stud_axes):
        for p in (s, s + axis * stud_height):  # widened by the radius in every direction: a bound
            lo = glm.vec3(min(lo.x, p.x - stud_radius), min(lo.y, p.y - stud_radius), min(lo.z, p.z - stud_radius))
            hi = glm.vec3(max(hi.x, p.x + stud_radius), max(hi.y, p.y + stud_radius), max(hi.z, p.z + stud_radius))
    flags = tuple(joint_solids) + (False,) * (len(solids) - len(joint_solids))
    return Shape([hull(s) for s in solids], stud_hulls,
                 [(a, b, axis) for (a, b), axis in zip(slots, slot_axes)], (lo, hi), flags, tuple(joints),
                 tuple(hollows))


def _move_hull(h: Hull, rot: np.ndarray, shift: np.ndarray) -> Hull:
    verts, normals, edges = h
    return verts @ rot + shift, normals @ rot, edges @ rot


def transform_shape(s: Shape, m: glm.mat4) -> Shape:
    """A shape moved by a rigid transform: the hulls' vertices, normals and edge directions are just
    rotated and shifted, so nothing is rebuilt (building hulls is the slow part)."""
    r3 = glm.mat3(m)
    rot = np.array([[r3[i][j] for j in range(3)] for i in range(3)])  # rows = columns of r3: v @ rot = r3 * v
    shift = np.array([m[3][0], m[3][1], m[3][2]])

    def pt(p):
        return glm.vec3(m * glm.vec4(p, 1.0))
    hulls = [_move_hull(h, rot, shift) for h in s.hulls]
    studs = [(pt(b), r3 * a, _move_hull(h, rot, shift)) for b, a, h in s.studs]
    verts = [h[0] for h in hulls] + [h[0] for _, _, h in studs]
    allv = np.vstack(verts)
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    return Shape(hulls, studs, [(pt(a), pt(b), r3 * n) for a, b, n in s.slots],
                 (glm.vec3(*map(float, lo)), glm.vec3(*map(float, hi))), s.joint_hulls,
                 tuple((k, pt(p), r3 * a, r3 * sl) for k, p, a, sl in s.joints),
                 tuple((pt(p0), pt(p1), pt(p2), r3 * n) for p0, p1, p2, n in s.hollows))


def _joined(a: Shape, b: Shape) -> bool:
    """A ball of one on a cup of the other (centres together): their joint bodies may overlap."""
    for x, y in ((a, b), (b, a)):
        for kind, point, _, _ in x.joints:
            if kind == "ball" and any(k == "cup" and glm.distance(point, p) <= TOLERANCE for k, p, _, _ in y.joints):
                return True
    return False


def _bodies_overlap(a: Shape, b: Shape) -> bool:
    skip = _joined(a, b)
    for i, x in enumerate(a.hulls):
        for j, y in enumerate(b.hulls):
            if skip and a.joint_hulls[i] and b.joint_hulls[j]:
                continue
            if overlap(x, y):
                return True
    return False


def clash(a: Shape, b: Shape) -> Optional[str]:
    """How two parts get in each other's way, or None: "bodies" overlapping, or a "stud" of one
    inside the other's body other than in one of its slots."""
    if not boxes_overlap(a.box, b.box):
        return None
    if _bodies_overlap(a, b):
        return "bodies"
    for x, y in ((a, b), (b, a)):
        for base, axis, h in x.studs:
            if hulls_overlap([h], y.hulls) and not any(in_slot(base, axis, slot) for slot in y.slots) \
                    and not any(in_hollow(base, axis, area) for area in y.hollows):
                return "stud"
    return None


def in_hollow(base: glm.vec3, axis: glm.vec3, area) -> bool:
    """Does a stud go into a hollow (a base plate's open middle): pointing the hollow's way, its
    base on or below the hollow's plane, its centre line inside the rectangle."""
    p0, p1, p2, n = area
    if glm.dot(axis, n) <= 1 - AXIS_TOLERANCE:
        return False
    t = glm.dot(base - p0, n)
    if t > TOLERANCE:
        return False
    q = base - n * t - p0
    for edge in (p1 - p0, p2 - p0):
        length2 = glm.dot(edge, edge)
        s = glm.dot(q, edge) / length2 if length2 > 0 else 0.0
        if s < -TOLERANCE or s > 1 + TOLERANCE:
            return False
    return True


def blocking_studs(a: Shape, b: Shape) -> List[Tuple[glm.vec3, glm.vec3]]:
    """The studs (base, axis) of either shape that are inside the other's body outside its slots."""
    if not boxes_overlap(a.box, b.box):
        return []
    return [(base, axis) for x, y in ((a, b), (b, a)) for base, axis, h in x.studs
            if hulls_overlap([h], y.hulls) and not any(in_slot(base, axis, slot) for slot in y.slots)
            and not any(in_hollow(base, axis, area) for area in y.hollows)]


def in_slot(base: glm.vec3, axis: glm.vec3, slot) -> bool:
    """Does a stud go into a slot's hollow: pointing the slot's way, its centre line through the
    slot, and its base on or below the slot's plane (a lower stud just goes in less deep; a higher
    one would push into the part's ceiling)."""
    s0, s1, slot_axis = slot
    if glm.dot(axis, slot_axis) <= 1 - AXIS_TOLERANCE:
        return False
    t = glm.dot(base - s0, slot_axis)  # how far the base is above the slot's plane
    if t > TOLERANCE:
        return False
    return on_slot(base - slot_axis * t, s0, s1)
