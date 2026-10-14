"""Exact part geometry on the sub-grid: bodies, wedge cut planes, per-sub-cell regions and faces.

Everything here works in sub-grid coordinates (integers wherever it matters), so complementary
wedges compare exactly equal. See docs/part_format.md ("Slope occupancy").
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import glm

Int3 = Tuple[int, int, int]
Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class Body:
    """One body of a part, in part cells: a box, or a wedge (a box cut along its diagonal)."""
    kind: str                     # "box" | "wedge"
    lo: Int3                      # min corner cell
    size: Int3                    # cells
    studs: bool                   # flat top carries studs (always False for a lower wedge)
    keep: str = ""                # wedge: "lower" (solid bottom, sloped top) | "upper" (solid top)
    tall_axis: int = 0            # wedge: 0 = x, 1 = y; the slope runs along this axis
    tall_sign: int = 1            # wedge: +1 / -1, the side where the wedge is full height


@dataclass(frozen=True)
class Cut:
    """Half-space side * (a*x + b*y + c*z + d) <= 0, in sub-grid coordinates.
    `plane` is canonical (primitive integer normal, first non-zero normal component positive),
    so two cuts by the same plane have equal `plane`, and complementary ones opposite `side`."""
    plane: Tuple[int, int, int, int]
    side: int

    def value(self, x: float, y: float, z: float) -> float:
        a, b, c, d = self.plane
        return self.side * (a * x + b * y + c * z + d)


def make_cut(a: int, b: int, c: int, d: int, side: int) -> Cut:
    g = math.gcd(math.gcd(abs(a), abs(b)), abs(c))
    a, b, c, d = a // g, b // g, c // g, d // g  # d stays integral: planes pass through grid points
    first = next(v for v in (a, b, c) if v != 0)
    if first < 0:
        a, b, c, d, side = -a, -b, -c, -d, -side
    return Cut((a, b, c, d), side)


def rotate_cut(cut: Cut, turns: int) -> Cut:
    """Rotate about the Z axis through the origin, quarter turns CCW (points (x, y) -> (-y, x))."""
    a, b, c, d = cut.plane
    side = cut.side
    for _ in range(turns % 4):
        a, b = -b, a
    return make_cut(a, b, c, d, side)


def translate_cut(cut: Cut, t: Int3) -> Cut:
    a, b, c, d = cut.plane
    return make_cut(a, b, c, d - (a * t[0] + b * t[1] + c * t[2]), cut.side)


def rotate_sub(x: int, y: int, turns: int) -> Tuple[int, int]:
    """Rotate the sub-cell whose min corner is (x, y), quarter turns CCW about the origin."""
    for _ in range(turns % 4):
        x, y = -y - 1, x
    return x, y


def compatible(a: Optional[Cut], b: Optional[Cut]) -> bool:
    """Can two parts share a sub-cell? Only two partial cuts by the same plane, opposite sides.
    (None = the sub-cell is full.) Conservative: other partial pairs count as overlapping."""
    return a is not None and b is not None and a.plane == b.plane and a.side != b.side


# --- wedge planes ------------------------------------------------------------------------

def _wedge_frame(body: Body, subdiv: Int3):
    """Sub-grid extents of a body: (u0, u1) along the slope axis, (w0, w1) vertical,
    (v0, v1) along the extrusion axis, plus the axis indices (u, v)."""
    u = body.tall_axis
    v = 1 - u
    lo = [body.lo[i] * subdiv[i] for i in range(3)]
    hi = [(body.lo[i] + body.size[i]) * subdiv[i] for i in range(3)]
    return (lo[u], hi[u]), (lo[2], hi[2]), (lo[v], hi[v]), u, v


def _wedge_triangle(body: Body, subdiv: Int3) -> List[Tuple[int, int]]:
    """The wedge's cross-section as (u, w) points."""
    (u0, u1), (w0, w1), _, _, _ = _wedge_frame(body, subdiv)
    tall_u = u1 if body.tall_sign > 0 else u0
    short_u = u0 if body.tall_sign > 0 else u1
    if body.keep == "lower":
        # Solid bottom, full height on the tall side
        return [(short_u, w0), (tall_u, w0), (tall_u, w1)]
    # Solid top: full height on the tall side, thin edge at the top of the short side
    return [(short_u, w1), (tall_u, w1), (tall_u, w0)]


def wedge_cut(body: Body, subdiv: Int3) -> Cut:
    """The half-space a wedge keeps (part sub-grid coordinates, before turning)."""
    (u0, u1), (w0, w1), _, u, _ = _wedge_frame(body, subdiv)
    tri = _wedge_triangle(body, subdiv)
    # The hypotenuse joins the two points that aren't the right-angle corner (the middle one)
    (pu, pw), (ru, rw), (qu, qw) = tri
    # Line through (pu, pw) and (qu, qw): (w - pw) * (qu - pu) - (u - pu) * (qw - pw) = 0
    cu, cw = -(qw - pw), (qu - pu)
    d = -(cu * pu + cw * pw)
    coeffs = [0, 0, 0]
    coeffs[u], coeffs[2] = cu, cw
    # Keep the side containing the right-angle corner
    side = 1 if (cu * ru + cw * rw + d) <= 0 else -1
    return make_cut(coeffs[0], coeffs[1], coeffs[2], d, side)


