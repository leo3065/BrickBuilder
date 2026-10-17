"""Placed parts, sub-cell occupancy and the save format (see docs/part_format.md)."""
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import json
import math
import os
import glm
from brickbuilder.core import collision
from brickbuilder.core.geometry import (Cut, body_faces, compatible, part_outline, part_regions, round_edges, round_faces,
                                        rotate_cut, rotate_sub, transform_faces, transform_segments,
                                        translate_cut)
from brickbuilder.core.parts import PartDef
from brickbuilder.core.profile import Profile

Sub = Tuple[int, int, int]  # sub-grid coordinate (profile.subdiv sub-cells per cell)
Region = Tuple[Sub, Optional[Cut]]  # a sub-cell and how it's filled: None = full, or a wedge cut
Solid = List[List[glm.vec3]]  # convex body as outward faces (world space)

SAVE_VERSION = 4  # v3: frames with parent, origin and rotation; v4: groups



class ModelError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    """A grid of its own: parts in it are placed on its sub-grid like on the root grid, then moved
    by the frame's transform. Frame 0 is the root (the global grid)."""
    id: int
    parent: Optional[int]                  # None only for the root
    origin: glm.vec3 = glm.vec3(0.0)       # in the parent's space, mm
    rotation: glm.quat = glm.quat()        # relative to the parent

    def local_matrix(self) -> glm.mat4:
        return glm.translate(glm.mat4(1.0), self.origin) * glm.mat4_cast(self.rotation)


ROOT = Frame(0, None)


@dataclass
class Group:
    """A named subassembly the user made: holds parts (PlacedPart.group) and child groups."""
    id: int
    name: str
    parent: Optional[int] = None


@dataclass
class PlacedPart:
    id: int
    part: PartDef
    pos: Sub                # sub-grid position of the part origin (min corner, bottom)
    turns: int              # quarter turns about +Z through the origin, 0..3
    color: str              # palette id
    frame: int              # frame id; 0 = the root grid. pos/turns/regions are in its grid
    regions: Tuple[Region, ...]     # sub-cells it occupies (fully, or partly for wedges)
    box: Tuple[glm.vec3, glm.vec3]  # world AABB
    solids: Tuple[Solid, ...]       # world-space bodies, for rendering and picking
    edges: Tuple[Tuple[glm.vec3, glm.vec3], ...]  # outline of the merged shape (no seams)
    studs: Tuple[glm.vec3, ...]     # world positions of stud bases (centre of the stud's bottom)
    antistuds: Tuple[Tuple[glm.vec3, glm.vec3], ...] = ()  # world slots where a stud fits
    stud_axes: Tuple[glm.vec3, ...] = ()      # world direction each stud points
    antistud_axes: Tuple[glm.vec3, ...] = ()  # world direction a stud in each slot points
    joint_solids: Tuple[bool, ...] = ()       # per solid: part of a joint (ball, arm, cup)
    joints: Tuple = ()                        # (kind, world pivot, axis, slot) per ball / cup socket
    hollows: Tuple = ()                       # (corner, side end, other side end, axis) per hollow
    group: Optional[int] = None    # the innermost group it belongs to, if any


# Rotating a cell's min corner is the same as rotating a sub-cell's (the origin is a corner)
rotate_cell = rotate_sub

# Per (part, subdiv, turns): regions relative to the part origin. Parts are immutable, so cache.
_REGION_CACHE: Dict[Tuple[PartDef, Tuple[int, int, int], int], List[Region]] = {}
_FACE_CACHE: Dict[Tuple[PartDef, Tuple[int, int, int]], List[list]] = {}
_OUTLINE_CACHE: Dict[Tuple[PartDef, Tuple[int, int, int]], list] = {}


def _turned_regions(profile: Profile, part: PartDef, turns: int) -> List[Region]:
    key = (part, profile.subdiv, turns % 4)
    if key not in _REGION_CACHE:
        out = []
        for (x, y, z), cut in part_regions(part.bodies, profile.subdiv):
            rx, ry = rotate_sub(x, y, turns)
            out.append(((rx, ry, z), rotate_cut(cut, turns) if cut else None))
        _REGION_CACHE[key] = out
    return _REGION_CACHE[key]


def footprint_regions(profile: Profile, part: PartDef, pos: Sub, turns: int) -> List[Region]:
    """Sub-cells a part occupies at sub-grid `pos`, turned `turns` times, with how each is filled."""
    return [((x + pos[0], y + pos[1], z + pos[2]), translate_cut(cut, pos) if cut else None)
            for (x, y, z), cut in _turned_regions(profile, part, turns)]


def footprint(profile: Profile, part: PartDef, pos: Sub, turns: int) -> List[Sub]:
    """Sub-cells a part touches (fully or partly) at sub-grid `pos`, turned `turns` times."""
    return [(x + pos[0], y + pos[1], z + pos[2]) for (x, y, z), _ in _turned_regions(profile, part, turns)]


def part_solids(profile: Profile, part: PartDef, pos: Sub, turns: int) -> Tuple[Solid, ...]:
    """World-space bodies (outward faces) of a part placed at `pos`, turned `turns` times: its boxes
    and wedges, then its round bodies (balls, arms, cups)."""
    key = (part, profile.subdiv)
    if key not in _FACE_CACHE:
        _FACE_CACHE[key] = [body_faces(b, profile.subdiv) for b in part.bodies]
    grid = tuple(transform_faces(faces, turns, pos, profile.sub_to_world) for faces in _FACE_CACHE[key])
    return grid + tuple(round_faces(rb, part_point_to_world(profile, rb.at, pos, turns), turn_axis(rb.axis, turns))
                        for rb in part.round_bodies)


def hollow_areas(profile: Profile, part: PartDef, pos: Sub, turns: int):
    """(corner, side end, other side end, axis) of a part's hollows, in its grid's space."""
    return tuple((part_point_to_world(profile, a, pos, turns), part_point_to_world(profile, b, pos, turns),
                  part_point_to_world(profile, c, pos, turns), glm.vec3(0, 0, 1)) for a, b, c in part.hollows)


def joint_solid_flags(part: PartDef) -> Tuple[bool, ...]:
    """Which of part_solids' solids belong to a joint."""
    return (False,) * len(part.bodies) + tuple(rb.joint for rb in part.round_bodies)


