"""Exact part geometry on the sub-grid: bodies, wedge cut planes, per-sub-cell regions and faces.

Everything here works in sub-grid coordinates (integers wherever it matters), so complementary
wedges compare exactly equal. See docs/part_format.md ("Occupancy").
"""
import math
from dataclasses import dataclass
from fractions import Fraction
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
    # box: radius of each vertical edge in cells, counter-clockwise from the +x-y corner:
    # (+x-y, +x+y, -x+y, -x-y). 0 = sharp.
    radii: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def rounded(self) -> bool:
        return any(r > 0 for r in self.radii)


@dataclass(frozen=True)
class RoundBody:
    """A sphere or (possibly tapered) cylinder off a part's grid (a joint's ball, arm or cup). Placed in cells, sized in
    mm (a sphere can't be sized in cells that aren't cubes). Not in the occupancy grid: the clash
    test covers it."""
    kind: str                       # "sphere" | "cylinder"
    at: Tuple[float, float, float]  # cells: a point on the face it starts from
    axis: Int3                      # which way it points from there
    offset: float = 0.0             # mm along the axis to where it starts (sphere: its centre)
    length: float = 0.0             # mm, cylinder only
    radius: float = 0.0             # mm (a cylinder's at its start)
    joint: bool = False             # part of a joint: a joined ball and cup may overlap
    end_radius: float = 0.0         # mm, a cylinder's at its far end (0 = the same: no taper)

    @property
    def far_radius(self) -> float:
        return self.end_radius or self.radius


ROUND_SEGMENTS = 16  # around a cylinder or a sphere's equator


def _basis(n):
    """Two unit vectors across `n` (a glm.vec3)."""
    import glm
    ref = glm.vec3(1, 0, 0) if abs(n.x) < 0.9 else glm.vec3(0, 1, 0)
    u = glm.normalize(ref - n * glm.dot(ref, n))
    return u, glm.cross(n, u)


def round_faces(body: RoundBody, base, axis) -> List[list]:
    """Outward faces of a round body starting at world point `base` along unit `axis` (glm)."""
    import glm
    u, v = _basis(axis)
    n_around = ROUND_SEGMENTS
    ring = [u * math.cos(2 * math.pi * i / n_around) + v * math.sin(2 * math.pi * i / n_around)
            for i in range(n_around)]
    if body.kind == "cylinder":
        a = base + axis * body.offset
        b = a + axis * body.length
        lo = [a + r * body.radius for r in ring]
        hi = [b + r * body.far_radius for r in ring]
        faces = [hi, lo[::-1]] + [[lo[i], lo[(i + 1) % n_around], hi[(i + 1) % n_around], hi[i]]
                                  for i in range(n_around)]
        centre = (a + b) * 0.5
    else:
        centre = base + axis * body.offset
        bands = n_around // 2
        rings = []
        for k in range(1, bands):
            t = math.pi * k / bands  # from +axis
            rings.append([centre + (axis * math.cos(t) + r * math.sin(t)) * body.radius for r in ring])
        top, bottom = centre + axis * body.radius, centre - axis * body.radius
        faces = [[top, rings[0][i], rings[0][(i + 1) % n_around]] for i in range(n_around)]
        for k in range(len(rings) - 1):
            faces += [[rings[k][i], rings[k + 1][i], rings[k + 1][(i + 1) % n_around], rings[k][(i + 1) % n_around]]
                      for i in range(n_around)]
        faces += [[bottom, rings[-1][(i + 1) % n_around], rings[-1][i]] for i in range(n_around)]
    out = []
    for f in faces:  # make every face wind outward
        c = sum(f, glm.vec3(0)) / len(f)
        n = glm.cross(f[1] - f[0], f[2] - f[0])
        out.append(f if glm.dot(n, c - centre) >= 0 else f[::-1])
    return out


