import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Tuple
import glm

DEFAULT_PROFILE_ID = "nanoblock"


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class StudSpec:
    diameter: float
    height: float
    hollow_diameter: float = 0.0


@dataclass(frozen=True)
class Profile:
    """A brick system: everything that differs between systems lives here (see docs/part_format.md).

    World units are millimetres. Cell index (x, y, z) occupies
    X in [x-0.5, x+0.5]*cell.x, Y in [y-0.5, y+0.5]*cell.y, Z in [z, z+1]*cell.z,
    i.e. cells are centred on integer XY and layer 0 sits on the Z=0 grid.
    """
    id: str
    name: str
    cell: glm.vec3
    subdiv: Tuple[int, int, int]
    grid_rotation: float
    clearance: float
    body_height: float
    stud: StudSpec
    socket_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def cell_box(self, index: glm.ivec3) -> Tuple[glm.vec3, glm.vec3]:
        """World-space AABB (min, max) of the cell at `index`. The single source of truth
        for cell-to-world mapping; renderer and picking must both go through it."""
        lo = glm.vec3(index.x - 0.5, index.y - 0.5, index.z) * self.cell
        return lo, lo + self.cell

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


def profile_from_dict(data: Dict[str, Any]) -> Profile:
    for key in ("id", "name"):
        if not isinstance(data.get(key), str):
            raise ProfileError(f"'{key}' must be a string")
    cell = _vec(data, "cell", 3, float)
    stud = data.get("stud", {})
    try:
        return Profile(
            id=data["id"],
            name=data["name"],
            cell=glm.vec3(*cell),
            subdiv=tuple(_vec(data, "subdiv", 3, int)),
            grid_rotation=float(data.get("grid_rotation", 90.0)),
            clearance=float(data.get("clearance", 0.0)),
            body_height=float(data.get("body_height", cell[2])),
            stud=StudSpec(
                diameter=float(stud["diameter"]),
                height=float(stud["height"]),
                hollow_diameter=float(stud.get("hollow_diameter", 0.0)),
            ),
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