def joint_sockets(profile: Profile, part: PartDef, pos: Sub, turns: int):
    """(kind, pivot, axis, slot) of a part's ball / cup sockets, in its grid's space."""
    out = []
    for j in part.joints:
        axis = turn_axis(j.axis, turns)
        out.append((j.kind, part_point_to_world(profile, j.at, pos, turns) + axis * j.offset, axis,
                    turn_axis(j.slot, turns)))
    return tuple(out)


def part_edges(profile: Profile, part: PartDef, pos: Sub, turns: int) -> Tuple[Tuple[glm.vec3, glm.vec3], ...]:
    """World-space outline of a placed part's merged shape (computed once per part type)."""
    key = (part, profile.subdiv)
    if key not in _OUTLINE_CACHE:
        _OUTLINE_CACHE[key] = part_outline(part.bodies, profile.subdiv)
    rings = [seg for rb in part.round_bodies
             for seg in round_edges(rb, part_point_to_world(profile, rb.at, pos, turns), turn_axis(rb.axis, turns))]
    return tuple(transform_segments(_OUTLINE_CACHE[key], turns, pos, profile.sub_to_world)) + tuple(rings)


def anchor_cells(part: PartDef) -> List[Tuple[int, int, int]]:
    """Cells of a part that can be held under the cursor when placing: its bottom layer."""
    return [c for c in part.cells if c[2] == 0]


def placement_target(profile: Profile, point: glm.vec3, normal: glm.vec3, half: bool) -> Optional[Sub]:
    """Sub-grid min corner of the cell to place against a face (or the ground).

    `point` is where the cursor ray hit, `normal` the face's axis-aligned outward normal.
    Along the normal the cell sits flush against the face; along the other axes it's the cell
    whose centre is nearest the hit point, snapped to whole cells, or to half-cell steps in XY
    when `half` is on (half-offset placement).

    A sloped face (normal not along an axis) targets the empty part of its own cell, the one
    just outside the face: nothing attaches to a slope, but that's where a complementary wedge
    goes (anything else won't fit there).
    """
    if sum(1 for v in normal if abs(v) > 0.999) != 1:
        p = profile.world_to_sub(point + normal * 0.05)
        out = []
        for axis in range(3):
            size = profile.subdiv[axis]
            step = 1 if (half and axis < 2) else size
            out.append(math.floor((p[axis] - size / 2) / step + 0.5) * step)
        return (out[0], out[1], out[2])
    p = profile.world_to_sub(point)
    out = []
    for axis in range(3):
        size = profile.subdiv[axis]
        n = normal[axis]
        if abs(n) > 0.5:
            face = math.floor(p[axis] + 0.5)  # faces lie on sub-grid lines
            out.append(face if n > 0 else face - size)
        else:
            step = 1 if (half and axis < 2) else size
            out.append(math.floor((p[axis] - size / 2) / step + 0.5) * step)
    return (out[0], out[1], out[2])


def default_anchor_index(part: PartDef) -> int:
    """Index into anchor_cells(part) of the cell nearest the centre of the bottom layer.
    Ties go to the cell further along +X, then +Y (part coordinates, before turning)."""
    cells = anchor_cells(part)
    cx = sum(c[0] + 0.5 for c in cells) / len(cells)
    cy = sum(c[1] + 0.5 for c in cells) / len(cells)
    def key(i):
        x, y, _ = cells[i]
        return ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2, -x, -y)
    return min(range(len(cells)), key=key)


def origin_for_anchor(profile: Profile, anchor: Tuple[int, int, int], turns: int, target: Sub) -> Sub:
    """Origin position that puts the part's `anchor` cell (after turning) on the cell whose
    min-corner sub-cell is `target`. This is an editor convenience: the saved position is still
    the part origin."""
    nx, ny, nz = profile.subdiv
    rx, ry = rotate_cell(anchor[0], anchor[1], turns)
    return (target[0] - rx * nx, target[1] - ry * ny, target[2] - anchor[2] * nz)


def part_point_to_world(profile: Profile, point, pos: Sub, turns: int) -> glm.vec3:
    """A point in part cells (x, y, z) -> world, for a part at `pos` turned `turns` times."""
    nx, ny, nz = profile.subdiv
    x, y, z = point
    for _ in range(turns % 4):  # turn CCW about the origin corner
        x, y = -y, x
    return profile.sub_to_world((pos[0] + x * nx, pos[1] + y * ny, pos[2] + z * nz))


def turn_axis(axis, turns: int) -> glm.vec3:
    """A part-space direction turned `turns` quarter turns CCW about Z."""
    x, y, z = axis
    for _ in range(turns % 4):
        x, y = -y, x
    return glm.vec3(x, y, z)


def stud_axes(part: PartDef, turns: int) -> Tuple[glm.vec3, ...]:
    return tuple(turn_axis(a, turns) for a in part.stud_axes)


def antistud_axes(part: PartDef, turns: int) -> Tuple[glm.vec3, ...]:
    return tuple(turn_axis(a, turns) for a in part.antistud_axes)


def antistud_slots(profile: Profile, part: PartDef, pos: Sub, turns: int):
    """World slots under a placed part where a stud from below fits."""
    return tuple((part_point_to_world(profile, a, pos, turns), part_point_to_world(profile, b, pos, turns))
                 for a, b in part.antistuds)


def stud_positions(profile: Profile, part: PartDef, pos: Sub, turns: int) -> Tuple[glm.vec3, ...]:
    """World positions of a placed part's stud bases (centre of each stud's bottom)."""
    return tuple(part_point_to_world(profile, p, pos, turns) for p in part.studs)


def unit_quat(rotation: glm.quat) -> glm.quat:
    # Normalise only if needed: re-normalising a unit quaternion in single precision nudges it,
    # so every save/load would drift
    rotation = glm.quat(rotation)
    if abs(glm.length(rotation) - 1) > 1e-6:
        rotation = glm.normalize(rotation)
    return rotation


def decompose(m: glm.mat4) -> Tuple[glm.vec3, glm.quat]:
    """A rigid transform as (translation, rotation), the way frames store it."""
    return glm.vec3(m[3]), unit_quat(glm.quat_cast(glm.mat3(m)))


def yaw_degrees(rotation: glm.quat) -> float:
    """How far a rotation turns the X axis about Z, in degrees (-180..180]."""
    x = glm.mat3_cast(rotation) * glm.vec3(1, 0, 0)
    return math.degrees(math.atan2(x.y, x.x))