def round_edges(body: RoundBody, base, axis) -> List[tuple]:
    """Outline of a round body: a cylinder's two end rings (a sphere has none)."""
    if body.kind != "cylinder":
        return []
    u, v = _basis(axis)
    segs = []
    for d, radius in ((body.offset, body.radius), (body.offset + body.length, body.far_radius)):
        c = base + axis * d
        pts = [c + (u * math.cos(2 * math.pi * i / ROUND_SEGMENTS) + v * math.sin(2 * math.pi * i / ROUND_SEGMENTS))
               * radius for i in range(ROUND_SEGMENTS)]
        segs += [(pts[i], pts[(i + 1) % ROUND_SEGMENTS]) for i in range(ROUND_SEGMENTS)]
    return segs


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
                    elif body.rounded and _subcell_outside_rounding(body, sub, subdiv):
                        continue  # outside a rounded corner; sub-cells the curve crosses count as full
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


ARC_SEGMENTS = 8  # per quarter circle, for rounded corners


def _corners(body: Body, scale: Tuple[float, float]):
    """The rounded box's corners, counter-clockwise from +x-y: (centre x, centre y, radius,
    start angle, x sign, y sign), in units of `scale` per cell (sub-cells, or 1 for cells)."""
    x0, y0 = body.lo[0] * scale[0], body.lo[1] * scale[1]
    x1, y1 = (body.lo[0] + body.size[0]) * scale[0], (body.lo[1] + body.size[1]) * scale[1]
    out = []
    for (sx, sy, start), r in zip(((1, -1, -90), (1, 1, 0), (-1, 1, 90), (-1, -1, 180)), body.radii):
        r = r * scale[0]  # subdiv X == Y (checked by the profile)
        cx = (x1 if sx > 0 else x0) - sx * r
        cy = (y1 if sy > 0 else y0) - sy * r
        out.append((cx, cy, r, start, sx, sy))
    return out


def _rounded_footprint(body: Body, subdiv: Int3):
    """Footprint of a rounded box as a convex polygon of (x, y) points (counter-clockwise), and the
    indices of points that get a vertical outline edge: sharp corners, and where a straight side
    meets a rounded corner (but not where two arcs meet smoothly)."""
    # Each corner contributes an arc (its end points flagged "end"), or one "sharp" point
    raw: List[Tuple[Tuple[float, float], str]] = []
    for cx, cy, r, start, _, _ in _corners(body, (subdiv[0], subdiv[1])):
        if r == 0:
            raw.append(((cx, cy), "sharp"))
            continue
        for k in range(ARC_SEGMENTS + 1):
            a = math.radians(start + 90 * k / ARC_SEGMENTS)
            raw.append(((cx + r * math.cos(a), cy + r * math.sin(a)), "end" if k in (0, ARC_SEGMENTS) else "mid"))
    # Merge points that coincide (zero-length straight sides). Two arc ends meeting = smooth.
    points: List[Tuple[float, float]] = []
    kinds: List[List[str]] = []
    for p, kind in raw:
        if points and math.dist(points[-1], p) < 1e-9:
            kinds[-1].append(kind)
        else:
            points.append(p)
            kinds.append([kind])
    if len(points) > 1 and math.dist(points[0], points[-1]) < 1e-9:
        kinds[0] += kinds.pop()
        points.pop()
    lines = [i for i, k in enumerate(kinds) if "sharp" in k or k == ["end"]]
    return points, lines


def outside_rounding(body: Body, x: float, y: float, scale: Tuple[float, float] = (1, 1)) -> bool:
    """Is the point (x, y) cut away by one of the box's rounded corners? (Units: `scale` per cell.)"""
    for cx, cy, r, _, sx, sy in _corners(body, scale):
        if r > 0 and (x - cx) * sx > 0 and (y - cy) * sy > 0 and math.hypot(x - cx, y - cy) > r + 1e-9:
            return True
    return False


