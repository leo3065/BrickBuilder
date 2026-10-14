"""Part definitions and the built-in part library (see docs/part_format.md, "Layer 2").

Library layout: parts/<profile id>/<category folders>/<name>.toml. A part's id is
"<profile id>:<file stem>"; its category is the folder path below the profile folder.
"""
import tomllib
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any, Dict, List, Optional, Tuple

Cell = Tuple[int, int, int]


class PartError(ValueError):
    pass


@dataclass(frozen=True)
class PartDef:
    id: str
    name: str
    category: str
    cells: Tuple[Cell, ...]           # occupied cells in part space; origin = min corner, bottom
    studs: Tuple[Cell, ...]           # cells that carry a stud on top (the stud sits on z+1)
    ldraw: Optional[str] = None       # cross-reference into the LDraw Nanoblock library


_TOP_KEYS = {"name", "ldraw", "body"}
_BOX_KEYS = {"shape", "size", "at", "studs"}
_STUD_MODES = {"top", "none"}


def _int_triple(where: str, value: Any, positive: bool) -> Cell:
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) for v in value)):
        raise PartError(f"{where} must be a list of 3 integers")
    if positive and any(v <= 0 for v in value):
        raise PartError(f"{where} values must be positive")
    return (value[0], value[1], value[2])


def part_from_dict(part_id: str, category: str, data: Dict[str, Any]) -> PartDef:
    if "params" in data:
        raise PartError(f"{part_id}: 'params' (parametric families) is reserved and not supported yet")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise PartError(f"{part_id}: unknown keys {sorted(unknown)}")
    if not isinstance(data.get("name"), str):
        raise PartError(f"{part_id}: 'name' must be a string")
    bodies = data.get("body")
    if not isinstance(bodies, list) or not bodies:
        raise PartError(f"{part_id}: needs at least one [[body]]")

    cells: Dict[Cell, None] = {}  # ordered set
    stud_tops: List[Cell] = []
    for n, body in enumerate(bodies):
        where = f"{part_id}: body[{n}]"
        shape = body.get("shape")
        if shape != "box":
            raise PartError(f"{where}: unsupported shape {shape!r} (only 'box' so far)")
        unknown = set(body) - _BOX_KEYS
        if unknown:
            raise PartError(f"{where}: unknown keys {sorted(unknown)}")
        sx, sy, sz = _int_triple(f"{where}.size", body.get("size"), positive=True)
        ax, ay, az = _int_triple(f"{where}.at", body.get("at", [0, 0, 0]), positive=False)
        studs = body.get("studs", "top")
        if studs not in _STUD_MODES:
            raise PartError(f"{where}.studs must be one of {sorted(_STUD_MODES)}")
        for x in range(ax, ax + sx):
            for y in range(ay, ay + sy):
                for z in range(az, az + sz):
                    cells[(x, y, z)] = None
                if studs == "top":
                    stud_tops.append((x, y, az + sz - 1))

    if min(c[0] for c in cells) != 0 or min(c[1] for c in cells) != 0 or min(c[2] for c in cells) != 0:
        raise PartError(f"{part_id}: cells must start at the origin (min corner at 0, 0, 0)")
    # A stud covered by another body isn't a stud.
    studs_final = tuple(c for c in dict.fromkeys(stud_tops) if (c[0], c[1], c[2] + 1) not in cells)
    ldraw = data.get("ldraw")
    if ldraw is not None and not isinstance(ldraw, str):
        raise PartError(f"{part_id}: 'ldraw' must be a string")
    return PartDef(part_id, data["name"], category, tuple(cells), studs_final, ldraw)


def _walk(folder: Traversable, category: List[str], profile_id: str, out: Dict[str, PartDef]) -> None:
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if entry.is_dir():
            _walk(entry, category + [entry.name], profile_id, out)
        elif entry.name.endswith(".toml"):
            part_id = f"{profile_id}:{entry.name[:-len('.toml')]}"
            if part_id in out:
                raise PartError(f"duplicate part id {part_id}")
            with entry.open("rb") as f:
                try:
                    data = tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    raise PartError(f"{part_id}: {e}") from None
            out[part_id] = part_from_dict(part_id, "/".join(category), data)


def load_builtin_library(profile_id: str) -> Dict[str, PartDef]:
    """All built-in parts for a profile, keyed by part id."""
    root = resources.files("brickbuilder") / "parts" / profile_id
    parts: Dict[str, PartDef] = {}
    if root.is_dir():
        _walk(root, [], profile_id, parts)
    return parts