def turn_about(pivot: glm.vec3, axis: glm.vec3, degrees: float) -> glm.mat4:
    """Turning about the line through `pivot` along `axis` (right-handed)."""
    return (glm.translate(glm.mat4(1.0), pivot)
            * glm.mat4_cast(glm.angleAxis(math.radians(degrees), glm.normalize(axis)))
            * glm.translate(glm.mat4(1.0), -pivot))


def turn_about_z(pivot: glm.vec3, degrees: float) -> glm.mat4:
    """Turning about the vertical axis through `pivot`."""
    return turn_about(pivot, glm.vec3(0, 0, 1), degrees)


def plane_basis(axis: glm.vec3) -> Tuple[glm.vec3, glm.vec3]:
    """Two unit vectors (u, v) across `axis`, with u x v = axis. For +Z: X and Y."""
    n = glm.normalize(axis)
    ref = glm.vec3(1, 0, 0) if abs(n.x) < 0.9 else glm.vec3(0, 1, 0)
    u = glm.normalize(ref - n * glm.dot(ref, n))
    return u, glm.cross(n, u)


def angle_about(axis: glm.vec3, a: glm.vec3, b: glm.vec3) -> float:
    """Signed angle (degrees) from a to b seen along `axis` (both projected across it)."""
    u, v = plane_basis(axis)
    return math.degrees(math.atan2(glm.dot(b, v), glm.dot(b, u)) - math.atan2(glm.dot(a, v), glm.dot(a, u)))


def to_parent_grid(profile: Profile, origin: glm.vec3, rotation: glm.quat,
                   pos: Sub, turns: int) -> Optional[Tuple[Sub, int]]:
    """A part at `pos`/`turns` in a frame placed at (origin, rotation) in its parent, as a
    position and turns on the parent's own grid; None if the frame isn't lined up with that grid
    (turned by something other than a multiple of 90 degrees about Z, or off the sub-grid)."""
    r = glm.mat3_cast(rotation)
    if glm.distance(r * glm.vec3(0, 0, 1), glm.vec3(0, 0, 1)) > 1e-5:
        return None
    angle = yaw_degrees(rotation)
    k = round(angle / 90)
    if abs(angle - k * 90) > 1e-3:
        return None
    q = profile.world_to_sub(r * profile.sub_to_world(pos) + origin)
    snapped = tuple(round(v) for v in q)
    if any(abs(a - b) > 1e-3 for a, b in zip(q, snapped)):
        return None
    return (snapped[0], snapped[1], snapped[2]), (turns + k) % 4


def subcells_box(profile: Profile, subcells: Iterable[Sub]) -> Tuple[glm.vec3, glm.vec3]:
    """World AABB around a set of sub-cells."""
    xs, ys, zs = zip(*subcells)
    return (profile.sub_to_world((min(xs), min(ys), min(zs))),
            profile.sub_to_world((max(xs) + 1, max(ys) + 1, max(zs) + 1)))


# v1 saves stored float RGB from the old placeholder palette. Map those values to palette ids
# so old files keep their colors; anything else gets the nearest palette color.
_V1_COLORS = {
    (0.8, 0.1, 0.1): "red",
    (0.1, 0.6, 0.1): "green",
    (0.1, 0.3, 0.8): "cobalt_blue",
    (0.95, 0.9, 0.1): "yellow",
    (0.95, 0.95, 0.95): "white",
    (0.1, 0.1, 0.1): "black",
    (0.6, 0.6, 0.6): "gray",
    (0.3, 0.3, 0.3): "dark_gray",
    (0.9, 0.5, 0.1): "orange",
    (0.4, 0.2, 0.1): "brown",
    (0.5, 0.1, 0.6): "purple",
    (0.9, 0.6, 0.7): "pink",
    (0.2, 0.8, 0.8): "mint_blue",
    (0.6, 0.8, 0.2): "light_green",
}


def v1_color_to_palette(profile: Profile, rgb: Tuple[float, float, float]) -> str:
    for known, color_id in _V1_COLORS.items():
        if color_id in profile.palette and all(abs(a - b) < 1e-3 for a, b in zip(known, rgb)):
            return color_id
    # v1 had no translucent bricks, so prefer opaque colors
    target = glm.vec3(*rgb)
    candidates = [c for c in profile.palette.values() if not c.clear] or list(profile.palette.values())
    return min(candidates, key=lambda c: glm.distance(c.rgb, target)).id