def _subcell_outside_rounding(body: Body, sub: Int3, subdiv: Int3) -> bool:
    """Is the whole sub-cell cut away by a rounded corner (it at most touches the curve)?"""
    x, y = sub[0], sub[1]
    for cx, cy, r, _, sx, sy in _corners(body, (subdiv[0], subdiv[1])):
        if r == 0:
            continue
        # Entirely beyond the corner's centre on both axes...
        if not ((x >= cx if sx > 0 else x + 1 <= cx) and (y >= cy if sy > 0 else y + 1 <= cy)):
            continue
        # ...and its nearest point to the centre is on or outside the circle
        nx = x if sx > 0 else x + 1
        ny = y if sy > 0 else y + 1
        if (nx - cx) ** 2 + (ny - cy) ** 2 >= r * r - 1e-9:
            return True
    return False


def body_faces(body: Body, subdiv: Int3) -> List[Face]:
    """Faces of a body in part sub-grid coordinates (before turning), oriented outward."""
    if body.kind == "box" and body.rounded:
        points, _ = _rounded_footprint(body, subdiv)
        z0, z1 = body.lo[2] * subdiv[2], (body.lo[2] + body.size[2]) * subdiv[2]
        faces = [[(x, y, z1) for x, y in points], [(x, y, z0) for x, y in reversed(points)]]
        for i, (xa, ya) in enumerate(points):
            xb, yb = points[(i + 1) % len(points)]
            faces.append([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)])
        return _orient_outward(faces)
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


# --- outline of a whole part (no seams between its bodies) -------------------------------
#
# A part is filled body by body, but its outline has to follow the merged shape: no line where
# two bodies' faces lie in one plane (e.g. a slope's box and wedge side faces), and none around
# faces hidden inside the part. Worked out once per part type, exactly, on the sub-grid:
#   1. split the part into sub-cell pieces (a unit cube, or a cube cut by a wedge plane);
#   2. drop piece faces that the neighbouring piece covers (inside the part);
#   3. per plane, keep only the parts of polygon edges covered by exactly one face (odd count):
#      edges between coplanar faces cancel out, the merged face's boundary remains.

FPoint = Tuple[Fraction, Fraction, Fraction]


def _clip(poly: List[FPoint], cut: Cut) -> List[FPoint]:
    """Sutherland-Hodgman: the part of a convex polygon the cut keeps (value <= 0)."""
    out: List[FPoint] = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        vp, vq = cut.value(*p), cut.value(*q)
        if vp <= 0:
            out.append(p)
        if (vp < 0 < vq) or (vq < 0 < vp):
            t = vp / (vp - vq)
            out.append(tuple(p[k] + (q[k] - p[k]) * t for k in range(3)))
    return out


def _cube_faces(sub: Int3) -> Dict[Tuple[int, int], List[FPoint]]:
    """Faces of the unit cube at `sub`, keyed by (axis, outward sign)."""
    x, y, z = (Fraction(v) for v in sub)
    return {
        (2, -1): [(x, y, z), (x + 1, y, z), (x + 1, y + 1, z), (x, y + 1, z)],
        (2, 1): [(x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)],
        (0, -1): [(x, y, z), (x, y + 1, z), (x, y + 1, z + 1), (x, y, z + 1)],
        (0, 1): [(x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)],
        (1, -1): [(x, y, z), (x + 1, y, z), (x + 1, y, z + 1), (x, y, z + 1)],
        (1, 1): [(x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)],
    }


