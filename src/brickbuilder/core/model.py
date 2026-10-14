"""Placed parts, sub-cell occupancy and the save format (see docs/part_format.md)."""
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import glm
from brickbuilder.core.parts import PartDef
from brickbuilder.core.profile import Profile

Sub = Tuple[int, int, int]  # sub-grid coordinate (profile.subdiv sub-cells per cell)

SAVE_VERSION = 2


class ModelError(ValueError):
    pass


@dataclass
class PlacedPart:
    id: int
    part: PartDef
    pos: Sub                # sub-grid position of the part origin (min corner, bottom)
    turns: int              # quarter turns about +Z through the origin, 0..3
    color: str              # palette id
    frame: int              # 0 = root frame (the only one so far)
    subcells: Tuple[Sub, ...]
    box: Tuple[glm.vec3, glm.vec3]  # world AABB
    studs: Tuple[glm.vec3, ...]     # world positions of stud bases (centre of the stud's bottom)


def rotate_cell(x: int, y: int, turns: int) -> Tuple[int, int]:
    """Rotate the cell whose min corner is (x, y) by quarter turns CCW about the origin corner."""
    for _ in range(turns % 4):
        x, y = -y - 1, x
    return x, y


def footprint(profile: Profile, part: PartDef, pos: Sub, turns: int) -> List[Sub]:
    """Sub-cells a part occupies when its origin is at sub-grid `pos`, turned `turns` times."""
    nx, ny, nz = profile.subdiv
    out: List[Sub] = []
    for cx, cy, cz in part.cells:
        rx, ry = rotate_cell(cx, cy, turns)
        bx, by, bz = pos[0] + rx * nx, pos[1] + ry * ny, pos[2] + cz * nz
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    out.append((bx + i, by + j, bz + k))
    return out


def anchor_cells(part: PartDef) -> List[Tuple[int, int, int]]:
    """Cells of a part that can be held under the cursor when placing: its bottom layer."""
    return [c for c in part.cells if c[2] == 0]


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


def stud_positions(profile: Profile, part: PartDef, pos: Sub, turns: int) -> Tuple[glm.vec3, ...]:
    """World positions of a placed part's stud bases: centre of the top face of each stud cell."""
    nx, ny, nz = profile.subdiv
    out = []
    for cx, cy, cz in part.studs:
        rx, ry = rotate_cell(cx, cy, turns)
        out.append(profile.sub_to_world((pos[0] + (rx + 0.5) * nx,
                                         pos[1] + (ry + 0.5) * ny,
                                         pos[2] + (cz + 1) * nz)))
    return tuple(out)


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
        self.occupancy: Dict[Sub, int] = {}  # sub-cell -> part id
        self.modified = False
        self._next_id = 1

    # --- queries -------------------------------------------------------------------------

    def can_place(self, part: PartDef, pos: Sub, turns: int) -> bool:
        return not any(s in self.occupancy for s in footprint(self.profile, part, pos, turns))

    def placement_box(self, part: PartDef, pos: Sub, turns: int) -> Tuple[glm.vec3, glm.vec3]:
        return subcells_box(self.profile, footprint(self.profile, part, pos, turns))

    def placement_studs(self, part: PartDef, pos: Sub, turns: int) -> Tuple[glm.vec3, ...]:
        return stud_positions(self.profile, part, pos, turns)

    def part_at(self, sub: Sub) -> Optional[PlacedPart]:
        part_id = self.occupancy.get(sub)
        return self.parts[part_id] if part_id is not None else None

    # --- edits ---------------------------------------------------------------------------

    def add_part(self, part: PartDef, pos: Sub, turns: int, color: str,
                 part_id: Optional[int] = None) -> Optional[PlacedPart]:
        """Place a part; returns None (and changes nothing) if it would overlap another part."""
        if color not in self.profile.palette:
            raise ModelError(f"unknown color {color!r}")
        cells = footprint(self.profile, part, pos, turns)
        if any(s in self.occupancy for s in cells):
            return None
        if part_id is None:
            part_id = self._next_id
        elif part_id in self.parts:
            raise ModelError(f"duplicate part id {part_id}")
        self._next_id = max(self._next_id, part_id + 1)
        placed = PlacedPart(part_id, part, tuple(pos), turns % 4, color, 0,
                            tuple(cells), subcells_box(self.profile, cells),
                            stud_positions(self.profile, part, pos, turns))
        self.parts[part_id] = placed
        for s in cells:
            self.occupancy[s] = part_id
        self.modified = True
        return placed

    def remove_part(self, part_id: int) -> None:
        placed = self.parts.pop(part_id, None)
        if placed is None:
            return
        for s in placed.subcells:
            del self.occupancy[s]
        self.modified = True

    def set_color(self, part_id: int, color: str) -> None:
        if color not in self.profile.palette:
            raise ModelError(f"unknown color {color!r}")
        placed = self.parts[part_id]
        if placed.color != color:
            placed.color = color
            self.modified = True

    def clear(self) -> None:
        self.parts.clear()
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
            "frames": [{"id": 0}],
            "parts": [
                {
                    "id": p.id,
                    "part": p.part.id,
                    "frame": p.frame,
                    "pos": self._pos_to_cells(p.pos),
                    "turns": p.turns,
                    "color": p.color,
                }
                for p in sorted(self.parts.values(), key=lambda p: p.id)
            ],
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Replace the model's contents. On error, raises ModelError and leaves the model untouched."""
        loaded = Model(self.profile, self.library)
        version = data.get("version")
        if version == 1:
            loaded._load_v1(data)
        elif version == SAVE_VERSION:
            loaded._load_v2(data)
        else:
            raise ModelError(f"unsupported save version {version!r}")
        self.parts, self.occupancy, self._next_id = loaded.parts, loaded.occupancy, loaded._next_id
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
        frames = data.get("frames", [{"id": 0}])
        if [f.get("id") for f in frames] != [0]:
            raise ModelError("only the root frame (id 0) is supported so far")
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
            if p.get("frame", 0) != 0:
                raise ModelError(f"{where}: only frame 0 is supported so far")
            turns, part_id, color = p.get("turns", 0), p.get("id"), p.get("color")
            if not isinstance(turns, int) or not 0 <= turns <= 3:
                raise ModelError(f"{where}: 'turns' must be 0..3")
            if not isinstance(part_id, int) or isinstance(part_id, bool) or part_id < 1:
                raise ModelError(f"{where}: 'id' must be a positive integer")
            if color not in self.profile.palette:
                raise ModelError(f"{where}: unknown color {color!r}")
            pos = self._cells_to_pos(where, p.get("pos"))
            if self.add_part(part, pos, turns, color, part_id) is None:
                raise ModelError(f"{where}: overlaps another part")

    def save_to_file(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
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