class Model:
    def __init__(self, profile: Profile, library: Dict[str, PartDef]) -> None:
        self.profile = profile
        self.library = library
        self.parts: Dict[int, PlacedPart] = {}
        self.frames: Dict[int, Frame] = {0: ROOT}
        self.groups: Dict[int, Group] = {}
        # (frame, sub-cell) -> [(part id, cut)]: more than one only where complementary wedges
        # meet. Each frame has its own grid; parts in different frames are compared by their
        # solids instead (collision.py), on demand.
        self.occupancy: Dict[Tuple[int, Sub], List[Tuple[int, Optional[Cut]]]] = {}
        self.modified = False
        self._next_id = 1
        self._links = None  # cached connection graph, dropped on any add/remove
        self._collisions: Optional[Set[int]] = None  # cached collisions(), dropped likewise
        self._shapes: Dict[int, collision.Shape] = {}  # part id -> its clash-test shape, built on demand
        # A spatial index of the parts' boxes (widened by the stud height): bucket -> part ids, so a
        # clash query only looks at nearby parts
        self._index: Dict[Tuple[int, int, int], Set[int]] = {}

    # --- frames ----------------------------------------------------------------------------

    def frame_matrix(self, frame_id: int) -> glm.mat4:
        """Frame space (its grid's mm coordinates, as the root grid's) -> world."""
        m = glm.mat4(1.0)
        f = self.frames[frame_id]
        while f.parent is not None:
            m = f.local_matrix() * m
            f = self.frames[f.parent]
        return m

    def to_frame(self, frame_id: int, point: glm.vec3, normal: glm.vec3):
        """A world point and direction in a frame's own coordinates (for placing onto its grid)."""
        if frame_id == 0:
            return point, normal
        inv = glm.inverse(self.frame_matrix(frame_id))
        return glm.vec3(inv * glm.vec4(point, 1.0)), glm.normalize(glm.vec3(inv * glm.vec4(normal, 0.0)))

    def add_frame(self, parent: int, origin: glm.vec3, rotation: glm.quat,
                  frame_id: Optional[int] = None) -> Frame:
        if parent not in self.frames:
            raise ModelError(f"unknown parent frame {parent}")
        if frame_id is None:
            frame_id = max(self.frames) + 1
        elif frame_id in self.frames:
            raise ModelError(f"duplicate frame id {frame_id}")
        frame = Frame(frame_id, parent, glm.vec3(origin), unit_quat(rotation))
        self.frames[frame_id] = frame
        self.modified = True
        return frame

    def set_frame(self, frame_id: int, parent: int, origin: glm.vec3, rotation: glm.quat) -> None:
        """Move a frame (new parent and/or transform); its parts and child frames follow."""
        if frame_id == 0:
            raise ModelError("the root frame can't be moved")
        if parent not in self.frames:
            raise ModelError(f"unknown parent frame {parent}")
        f = parent
        while f is not None:
            if f == frame_id:
                raise ModelError(f"frame {frame_id} can't go inside itself")
            f = self.frames[f].parent
        self.frames[frame_id] = Frame(frame_id, parent, glm.vec3(origin), unit_quat(rotation))
        self.modified = True
        inside = self.frame_subtree(frame_id)
        for pid in [p.id for p in self.parts.values() if p.frame in inside]:
            p = self.parts[pid]
            # Same frame, same grid position: only the world geometry changes
            self.remove_part(pid)
            self.add_part(p.part, p.pos, p.turns, p.color, pid, p.frame, p.group)

    def frame_subtree(self, frame_id: int) -> Set[int]:
        """A frame and every frame inside it."""
        inside = {frame_id}
        changed = True
        while changed:
            more = {f.id for f in self.frames.values() if f.parent in inside}
            changed = not more <= inside
            inside |= more
        return inside

    def side_stud_grid(self, part_id: int, stud: int) -> glm.mat4:
        """The grid (grid space -> world) for building on a part's side stud: Z along the stud,
        Y along the part's own up (its frame's Z), origin on the stud's base, so cell (0, 0)'s
        centre is on the stud and layer 0 sits against the face."""
        p = self.parts[part_id]
        z = glm.normalize(p.stud_axes[stud])
        up = glm.vec3(self.frame_matrix(p.frame) * glm.vec4(0, 0, 1, 0))
        y = glm.normalize(up - z * glm.dot(up, z))
        x = glm.cross(y, z)
        return glm.mat4(glm.vec4(x, 0), glm.vec4(y, 0), glm.vec4(z, 0), glm.vec4(p.studs[stud], 1))

    def joint_grid(self, part: PartDef, turns: int, joint: int, target, up: glm.vec3) -> glm.mat4:
        """The grid (grid space -> world) that puts `part` (at pos 0, `turns`) with its joint number
        `joint` straight on `target` (kind, pivot, axis, slot in world): the pivots together, the
        arm pointing into the cup (opposite axes), and the part's up along `up` (the other part's
        up, so a straight joint has both tops the same way)."""
        _, local_pivot, local_axis, _ = joint_sockets(self.profile, part, (0, 0, 0), turns)[joint]
        _, pivot, axis, _ = target

        def basis(x, z):
            x, z = glm.normalize(x), glm.normalize(z)
            return glm.mat3(x, z, glm.cross(x, z))
        r = basis(-axis, up) * glm.transpose(basis(local_axis, glm.vec3(0, 0, 1)))
        m = glm.mat4(r)
        m[3] = glm.vec4(pivot - r * local_pivot, 1.0)
        return m

    def lined_up_frames(self, grid: glm.mat4, exclude: Iterable[int] = ()):
        """Existing frames whose grid lines up with `grid` (grid space -> world): turned by whole
        quarter turns about Z and offset by whole sub-cells. Yields (frame, origin, rotation): `grid`
        in that frame's space, for model.to_parent_grid to convert part positions."""
        exclude = set(exclude)
        for f in sorted(self.frames):
            if f in exclude:
                continue
            origin, rotation = decompose(glm.inverse(self.frame_matrix(f)) * grid)
            if to_parent_grid(self.profile, origin, rotation, (0, 0, 0), 0) is not None:
                yield f, origin, rotation

    def find_grid(self, grid: glm.mat4) -> Optional[Tuple[int, Sub]]:
        """An existing frame whose grid lines up with `grid`. Returns (frame, the sub-cell that
        `grid`'s cell (0, 0, 0) is there), or None. Lets parts on side studs in one plane share a
        frame (so a part can bridge them)."""
        nx, ny, _ = self.profile.subdiv
        centre = self.profile.sub_to_world((nx / 2, ny / 2, 0))
        for f, _, _ in self.lined_up_frames(grid):
            rel = glm.inverse(self.frame_matrix(f)) * grid
            s = self.profile.world_to_sub(glm.vec3(rel * glm.vec4(centre, 1.0)))
            cell = (s[0] - nx / 2, s[1] - ny / 2, s[2])
            snapped = tuple(round(v) for v in cell)
            if all(abs(a - b) < 1e-3 for a, b in zip(cell, snapped)):
                return f, (snapped[0], snapped[1], snapped[2])
        return None

    def remove_frame(self, frame_id: int) -> None:
        """Remove an empty frame with no child frames."""
        if frame_id == 0:
            raise ModelError("the root frame can't be removed")
        if any(p.frame == frame_id for p in self.parts.values()) or \
                any(f.parent == frame_id for f in self.frames.values()):
            raise ModelError(f"frame {frame_id} still has parts or child frames")
        del self.frames[frame_id]
        self.modified = True

    # --- queries ---------------------------------------------------------------------------

    def _fits(self, frame: int, regions: List[Region]) -> bool:
        for sub, cut in regions:
            for _, other in self.occupancy.get((frame, sub), ()):
                if not compatible(cut, other):
                    return False
        return True

    def can_place(self, part: PartDef, pos: Sub, turns: int, frame: int = 0) -> bool:
        """Fits its frame's grid and doesn't clash with anything: the full clash test against every
        part (on its own grid bodies can only touch, so there it's the studs that count: a stud
        outside the new part's slots, or the new part's stud outside another's, blocks)."""
        if not self._fits(frame, footprint_regions(self.profile, part, pos, turns)):
            return False
        return not self.clashes(self.placed_shape(part, pos, turns, self.frame_matrix(frame)))

    INDEX_SIZE = 8.0  # mm: the spatial index's bucket size (two Nanoblock cells)

    def _buckets(self, box):
        s = self.INDEX_SIZE
        lo = [math.floor(box[0][k] / s) for k in range(3)]
        hi = [math.floor(box[1][k] / s) for k in range(3)]
        for i in range(lo[0], hi[0] + 1):
            for j in range(lo[1], hi[1] + 1):
                for k in range(lo[2], hi[2] + 1):
                    yield i, j, k

    def _index_box(self, placed) -> Tuple[glm.vec3, glm.vec3]:
        h = self.profile.stud.height
        return placed.box[0] - glm.vec3(h), placed.box[1] + glm.vec3(h)

    def _index_add(self, placed) -> None:
        for key in self._buckets(self._index_box(placed)):
            self._index.setdefault(key, set()).add(placed.id)

    def _index_remove(self, placed) -> None:
        for key in self._buckets(self._index_box(placed)):
            ids = self._index.get(key)
            if ids is not None:
                ids.discard(placed.id)
                if not ids:
                    del self._index[key]

    def near(self, box) -> Set[int]:
        """Parts whose (stud-widened) box may touch `box`, from the spatial index."""
        out: Set[int] = set()
        for key in self._buckets(box):
            out |= self._index.get(key, set())
        return out

    _LOCAL_SHAPES: Dict[Tuple[str, Tuple[int, int, int], int], collision.Shape] = {}

    def placed_shape(self, part: PartDef, pos: Sub, turns: int, matrix: glm.mat4) -> collision.Shape:
        """The clash-test shape of a part at pos / turns on a grid placed by `matrix`: built once per
        part type and turn (at pos 0), then moved into place."""
        key = (part.id, self.profile.subdiv, turns % 4)
        if key not in self._LOCAL_SHAPES:
            self._LOCAL_SHAPES[key] = self.shape(self.placement_geometry(part, (0, 0, 0), turns, glm.mat4(1.0)))
        offset = self.profile.sub_to_world(pos) - self.profile.sub_to_world((0, 0, 0))
        return collision.transform_shape(self._LOCAL_SHAPES[key], matrix * glm.translate(glm.mat4(1.0), offset))

    def shape(self, geo) -> collision.Shape:
        """World geometry (a placement_geometry dict, or a PlacedPart) -> what the clash test needs."""
        g = geo if isinstance(geo, dict) else vars(geo)
        st = self.profile.stud
        return collision.make_shape(g["solids"], g["studs"], g["stud_axes"], g["antistuds"], g["antistud_axes"],
                                    st.diameter / 2, st.height, g.get("joint_solids", ()), g.get("joints", ()),
                                    g.get("hollows", ()))

    def part_shape(self, part_id: int) -> collision.Shape:
        if part_id not in self._shapes:
            p = self.parts[part_id]
            self._shapes[part_id] = self.placed_shape(p.part, p.pos, p.turns, self.frame_matrix(p.frame))
        return self._shapes[part_id]

    def clashes(self, shape: collision.Shape, skip=lambda p: False) -> List[int]:
        """Parts (except those `skip` says) that a shape clashes with, nearest by id order."""
        out = []
        for pid in sorted(self.near(shape.box)):
            p = self.parts[pid]
            if not skip(p) and collision.boxes_overlap(shape.box, p.box, -self.profile.stud.height) \
                    and collision.clash(shape, self.part_shape(pid)) is not None:
                out.append(pid)
        return out

    def blocking_studs(self, shape: collision.Shape) -> List[Tuple[glm.vec3, glm.vec3]]:
        """Studs (base, axis), of the shape or of any part, that stop the shape going where it is."""
        out = []
        for pid in self.clashes(shape):
            out += collision.blocking_studs(shape, self.part_shape(pid))
        return out

    def clash_reason(self, a: collision.Shape, part_id: int) -> str:
        """Words for why a shape clashes with a part (for the status bar)."""
        kind = collision.clash(a, self.part_shape(part_id))
        if kind == "stud":
            return f"a stud would be outside the slots of part {part_id}"
        return f"it would overlap part {part_id}"

    def cross_frame_overlaps(self, frame: int, shape: collision.Shape, ignore: Iterable[int] = ()) -> List[int]:
        """Parts outside `frame` (and not in `ignore`) that a shape clashes with. Within a frame
        the occupancy decides instead."""
        ignore = set(ignore)
        return self.clashes(shape, lambda p: p.frame == frame or p.id in ignore)

    def placement_geometry(self, part: PartDef, pos: Sub, turns: int, matrix: glm.mat4) -> Dict[str, tuple]:
        """World solids, studs and antistud slots of a part at pos/turns on a grid placed by
        `matrix` (grid space -> world), e.g. a frame that doesn't exist yet."""
        def pt(p):
            return glm.vec3(matrix * glm.vec4(p, 1.0))

        def axis(v):
            return glm.normalize(glm.vec3(matrix * glm.vec4(v, 0.0)))
        return {
            "solids": tuple([[pt(p) for p in face] for face in solid]
                            for solid in part_solids(self.profile, part, pos, turns)),
            "studs": tuple(pt(p) for p in stud_positions(self.profile, part, pos, turns)),
            "antistuds": tuple((pt(a), pt(b)) for a, b in antistud_slots(self.profile, part, pos, turns)),
            "stud_axes": tuple(axis(a) for a in stud_axes(part, turns)),
            "antistud_axes": tuple(axis(a) for a in antistud_axes(part, turns)),
            "joint_solids": joint_solid_flags(part),
            "joints": tuple((k, pt(p), axis(a), axis(s)) for k, p, a, s in joint_sockets(self.profile, part, pos, turns)),
            "hollows": tuple((pt(a), pt(b), pt(c), axis(n)) for a, b, c, n in hollow_areas(self.profile, part, pos, turns)),
        }

    def turned_placement_problem(self, part: PartDef, pos: Sub, turns: int, matrix: glm.mat4) -> Optional[str]:
        """Why a part can't go on a grid of its own placed by `matrix` (None if it can): it must
        not clash with anything and must be held by a real stud contact."""
        from types import SimpleNamespace
        from brickbuilder.core.connections import contacts_between, joint_contacts
        geo = self.placement_geometry(part, pos, turns, matrix)
        shape = self.placed_shape(part, pos, turns, matrix)
        hit = self.clashes(shape)
        if hit:
            return self.clash_reason(shape, hit[0])
        ghost = SimpleNamespace(id=-1, **geo)
        if not contacts_between(self.profile, [ghost], self.parts.values()) and \
                not joint_contacts(self.profile, [ghost], self.parts.values()):
            return "a part on a grid of its own has to sit on a stud or a joint (or take one)"
        return None

    def moved_overlaps(self, part_ids, transform: glm.mat4) -> Optional[int]:
        """A part the given parts would clash with if moved by a world transform (the first
        found), or None. For previews; History.move_parts does the real check."""
        moving = set(part_ids)
        for pid in sorted(moving):
            shape = collision.transform_shape(self.part_shape(pid), transform)
            hit = self.clashes(shape, lambda q: q.id in moving)
            if hit:
                return hit[0]
        return None

    def joints_within_limits(self, part_ids, transform: glm.mat4) -> bool:
        """Would the joints between the given parts and the rest stay within their limits if the
        parts were moved by a world transform (their centres move with them, so only the angles
        are checked)?"""
        from brickbuilder.core.connections import joint_contacts, joint_limits, within_limits
        moving = set(part_ids)
        rest = [p for p in self.parts.values() if p.id not in moving]
        rot = glm.mat3(transform)
        cone, slot = joint_limits(self.profile)
        for j in joint_contacts(self.profile, [self.parts[p] for p in moving], rest):
            ball = rot * j.ball_axis if j.ball_part in moving else j.ball_axis
            cup, cup_slot = (rot * j.cup_axis, rot * j.cup_slot) if j.cup_part in moving else (j.cup_axis, j.cup_slot)
            if not within_limits(ball, cup, cup_slot, cone, slot):
                return False
        return True

    def collisions(self) -> Set[int]:
        """Parts clashing with a part in another frame (within a frame, overlaps can't happen).
        Cached until the next change."""
        if self._collisions is None:
            self._collisions = self._find_collisions()
        return self._collisions

    def _find_collisions(self) -> Set[int]:
        out: Set[int] = set()
        if len({p.frame for p in self.parts.values()}) < 2:
            return out  # one grid: the occupancy map already rules overlaps out
        for a in self.parts.values():
            for bid in self.near(self._index_box(a)):
                b = self.parts[bid]
                if bid > a.id and b.frame != a.frame and \
                        collision.clash(self.part_shape(a.id), self.part_shape(bid)) is not None:
                    out |= {a.id, bid}
        return out

    def _to_world(self, frame: int, solids=(), edges=(), studs=(), antistuds=(), stud_axes=(), antistud_axes=(),
                  joints=(), hollows=()):
        """Move frame-space geometry into the world (a no-op for the root frame)."""
        if frame == 0:
            return {"solids": solids, "edges": edges, "studs": studs, "antistuds": antistuds,
                    "stud_axes": stud_axes, "antistud_axes": antistud_axes, "joints": joints, "hollows": hollows}
        m = self.frame_matrix(frame)

        def pt(p):
            return glm.vec3(m * glm.vec4(p, 1.0))

        def axis(v):
            return glm.normalize(glm.vec3(m * glm.vec4(v, 0.0)))
        return {
            "solids": tuple([[pt(p) for p in face] for face in solid] for solid in solids),
            "edges": tuple((pt(a), pt(b)) for a, b in edges),
            "studs": tuple(pt(p) for p in studs),
            "antistuds": tuple((pt(a), pt(b)) for a, b in antistuds),
            "stud_axes": tuple(axis(a) for a in stud_axes),
            "antistud_axes": tuple(axis(a) for a in antistud_axes),
            "joints": tuple((k, pt(p), axis(a), axis(s)) for k, p, a, s in joints),
            "hollows": tuple((pt(a), pt(b), pt(c), axis(n)) for a, b, c, n in hollows),
        }

    def connections(self) -> Dict[int, set]:
        """Part id -> ids of the parts it's connected to (a stud of one in a slot of the other).
        Worked out from the parts, not stored; cached until the next add or remove."""
        if self._links is None:
            from brickbuilder.core.connections import find_connections
            self._links = find_connections(self.profile, self.parts.values())
        return self._links

    def parts_at(self, sub: Sub, frame: int = 0) -> List[PlacedPart]:
        return [self.parts[part_id] for part_id, _ in self.occupancy.get((frame, sub), ())]

    # --- edits ---------------------------------------------------------------------------

    def add_part(self, part: PartDef, pos: Sub, turns: int, color: str,
                 part_id: Optional[int] = None, frame: int = 0,
                 group: Optional[int] = None) -> Optional[PlacedPart]:
        """Place a part on a frame's grid; returns None (and changes nothing) if it would overlap
        another part in that frame."""
        if color not in self.profile.palette:
            raise ModelError(f"unknown color {color!r}")
        if frame not in self.frames:
            raise ModelError(f"unknown frame {frame}")
        if group is not None and group not in self.groups:
            raise ModelError(f"unknown group {group}")
        regions = footprint_regions(self.profile, part, pos, turns)
        if not self._fits(frame, regions):
            return None
        if part_id is None:
            part_id = self._next_id
        elif part_id in self.parts:
            raise ModelError(f"duplicate part id {part_id}")
        self._next_id = max(self._next_id, part_id + 1)
        world = self._to_world(frame,
                               solids=part_solids(self.profile, part, pos, turns),
                               edges=part_edges(self.profile, part, pos, turns),
                               studs=stud_positions(self.profile, part, pos, turns),
                               antistuds=antistud_slots(self.profile, part, pos, turns),
                               stud_axes=stud_axes(part, turns),
                               antistud_axes=antistud_axes(part, turns),
                               joints=joint_sockets(self.profile, part, pos, turns),
                               hollows=hollow_areas(self.profile, part, pos, turns))
        if frame == 0 and not part.round_bodies:
            box = subcells_box(self.profile, (s for s, _ in regions))
        else:
            box = collision.solids_box(world["solids"])
        placed = PlacedPart(part_id, part, tuple(pos), turns % 4, color, frame,
                            tuple(regions), box, world["solids"], world["edges"],
                            world["studs"], world["antistuds"], world["stud_axes"], world["antistud_axes"],
                            joint_solid_flags(part), world["joints"], world["hollows"], group)
        self.parts[part_id] = placed
        self._index_add(placed)
        for sub, cut in regions:
            self.occupancy.setdefault((frame, sub), []).append((part_id, cut))
        self._links = self._collisions = None
        self.modified = True
        return placed

    def remove_part(self, part_id: int) -> None:
        placed = self.parts.pop(part_id, None)
        if placed is None:
            return
        self._shapes.pop(part_id, None)
        self._index_remove(placed)
        for sub, _ in placed.regions:
            key = (placed.frame, sub)
            remaining = [entry for entry in self.occupancy[key] if entry[0] != part_id]
            if remaining:
                self.occupancy[key] = remaining
            else:
                del self.occupancy[key]
        self._links = self._collisions = None
        self.modified = True

    def set_color(self, part_id: int, color: str) -> None:
        if color not in self.profile.palette:
            raise ModelError(f"unknown color {color!r}")
        placed = self.parts[part_id]
        if placed.color != color:
            placed.color = color
            self.modified = True

    # --- groups ----------------------------------------------------------------------------

    def add_group(self, name: str, parent: Optional[int] = None, group_id: Optional[int] = None) -> Group:
        if parent is not None and parent not in self.groups:
            raise ModelError(f"unknown parent group {parent}")
        if group_id is None:
            group_id = max(self.groups, default=0) + 1
        elif group_id in self.groups:
            raise ModelError(f"duplicate group id {group_id}")
        group = Group(group_id, name, parent)
        self.groups[group_id] = group
        self.modified = True
        return group

    def remove_group(self, group_id: int) -> None:
        """Remove an empty group (no parts, no child groups)."""
        if any(p.group == group_id for p in self.parts.values()) or \
                any(g.parent == group_id for g in self.groups.values()):
            raise ModelError(f"group {group_id} isn't empty")
        del self.groups[group_id]
        self.modified = True

    def set_part_group(self, part_id: int, group_id: Optional[int]) -> None:
        if group_id is not None and group_id not in self.groups:
            raise ModelError(f"unknown group {group_id}")
        self.parts[part_id].group = group_id
        self.modified = True

    def set_group_parent(self, group_id: int, parent: Optional[int]) -> None:
        g = parent
        while g is not None:  # no cycles: the new parent can't be inside this group
            if g == group_id:
                raise ModelError(f"group {group_id} can't go inside itself")
            g = self.groups[g].parent
        self.groups[group_id].parent = parent
        self.modified = True

    def rename_group(self, group_id: int, name: str) -> None:
        self.groups[group_id].name = name
        self.modified = True

    def group_ancestors(self, group_id: Optional[int]) -> List[int]:
        """The group and the groups it's inside, outermost first."""
        chain: List[int] = []
        while group_id is not None:
            chain.append(group_id)
            group_id = self.groups[group_id].parent
        return chain[::-1]

    def group_chain(self, part_id: int) -> List[int]:
        """The groups a part is inside, outermost first."""
        return self.group_ancestors(self.parts[part_id].group)

    def group_parts(self, group_id: int) -> Set[int]:
        """Every part inside a group, including its child groups."""
        inside = {group_id}
        changed = True
        while changed:
            more = {g.id for g in self.groups.values() if g.parent in inside}
            changed = not more <= inside
            inside |= more
        return {p.id for p in self.parts.values() if p.group in inside}

    def selection_unit(self, part_id: int, context: Optional[int] = None) -> Tuple[Set[int], Optional[int]]:
        """What clicking a part selects: the group one level below `context` that holds it
        (the outermost group for None), or the part itself below its innermost group.
        Returns (part ids, group id or None). A context the part isn't inside counts as None."""
        chain = self.group_chain(part_id)
        level = chain.index(context) + 1 if context in chain else 0
        if level < len(chain):
            return self.group_parts(chain[level]), chain[level]
        return {part_id}, None

    def top_units(self, part_ids) -> Tuple[Set[int], Set[int]]:
        """Split a set of parts into its largest whole groups and the loose parts left over:
        each part goes up to the outermost group whose parts are all in the set.
        Returns (group ids, part ids)."""
        part_ids = set(part_ids)
        whole: Dict[int, bool] = {}
        groups: Set[int] = set()
        loose: Set[int] = set()
        for pid in part_ids:
            top = None
            for g in self.group_chain(pid):
                if g not in whole:
                    whole[g] = self.group_parts(g) <= part_ids
                if whole[g]:
                    top = g
                    break
            if top is None:
                loose.add(pid)
            else:
                groups.add(top)
        return groups, loose

    def clear(self) -> None:
        self._links = self._collisions = None
        self.parts.clear()
        self._shapes = {}
        self._index = {}
        self.frames = {0: ROOT}
        self.groups = {}
        self.occupancy.clear()
        self._next_id = 1
        self.modified = True

    # --- save / load ---------------------------------------------------------------------

    def _pos_to_cells(self, pos: Sub) -> List[float]:
        out: List[float] = []
        for v, n in zip(pos, self.profile.subdiv):
            out.append(v // n if v % n == 0 else v / n)
        return out

    def _cells_to_pos(self, where: str, value: Any) -> Sub:
        if not (isinstance(value, list) and len(value) == 3
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
            raise ModelError(f"{where}: 'pos' must be a list of 3 numbers")
        out = []
        for v, n in zip(value, self.profile.subdiv):
            sub = round(v * n)
            if abs(sub - v * n) > 1e-6:
                raise ModelError(f"{where}: pos {value} is not on the 1/{n} sub-grid")
            out.append(sub)
        return (out[0], out[1], out[2])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SAVE_VERSION,
            "profile": self.profile.id,
            "frames": [self._frame_to_dict(f) for f in sorted(self.frames.values(), key=lambda f: f.id)],
            "groups": [{"id": g.id, "name": g.name, "parent": g.parent} for g in self._groups_parent_first()],
            "parts": [
                {
                    "id": p.id,
                    "part": p.part.id,
                    "frame": p.frame,
                    "pos": self._pos_to_cells(p.pos),
                    "turns": p.turns,
                    "color": p.color,
                    **({"group": p.group} if p.group is not None else {}),
                }
                for p in sorted(self.parts.values(), key=lambda p: p.id)
            ],
        }

    def _groups_parent_first(self) -> List[Group]:
        out: List[Group] = []
        def visit(parent):
            for g in sorted((g for g in self.groups.values() if g.parent == parent), key=lambda g: g.id):
                out.append(g)
                visit(g.id)
        visit(None)
        return out

    @staticmethod
    def _frame_to_dict(f: Frame) -> Dict[str, Any]:
        if f.parent is None:
            return {"id": f.id}
        q = f.rotation
        return {"id": f.id, "parent": f.parent, "origin": [f.origin.x, f.origin.y, f.origin.z],
                "rotation": [q.w, q.x, q.y, q.z]}

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Replace the model's contents. On error, raises ModelError and leaves the model untouched."""
        loaded = Model(self.profile, self.library)
        version = data.get("version")
        if version == 1:
            loaded._load_v1(data)
        elif version in (2, 3, SAVE_VERSION):
            loaded._load_v2(data)
        else:
            raise ModelError(f"unsupported save version {version!r}")
        self.parts, self.occupancy, self._next_id = loaded.parts, loaded.occupancy, loaded._next_id
        self.frames = loaded.frames
        self.groups = loaded.groups
        self._links = self._collisions = None
        self._shapes = {}
        self._index = loaded._index
        self.modified = False

    def _load_v1(self, data: Dict[str, Any]) -> None:
        brick = self.library.get(f"{self.profile.id}:brick_1x1")
        if brick is None:
            raise ModelError("v1 files need a brick_1x1 part in the library")
        for n, b in enumerate(data.get("bricks", [])):
            try:
                cell = (int(b["x"]), int(b["y"]), int(b["z"]))
                rgb = (float(b["r"]), float(b["g"]), float(b["b"]))
            except (KeyError, TypeError, ValueError):
                raise ModelError(f"bricks[{n}]: needs x, y, z, r, g, b") from None
            color = v1_color_to_palette(self.profile, rgb)
            if self.add_part(brick, self.profile.cell_to_sub(cell), 0, color) is None:
                raise ModelError(f"bricks[{n}]: overlaps another brick")

    def _load_v2(self, data: Dict[str, Any]) -> None:
        if data.get("profile") != self.profile.id:
            raise ModelError(f"file is for profile {data.get('profile')!r}, not {self.profile.id!r}")
        self._load_frames(data.get("frames", [{"id": 0}]), data.get("version"))
        self._load_groups(data.get("groups", []), data.get("version"))
        parts = data.get("parts", [])
        if not isinstance(parts, list):
            raise ModelError("'parts' must be a list")
        for n, p in enumerate(parts):
            where = f"parts[{n}]"
            if not isinstance(p, dict):
                raise ModelError(f"{where}: must be an object")
            part = self.library.get(p.get("part"))
            if part is None:
                raise ModelError(f"{where}: unknown part {p.get('part')!r}")
            frame = p.get("frame", 0)
            if frame not in self.frames:
                raise ModelError(f"{where}: unknown frame {frame!r}")
            turns, part_id, color = p.get("turns", 0), p.get("id"), p.get("color")
            if not isinstance(turns, int) or not 0 <= turns <= 3:
                raise ModelError(f"{where}: 'turns' must be 0..3")
            if not isinstance(part_id, int) or isinstance(part_id, bool) or part_id < 1:
                raise ModelError(f"{where}: 'id' must be a positive integer")
            if color not in self.profile.palette:
                raise ModelError(f"{where}: unknown color {color!r}")
            pos = self._cells_to_pos(where, p.get("pos"))
            group = p.get("group")
            if group is not None and group not in self.groups:
                raise ModelError(f"{where}: unknown group {group!r}")
            if self.add_part(part, pos, turns, color, part_id, frame, group) is None:
                raise ModelError(f"{where}: overlaps another part")

    def _load_groups(self, groups: Any, version: Any) -> None:
        """Groups in order, each after its parent."""
        if not isinstance(groups, list):
            raise ModelError("'groups' must be a list")
        if version in (2, 3) and groups:
            raise ModelError(f"v{version} files have no groups")
        for n, g in enumerate(groups):
            where = f"groups[{n}]"
            if not isinstance(g, dict) or set(g) != {"id", "name", "parent"}:
                raise ModelError(f"{where}: needs id, name and parent")
            gid, name, parent = g["id"], g["name"], g["parent"]
            if not isinstance(gid, int) or isinstance(gid, bool) or gid < 1 or gid in self.groups:
                raise ModelError(f"{where}: 'id' must be a new positive integer")
            if not isinstance(name, str):
                raise ModelError(f"{where}: 'name' must be a string")
            if parent is not None and parent not in self.groups:
                raise ModelError(f"{where}: parent {parent!r} must be listed before it")
            self.add_group(name, parent, gid)

    def _load_frames(self, frames: Any, version: Any) -> None:
        """Frames in order, each after its parent (so they always form a tree from the root)."""
        if not isinstance(frames, list) or not frames or frames[0] != {"id": 0}:
            raise ModelError("'frames' must be a list starting with the root frame {\"id\": 0}")
        if version == 2 and len(frames) > 1:
            raise ModelError("v2 files have only the root frame")

        def numbers(v, k):
            return isinstance(v, list) and len(v) == k and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
        for n, f in enumerate(frames[1:], start=1):
            where = f"frames[{n}]"
            if not isinstance(f, dict) or set(f) != {"id", "parent", "origin", "rotation"}:
                raise ModelError(f"{where}: needs id, parent, origin and rotation")
            fid, parent, origin, rotation = f["id"], f["parent"], f["origin"], f["rotation"]
            if not isinstance(fid, int) or isinstance(fid, bool) or fid < 1 or fid in self.frames:
                raise ModelError(f"{where}: 'id' must be a new positive integer")
            if parent not in self.frames:
                raise ModelError(f"{where}: parent {parent!r} must be listed before it")
            if not numbers(origin, 3):
                raise ModelError(f"{where}: 'origin' must be 3 numbers (mm)")
            if not numbers(rotation, 4) or abs(sum(x * x for x in rotation) - 1) > 1e-6:
                raise ModelError(f"{where}: 'rotation' must be a unit quaternion [w, x, y, z]")
            self.add_frame(parent, glm.vec3(*origin), glm.quat(*rotation), fid)

    def save_to_file(self, filename: str) -> None:
        # Write to a temporary file and swap it in, so a failed save never truncates the old file
        data = json.dumps(self.to_dict(), indent=2)
        tmp = f"{filename}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, filename)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        self.modified = False

    def load_from_file(self, filename: str) -> None:
        with open(filename, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise ModelError(f"not a valid save file: {e}") from None
        if not isinstance(data, dict):
            raise ModelError("not a valid save file")
        self.from_dict(data)