def _cap(sub: Int3, cut: Cut) -> List[FPoint]:
    """The cut plane's polygon inside the cube at `sub`, in order around its centre."""
    corners = [tuple(Fraction(sub[k] + d[k]) for k in range(3)) for d in _CORNERS]
    pts = {c for c in corners if cut.value(*c) == 0}
    for i, p in enumerate(corners):
        for q in corners[i + 1:]:
            if sum(1 for k in range(3) if p[k] != q[k]) != 1:
                continue  # only cube edges
            vp, vq = cut.value(*p), cut.value(*q)
            if (vp < 0 < vq) or (vq < 0 < vp):
                t = vp / (vp - vq)
                pts.add(tuple(p[k] + (q[k] - p[k]) * t for k in range(3)))
    pts = list(pts)
    if len(pts) < 3:
        return []
    # Sort by angle in the plane (floats only for sorting; the points stay exact)
    n = cut.plane[:3]
    cx, cy, cz = (sum(float(p[k]) for p in pts) / len(pts) for k in range(3))
    helper = [0.0, 0.0, 0.0]
    helper[(next(k for k in range(3) if n[k] != 0) + 1) % 3] = 1.0
    w = (n[1] * helper[2] - n[2] * helper[1], n[2] * helper[0] - n[0] * helper[2],
         n[0] * helper[1] - n[1] * helper[0])
    u = (w[1] * n[2] - w[2] * n[1], w[2] * n[0] - w[0] * n[2], w[0] * n[1] - w[1] * n[0])

    def angle(p):
        d = (float(p[0]) - cx, float(p[1]) - cy, float(p[2]) - cz)
        return math.atan2(sum(d[k] * w[k] for k in range(3)), sum(d[k] * u[k] for k in range(3)))
    return sorted(pts, key=angle)


def _inside(poly: List[FPoint], container: List[FPoint], axis: int) -> bool:
    """Is convex `poly` within convex `container`? Both lie in a plane normal to `axis`."""
    i, j = [k for k in range(3) if k != axis]

    def cross(o, a, b):
        return (a[i] - o[i]) * (b[j] - o[j]) - (a[j] - o[j]) * (b[i] - o[i])
    n = len(container)
    turn = [cross(container[k], container[(k + 1) % n], container[(k + 2) % n]) for k in range(n)]
    signs = {1 if t > 0 else -1 for t in turn if t != 0}
    if len(signs) != 1:
        return False
    s = signs.pop()
    return all(s * cross(container[k], container[(k + 1) % n], p) >= 0 for p in poly for k in range(n))


def _area_positive(poly: List[FPoint]) -> bool:
    if len(poly) < 3:
        return False
    n = _newell([tuple(float(v) for v in p) for p in poly])
    return abs(n[0]) + abs(n[1]) + abs(n[2]) > 1e-12