# --- per-sub-cell regions ----------------------------------------------------------------

_CORNERS = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]


def classify(cut: Cut, sub: Int3) -> str:
    """'full', 'empty' or 'partial': how much of the unit sub-cell at `sub` the cut keeps."""
    values = [cut.value(sub[0] + i, sub[1] + j, sub[2] + k) for i, j, k in _CORNERS]
    if all(v <= 0 for v in values):
        return "full"
    if all(v >= 0 for v in values):
        return "empty"
    return "partial"


def part_regions(bodies: Sequence[Body], subdiv: Int3) -> List[Tuple[Int3, Optional[Cut]]]:
    """Sub-cells a part occupies (part coordinates, before turning) and how: None = full, or the
    Cut that keeps part of it. Overlapping bodies within one part merge (conservatively to full)."""
    regions: Dict[Int3, Optional[Cut]] = {}
    for body in bodies:
        cut = wedge_cut(body, subdiv) if body.kind == "wedge" else None
        lo = [body.lo[i] * subdiv[i] for i in range(3)]
        hi = [(body.lo[i] + body.size[i]) * subdiv[i] for i in range(3)]
        for x in range(lo[0], hi[0]):
            for y in range(lo[1], hi[1]):
                for z in range(lo[2], hi[2]):
                    sub = (x, y, z)
                    region: Optional[Cut] = None
                    if cut is not None:
                        kind = classify(cut, sub)
                        if kind == "empty":
                            continue
                        region = cut if kind == "partial" else None
                    if sub in regions:
                        region = None  # covered twice within the part: treat as full
                    regions[sub] = region
    return list(regions.items())


# --- faces (for rendering and picking) ---------------------------------------------------

Face = List[Vec3]  # convex polygon, counter-clockwise seen from outside


def _newell(poly: Sequence[Vec3]) -> Vec3:
    nx = ny = nz = 0.0
    for i, (x1, y1, z1) in enumerate(poly):
        x2, y2, z2 = poly[(i + 1) % len(poly)]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return nx, ny, nz


def _orient_outward(faces: List[Face]) -> List[Face]:
    pts = [p for f in faces for p in f]
    cx, cy, cz = (sum(p[i] for p in pts) / len(pts) for i in range(3))
    out = []
    for f in faces:
        fx, fy, fz = (sum(p[i] for p in f) / len(f) for i in range(3))
        n = _newell(f)
        out.append(f if n[0] * (fx - cx) + n[1] * (fy - cy) + n[2] * (fz - cz) >= 0 else f[::-1])
    return out


def body_faces(body: Body, subdiv: Int3) -> List[Face]:
    """Faces of a body in part sub-grid coordinates (before turning), oriented outward."""
    if body.kind == "box":
        x0, y0, z0 = (body.lo[i] * subdiv[i] for i in range(3))
        x1, y1, z1 = ((body.lo[i] + body.size[i]) * subdiv[i] for i in range(3))
        faces = [
            [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
            [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],
            [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)],
            [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
            [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
        ]
        return _orient_outward(faces)
    _, _, (v0, v1), u, v = _wedge_frame(body, subdiv)
    tri = _wedge_triangle(body, subdiv)

    def point(uw, vv) -> Vec3:
        p = [0.0, 0.0, 0.0]
        p[u], p[2], p[v] = uw[0], uw[1], vv
        return (p[0], p[1], p[2])
    faces = [[point(t, v0) for t in tri], [point(t, v1) for t in tri]]
    for i in range(3):
        a, b = tri[i], tri[(i + 1) % 3]
        faces.append([point(a, v0), point(b, v0), point(b, v1), point(a, v1)])
    return _orient_outward(faces)


def transform_faces(faces: Sequence[Face], turns: int, pos: Int3, to_world) -> List[List[glm.vec3]]:
    """Turn (quarter turns CCW about the origin), translate by `pos`, map to world space."""
    out = []
    for f in faces:
        poly = []
        for x, y, z in f:
            for _ in range(turns % 4):
                x, y = -y, x
            poly.append(to_world((x + pos[0], y + pos[1], z + pos[2])))
        out.append(poly)
    return out


def face_normal(poly: Sequence[glm.vec3]) -> glm.vec3:
    n = glm.vec3(*_newell([(p.x, p.y, p.z) for p in poly]))
    return glm.normalize(n)


def ray_convex(origin: glm.vec3, direction: glm.vec3, faces: Sequence[Sequence[glm.vec3]]):
    """Ray vs convex solid given by outward faces. Returns (t, entry face normal) or None."""
    t_enter, t_exit = 0.0, math.inf
    enter_normal = None
    for poly in faces:
        n = face_normal(poly)
        denom = glm.dot(n, direction)
        num = glm.dot(n, poly[0] - origin)
        if abs(denom) < 1e-12:
            if num < 0:  # parallel and outside this face
                return None
            continue
        t = num / denom
        if denom < 0:
            if t > t_enter:
                t_enter, enter_normal = t, n
        else:
            t_exit = min(t_exit, t)
        if t_enter > t_exit:
            return None
    if enter_normal is None:
        return None  # ray starts inside
    return t_enter, enter_normal
