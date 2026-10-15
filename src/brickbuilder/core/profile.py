import math
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Tuple
import glm

DEFAULT_PROFILE_ID = "nanoblock"


class ProfileError(ValueError):
    pass


# Profile and colour ids are stable keys in save files: plain ASCII
ID_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class StudSpec:
    diameter: float
    height: float
    hollow_diameter: float = 0.0


@dataclass(frozen=True)
class PaletteColor:
    id: str
    name: str
    rgb: glm.vec3       # 0..1
    clear: bool = False # translucent; rendered opaque for now
    alpha: float = 1.0  # opacity for when translucency is rendered


@dataclass(frozen=True)
class Profile:
    """A brick system: everything that differs between systems lives here (see docs/part_format.md).

    World units are millimetres. Cell index (x, y, z) occupies
    X in [x-0.5, x+0.5]*cell.x, Y in [y-0.5, y+0.5]*cell.y, Z in [z, z+1]*cell.z,
    i.e. cells are centred on integer XY and layer 0 sits on the Z=0 grid.

    Placement uses a finer sub-grid of `subdiv` sub-cells per cell. Sub-cell s along X covers
    cell-space [s/n - 0.5, (s+1)/n - 0.5], so cell i is sub-cells n*i .. n*i + n-1 (same for Y;
    Z is not centred: [s/n, (s+1)/n]).
    """
    id: str
    name: str
    cell: glm.vec3
    subdiv: Tuple[int, int, int]
    grid_rotation: float
    clearance: float
    body_height: float
    stud: StudSpec
    palette: Dict[str, PaletteColor] = field(default_factory=dict)
    socket_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def sub_to_world(self, sub) -> glm.vec3:
        """World position of the minimum corner of sub-cell `sub` (any int triple).
        The single source of truth for grid-to-world mapping; everything else goes through it."""
        nx, ny, nz = self.subdiv
        return glm.vec3(
            (sub[0] / nx - 0.5) * self.cell.x,
            (sub[1] / ny - 0.5) * self.cell.y,
            (sub[2] / nz) * self.cell.z,
        )

    def world_to_sub(self, point: glm.vec3) -> Tuple[float, float, float]:
        """Inverse of sub_to_world: continuous sub-grid coordinates of a world point."""
        nx, ny, nz = self.subdiv
        return ((point.x / self.cell.x + 0.5) * nx,
                (point.y / self.cell.y + 0.5) * ny,
                point.z / self.cell.z * nz)

    def cell_to_sub(self, index) -> Tuple[int, int, int]:
        """Sub-cell at the minimum corner of cell `index`."""
        nx, ny, nz = self.subdiv
        return (index[0] * nx, index[1] * ny, index[2] * nz)

    def cell_box(self, index: glm.ivec3) -> Tuple[glm.vec3, glm.vec3]:
        """World-space AABB (min, max) of the cell at `index`."""
        lo = self.cell_to_sub(index)
        nx, ny, nz = self.subdiv
        return self.sub_to_world(lo), self.sub_to_world((lo[0] + nx, lo[1] + ny, lo[2] + nz))

    def world_to_cell(self, point: glm.vec3) -> glm.ivec3:
        """Index of the cell containing a world-space point."""
        x, y = self.world_to_cell_xy(point)
        return glm.ivec3(x, y, math.floor(point.z / self.cell.z))

    def world_to_cell_xy(self, point: glm.vec3) -> Tuple[int, int]:
        """Index of the cell column containing a world-space point."""
        return round(point.x / self.cell.x), round(point.y / self.cell.y)


def _vec(data: Dict[str, Any], key: str, length: int, kind: type) -> list:
    value = data.get(key)
    if not isinstance(value, list) or len(value) != length:
        raise ProfileError(f"'{key}' must be a list of {length} numbers")
    try:
        items = [kind(v) for v in value]
    except (TypeError, ValueError):
        raise ProfileError(f"'{key}' must be a list of {length} numbers") from None
    if any(v <= 0 for v in items):
        raise ProfileError(f"'{key}' values must be positive")
    return items


def _parse_rgb(color_id: str, value: Any) -> glm.vec3:
    if not (isinstance(value, str) and len(value) == 7 and value.startswith("#")):
        raise ProfileError(f"palette.{color_id}.rgb must look like '#rrggbb'")
    try:
        return glm.vec3(*(int(value[i:i + 2], 16) / 255.0 for i in (1, 3, 5)))
    except ValueError:
        raise ProfileError(f"palette.{color_id}.rgb must look like '#rrggbb'") from None


def _parse_palette(data: Dict[str, Any]) -> Dict[str, PaletteColor]:
    palette: Dict[str, PaletteColor] = {}
    for color_id, entry in data.items():
        if not ID_PATTERN.fullmatch(color_id):
            raise ProfileError(f"palette id {color_id!r} may only use a-z, 0-9 and _")
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ProfileError(f"palette.{color_id} needs a 'name'")
        clear = bool(entry.get("clear", False))
        alpha = entry.get("alpha", 0.75 if clear else 1.0)
        if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0.0 < alpha <= 1.0:
            raise ProfileError(f"palette.{color_id}.alpha must be a number in (0, 1]")
        palette[color_id] = PaletteColor(
            id=color_id,
            name=entry["name"],
            rgb=_parse_rgb(color_id, entry.get("rgb")),
            clear=clear,
            alpha=float(alpha),
        )
    return palette


def profile_from_dict(data: Dict[str, Any]) -> Profile:
    for key in ("id", "name"):
        if not isinstance(data.get(key), str):
            raise ProfileError(f"'{key}' must be a string")
    if not ID_PATTERN.fullmatch(data["id"]):
        raise ProfileError(f"profile id {data['id']!r} may only use a-z, 0-9 and _")
    cell = _vec(data, "cell", 3, float)
    subdiv = _vec(data, "subdiv", 3, int)
    if subdiv[0] != subdiv[1]:
        # Parts turn in 90° steps, which swaps X and Y.
        raise ProfileError("'subdiv' X and Y must be equal")
    palette = _parse_palette(data.get("palette", {}))
    if not palette:
        raise ProfileError("'palette' must define at least one color")
    stud = data.get("stud", {})
    try:
        return Profile(
            id=data["id"],
            name=data["name"],
            cell=glm.vec3(*cell),
            subdiv=tuple(subdiv),
            grid_rotation=float(data.get("grid_rotation", 90.0)),
            clearance=float(data.get("clearance", 0.0)),
            body_height=float(data.get("body_height", cell[2])),
            stud=StudSpec(
                diameter=float(stud["diameter"]),
                height=float(stud["height"]),
                hollow_diameter=float(stud.get("hollow_diameter", 0.0)),
            ),
            palette=palette,
            socket_types=dict(data.get("socket_types", {})),
        )
    except KeyError as e:
        raise ProfileError(f"missing key: stud.{e.args[0]}") from None


def load_profile(path: Path) -> Profile:
    with open(path, "rb") as f:
        return profile_from_dict(tomllib.load(f))


def load_builtin_profile(profile_id: str = DEFAULT_PROFILE_ID) -> Profile:
    source = resources.files("brickbuilder") / "profiles" / f"{profile_id}.toml"
    with source.open("rb") as f:
        return profile_from_dict(tomllib.load(f))