def _primitive(v: Sequence[Fraction]) -> Int3:
    """Integer direction with no common factor and a canonical sign."""
    den = math.lcm(*(f.denominator for f in v))
    ints = [int(f * den) for f in v]
    g = math.gcd(math.gcd(abs(ints[0]), abs(ints[1])), abs(ints[2]))
    ints = [k // g for k in ints]
    if next(k for k in ints if k != 0) < 0:
        ints = [-k for k in ints]
    return (ints[0], ints[1], ints[2])


def part_outline(bodies: Sequence[Body], subdiv: Int3) -> List[Tuple[Vec3, Vec3]]:
    """Outline segments of a part's merged shape, in part sub-grid coordinates (before turning)."""
    if len(bodies) == 1 and bodies[0].kind == "box" and bodies[0].rounded:
        # A rounded box: top and bottom outlines, plus vertical lines only where a straight side
        # meets a rounded corner (a line per arc segment would just be noise)
        b = bodies[0]
        points, lines = _rounded_footprint(b, subdiv)
        z0, z1 = float(b.lo[2] * subdiv[2]), float((b.lo[2] + b.size[2]) * subdiv[2])
        segs = []
        for z in (z0, z1):
            segs += [((*points[i], z), (*points[(i + 1) % len(points)], z)) for i in range(len(points))]
        segs += [((*points[i], z0), (*points[i], z1)) for i in lines]
        return segs
    if len(bodies) == 1 and bodies[0].kind == "box":
        # Shortcut: a lone box is just its 12 edges (big plates would take seconds otherwise)
        b = bodies[0]
        lo = [float(b.lo[i] * subdiv[i]) for i in range(3)]
        hi = [float((b.lo[i] + b.size[i]) * subdiv[i]) for i in range(3)]
        corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        return [(p, q) for i, p in enumerate(corners) for q in corners[i + 1:]
                if sum(1 for k in range(3) if p[k] != q[k]) == 1]
    regions = dict(part_regions(bodies, subdiv))
    # 1. piece faces
    pieces: Dict[Int3, Dict[object, List[FPoint]]] = {}
    for sub, cut in regions.items():
        faces: Dict[object, List[FPoint]] = {}
        for key, poly in _cube_faces(sub).items():
            if cut is not None:
                poly = _clip(poly, cut)
            if _area_positive(poly):
                faces[key] = poly
        if cut is not None:
            cap = _cap(sub, cut)
            if _area_positive(cap):
                faces["cap"] = cap
        pieces[sub] = faces
    # 2. visible faces, grouped by plane
    groups: Dict[object, List[List[FPoint]]] = {}
    for sub, faces in pieces.items():
        for key, poly in faces.items():
            if key == "cap":
                cut = regions[sub]
                groups.setdefault(("cap", cut.plane, cut.side), []).append(poly)
                continue
            axis, sign = key
            neighbour = list(sub)
            neighbour[axis] += sign
            other = pieces.get(tuple(neighbour), {}).get((axis, -sign))
            if other is not None and _inside(poly, other, axis):
                continue  # covered by the neighbouring piece: inside the part
            groups.setdefault((axis, sign, sub[axis] + (1 if sign > 0 else 0)), []).append(poly)
    # 3. per plane, the edge portions covered an odd number of times
    result: Dict[Tuple[FPoint, FPoint], None] = {}
    for polys in groups.values():
        lines: Dict[object, list] = {}
        for poly in polys:
            for k, p in enumerate(poly):
                q = poly[(k + 1) % len(poly)]
                if p == q:
                    continue
                d = _primitive([q[m] - p[m] for m in range(3)])
                # All points of a line share cross(d, p); dot(d, p) is the position along it
                key = (d, (d[1] * p[2] - d[2] * p[1], d[2] * p[0] - d[0] * p[2], d[0] * p[1] - d[1] * p[0]))
                tp = sum(d[m] * p[m] for m in range(3))
                tq = sum(d[m] * q[m] for m in range(3))
                lines.setdefault(key, []).append((min(tp, tq), max(tp, tq), p))
        for (d, _), spans in lines.items():
            ts = sorted({t for a, b, _ in spans for t in (a, b)})
            start = end = None
            for t0, t1 in zip(ts, ts[1:]):
                if sum(1 for a, b, _ in spans if a <= t0 and t1 <= b) % 2 == 1:
                    start = t0 if start is None else start
                    end = t1
                elif start is not None:
                    result[_segment(spans[0][2], d, start, end)] = None
                    start = None
            if start is not None:
                result[_segment(spans[0][2], d, start, end)] = None
    return [(tuple(float(v) for v in a), tuple(float(v) for v in b)) for a, b in result]


def _segment(p: FPoint, d: Int3, t0: Fraction, t1: Fraction) -> Tuple[FPoint, FPoint]:
    """The points at positions t0 and t1 along the line through p with direction d."""
    norm2 = sum(c * c for c in d)
    tp = sum(d[m] * p[m] for m in range(3))
    a, b = (tuple(p[m] + d[m] * (t - tp) / norm2 for m in range(3)) for t in (t0, t1))
    return (a, b) if a <= b else (b, a)


def transform_segments(segments, turns: int, pos: Int3, to_world) -> List[Tuple[glm.vec3, glm.vec3]]:
    """Like transform_faces, for outline segments."""
    out = []
    for seg in segments:
        ends = []
        for x, y, z in seg:
            for _ in range(turns % 4):
                x, y = -y, x
            ends.append(to_world((x + pos[0], y + pos[1], z + pos[2])))
        out.append((ends[0], ends[1]))
    return out
