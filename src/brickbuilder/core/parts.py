"""Part definitions and the built-in part library (see docs/part_format.md, "Layer 2").

Library layout: parts/<profile id>/<category folders>/<name>.toml. A part's id is
"<profile id>:<file stem>"; its category is the folder path below the profile folder.
"""
import tomllib
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any, Dict, List, Optional, Tuple

from brickbuilder.core.geometry import Body, part_regions

Cell = Tuple[int, int, int]


class PartError(ValueError):
    pass


@dataclass(frozen=True)
class PartDef:
    id: str
    name: str
    category: str
    bodies: Tuple[Body, ...]          # in part cells; origin = min corner, bottom
    cells: Tuple[Cell, ...]           # cells any body touches (partly, for wedges), in body order
    studs: Tuple[Cell, ...]           # cells that carry a stud on top (the stud sits on z+1)
    ldraw: Optional[str] = None       # cross-reference into the LDraw Nanoblock library


_TOP_KEYS = {"name", "ldraw", "body"}
_BODY_KEYS = {
    "box": {"shape", "size", "at", "studs"},
    "wedge": {"shape", "size", "at", "studs", "keep", "tall"},
}
_STUD_MODES = {"top", "none"}
_TALL = {"+x": (0, 1), "-x": (0, -1), "+y": (1, 1), "-y": (1, -1)}


def _int_triple(where: str, value: Any, positive: bool) -> Cell:
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) for v in value)):
        raise PartError(f"{where} must be a list of 3 integers")
    if positive and any(v <= 0 for v in value):
        raise PartError(f"{where} values must be positive")
    return (value[0], value[1], value[2])


def _parse_body(where: str, body: Any) -> Body:
    if not isinstance(body, dict):
        raise PartError(f"{where}: must be a table")
    shape = body.get("shape")
    if shape not in _BODY_KEYS:
        raise PartError(f"{where}: unsupported shape {shape!r} (expected one of {sorted(_BODY_KEYS)})")
    unknown = set(body) - _BODY_KEYS[shape]
    if unknown:
        raise PartError(f"{where}: unknown keys {sorted(unknown)}")
    size = _int_triple(f"{where}.size", body.get("size"), positive=True)
    at = _int_triple(f"{where}.at", body.get("at", [0, 0, 0]), positive=False)
    if shape == "box":
        studs = body.get("studs", "top")
        if studs not in _STUD_MODES:
            raise PartError(f"{where}.studs must be one of {sorted(_STUD_MODES)}")
        return Body("box", at, size, studs == "top")
    keep = body.get("keep")
    if keep not in ("lower", "upper"):
        raise PartError(f"{where}.keep must be 'lower' or 'upper'")
    if body.get("tall") not in _TALL:
        raise PartError(f"{where}.tall must be one of {sorted(_TALL)}")
    axis, sign = _TALL[body["tall"]]
    # Only an upper wedge has a flat top; a lower wedge's top is the slope
    studs = body.get("studs", "top" if keep == "upper" else "none")
    if studs not in _STUD_MODES:
        raise PartError(f"{where}.studs must be one of {sorted(_STUD_MODES)}")
    if studs == "top" and keep == "lower":
        raise PartError(f"{where}: a lower wedge's top is sloped and can't carry studs")
    return Body("wedge", at, size, studs == "top", keep, axis, sign)


def part_from_dict(part_id: str, category: str, data: Dict[str, Any]) -> PartDef:
    if "params" in data:
        raise PartError(f"{part_id}: 'params' (parametric families) is reserved and not supported yet")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise PartError(f"{part_id}: unknown keys {sorted(unknown)}")
    if not isinstance(data.get("name"), str):
        raise PartError(f"{part_id}: 'name' must be a string")
    raw_bodies = data.get("body")
    if not isinstance(raw_bodies, list) or not raw_bodies:
        raise PartError(f"{part_id}: needs at least one [[body]]")
    bodies = tuple(_parse_body(f"{part_id}: body[{n}]", b) for n, b in enumerate(raw_bodies))

    # Cells any body touches: the occupancy computation at whole-cell resolution
    cells = tuple(cell for cell, _ in part_regions(bodies, (1, 1, 1)))
    if min(c[0] for c in cells) != 0 or min(c[1] for c in cells) != 0 or min(c[2] for c in cells) != 0:
        raise PartError(f"{part_id}: cells must start at the origin (min corner at 0, 0, 0)")
    stud_tops: List[Cell] = []
    for b in bodies:
        if b.studs:
            top = b.lo[2] + b.size[2] - 1
            stud_tops += [(x, y, top) for x in range(b.lo[0], b.lo[0] + b.size[0])
                          for y in range(b.lo[1], b.lo[1] + b.size[1])]
    # A stud covered by another body isn't a stud.
    cell_set = set(cells)
    studs_final = tuple(c for c in dict.fromkeys(stud_tops) if (c[0], c[1], c[2] + 1) not in cell_set)
    ldraw = data.get("ldraw")
    if ldraw is not None and not isinstance(ldraw, str):
        raise PartError(f"{part_id}: 'ldraw' must be a string")
    return PartDef(part_id, data["name"], category, bodies, cells, studs_final, ldraw)


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
