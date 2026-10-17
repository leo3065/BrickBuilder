"""Part definitions and the built-in part library (see docs/part_format.md, "Part files").

Library layout: parts/<profile id>/<category folders>/<name>.toml. A part's id is
"<profile id>:<file stem>"; its category is the folder path below the profile folder.
"""
import tomllib
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any, Dict, List, Sequence, Tuple, Union

from brickbuilder.core.geometry import Body, RoundBody, outside_rounding, part_regions
from brickbuilder.core.profile import ID_PATTERN, Profile, UndersideRule, load_builtin_profile

Cell = Tuple[int, int, int]
Point = Tuple[float, float, float]
Segment = Tuple[Point, Point]  # a slot a stud can sit anywhere along; equal ends = a point
Axis = Tuple[int, int, int]    # a unit direction along a part axis, e.g. (0, 0, 1)
UP: Axis = (0, 0, 1)
AXES = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


class PartError(ValueError):
    pass




@dataclass(frozen=True)
class PartDef:
    id: str
    name: str
    category: str
    bodies: Tuple[Body, ...]          # in part cells; origin = min corner, bottom
    cells: Tuple[Cell, ...]           # cells any body touches (partly, for wedges), in body order
    studs: Tuple[Point, ...]          # stud base positions in cells (x, y, height of the face it's on)
    # Where a stud fits: slots (segments) or points, in cells. Derived from the bodies'
    # undersides plus explicit antistud sockets.
    antistuds: Tuple[Segment, ...] = ()
    # Which way each stud points (parallel to `studs`), and which way a stud in each antistud
    # points (parallel to `antistuds`): +z for top studs and undersides, e.g. +x for a side stud
    stud_axes: Tuple[Axis, ...] = ()
    antistud_axes: Tuple[Axis, ...] = ()
    round_bodies: Tuple[RoundBody, ...] = ()  # spheres and cylinders off the grid (joints)
    joints: Tuple["Joint", ...] = ()          # ball and cup sockets

    def __post_init__(self):
        # Parts built without axes (tests, older code) point everything up
        if len(self.stud_axes) != len(self.studs):
            object.__setattr__(self, "stud_axes", (UP,) * len(self.studs))
        if len(self.antistud_axes) != len(self.antistuds):
            object.__setattr__(self, "antistud_axes", (UP,) * len(self.antistuds))


@dataclass(frozen=True)
class Joint:
    """A ball or cup socket: its pivot is `offset` mm along `axis` from `at` (cells, on a face).
    A ball's axis points from its part to the ball; a cup's out of the cup. `slot`: the direction
    the cup's slot opens toward (the cup part's up by default)."""
    kind: str        # "ball" | "cup"
    at: Point
    axis: Axis
    offset: float
    slot: Axis = (0, 0, 1)


_TOP_KEYS = {"name", "body", "socket", "antistuds"}
_SOCKET_KEYS = {"type", "at", "to", "axis", "offset_mm", "slot"}
_JOINT_TYPES = {"ball", "cup"}
_ANTISTUD_MODES = {"derived", "none"}
_SOCKET_TYPES = {"stud", "antistud", "ball", "cup"}
_BODY_KEYS = {
    "box": {"shape", "size", "at", "studs", "corner_radius"},
    "wedge": {"shape", "size", "at", "studs", "keep", "tall"},
}
_ROUND_KEYS = {
    "sphere": {"shape", "at", "axis", "offset_mm", "diameter_mm", "joint"},
    "cylinder": {"shape", "at", "axis", "offset_mm", "length_mm", "diameter_mm", "end_diameter_mm", "joint"},
}
_STUD_MODES = {"top", "none"}
_TALL = {"+x": (0, 1), "-x": (0, -1), "+y": (1, 1), "-y": (1, -1)}
_CORNERS = ("+x-y", "+x+y", "-x+y", "-x-y")  # the order of Body.radii


def _parse_radii(where: str, value: Any, size: Cell) -> Tuple[float, float, float, float]:
    """corner_radius: one number for all four corners, or a table of corner -> radius (cells)."""
    def number(v, key):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            raise PartError(f"{where}.{key} must be a number >= 0 (cells)")
        return float(v)
    if isinstance(value, dict):
        unknown = set(value) - set(_CORNERS)
        if unknown:
            raise PartError(f"{where}.corner_radius: unknown corners {sorted(unknown)} (use {', '.join(_CORNERS)})")
        radii = tuple(number(value.get(c, 0), f"corner_radius.{c}") for c in _CORNERS)
    else:
        r = number(value, "corner_radius")
        if r > min(size[0], size[1]) / 2:
            raise PartError(f"{where}.corner_radius can be at most half the shorter side")
        radii = (r, r, r, r)
    # Two corners on one side can't round more than that side's length
    a, b, c, d = radii  # +x-y, +x+y, -x+y, -x-y
    if a + b > size[1] or d + c > size[1] or b + c > size[0] or a + d > size[0]:
        raise PartError(f"{where}.corner_radius: two corners on one side round more than its length")
    return radii


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
        radii = _parse_radii(where, body.get("corner_radius", 0), size)
        return Body("box", at, size, studs == "top", radii=radii)
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


def _mm(where: str, value: Any, positive: bool = True) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or (value <= 0 if positive else value < 0):
        raise PartError(f"{where} must be a {'positive ' if positive else ''}number (mm)")
    return float(value)


def _parse_round_body(where: str, body: Dict[str, Any]) -> RoundBody:
    shape = body["shape"]
    unknown = set(body) - _ROUND_KEYS[shape]
    if unknown:
        raise PartError(f"{where}: unknown keys {sorted(unknown)}")
    axis = body.get("axis", "+z")
    if axis not in AXES:
        raise PartError(f"{where}.axis must be one of {sorted(AXES)}")
    joint = body.get("joint", False)
    if not isinstance(joint, bool):
        raise PartError(f"{where}.joint must be true or false")
    length = _mm(f"{where}.length_mm", body.get("length_mm")) if shape == "cylinder" else 0.0
    end = _mm(f"{where}.end_diameter_mm", body["end_diameter_mm"]) / 2 if "end_diameter_mm" in body else 0.0
    return RoundBody(shape, _point(f"{where}.at", body.get("at")), AXES[axis],
                     _mm(f"{where}.offset_mm", body.get("offset_mm", 0), positive=False), length,
                     _mm(f"{where}.diameter_mm", body.get("diameter_mm")) / 2, joint, end)


def _point(where: str, value: Any) -> Point:
    if not (isinstance(value, list) and len(value) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise PartError(f"{where} must be a list of 3 numbers (cells)")
    return (float(value[0]), float(value[1]), float(value[2]))


def _parse_socket(where: str, socket: Any) -> Tuple[str, Segment, Axis]:
    """An explicit socket: its type, position in cells (a segment for an antistud slot) and axis
    (which way the stud points: out of a stud socket, or of a stud sitting in an antistud)."""
    if not isinstance(socket, dict):
        raise PartError(f"{where}: must be a table")
    unknown = set(socket) - _SOCKET_KEYS
    if unknown:
        raise PartError(f"{where}: unknown keys {sorted(unknown)}")
    if socket.get("type") not in _SOCKET_TYPES:
        raise PartError(f"{where}.type must be one of {sorted(_SOCKET_TYPES)}")
    at = _point(f"{where}.at", socket.get("at"))
    axis = socket.get("axis", "+z")
    if axis not in AXES:
        raise PartError(f"{where}.axis must be one of {sorted(AXES)}")
    axis = AXES[axis]
    if socket["type"] in _JOINT_TYPES:
        slot = socket.get("slot", "+z")
        if slot not in AXES or sum(a * b for a, b in zip(AXES[slot], axis)) != 0:
            raise PartError(f"{where}.slot must be one of {sorted(AXES)}, across the axis")
        if "to" in socket:
            raise PartError(f"{where}.to: a joint is a point")
        offset = _mm(f"{where}.offset_mm", socket.get("offset_mm", 0), positive=False)
        return socket["type"], Joint(socket["type"], at, axis, offset, AXES[slot]), axis
    if "offset_mm" in socket or "slot" in socket:
        raise PartError(f"{where}: offset_mm and slot are for ball and cup sockets")
    to = at
    if "to" in socket:
        if socket["type"] != "antistud":
            raise PartError(f"{where}.to: only antistud sockets can be slots")
        to = _point(f"{where}.to", socket["to"])
        if sum((t - a) * n for t, a, n in zip(to, at, axis)) != 0:
            raise PartError(f"{where}: a slot must lie across its axis (at and to at the same height)")
    return socket["type"], (at, to), axis


def _underside_pattern(rules: Sequence[UndersideRule], w: int, d: int) -> str:
    for rule in rules:
        if rule.max_short_side is None or min(w, d) <= rule.max_short_side:
            return rule.slots
    return "none"


def _derived_antistuds(bodies, cell_set, rules: Sequence[UndersideRule]) -> List[Segment]:
    """Slots under each body whose bottom isn't sitting on another body of the part, laid out by
    the profile's underside rules (system specific). A lower wedge's bottom always sits on its
    base, so only boxes and upper wedges count. The "rows" pattern: one slot per row of cells
    along the long side (Y when the sides are equal); a 1xN gets its middle line, a 1x1 a point."""
    out: List[Segment] = []
    for b in bodies:
        if b.kind == "wedge" and b.keep == "lower":
            continue
        (x0, y0, z), (w, d) = b.lo, b.size[:2]
        if z > 0 and all((x, y, z - 1) in cell_set for x in range(x0, x0 + w) for y in range(y0, y0 + d)):
            continue
        if _underside_pattern(rules, w, d) != "rows":
            continue
        along_y = d >= w
        rows = w if along_y else d
        length = d if along_y else w
        for r in range(rows):
            if along_y:
                a, c = (x0 + r + 0.5, y0 + 0.5, float(z)), (x0 + r + 0.5, y0 + length - 0.5, float(z))
            else:
                a, c = (x0 + 0.5, y0 + r + 0.5, float(z)), (x0 + length - 0.5, y0 + r + 0.5, float(z))
            out.append((a, c))
    return out


def part_from_dict(part_id: str, category: str, data: Dict[str, Any],
                   underside: Sequence[UndersideRule] = ()) -> PartDef:
    """A part from its TOML data. `underside`: the profile's rules for derived antistuds (none
    given: no derived antistuds)."""
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
    round_bodies = tuple(_parse_round_body(f"{part_id}: body[{n}]", b) for n, b in enumerate(raw_bodies)
                         if isinstance(b, dict) and b.get("shape") in _ROUND_KEYS)
    bodies = tuple(_parse_body(f"{part_id}: body[{n}]", b) for n, b in enumerate(raw_bodies)
                   if not (isinstance(b, dict) and b.get("shape") in _ROUND_KEYS))
    if not bodies:
        raise PartError(f"{part_id}: needs at least one box or wedge body")
    if len(bodies) > 1 and any(b.rounded for b in bodies):
        raise PartError(f"{part_id}: a rounded box must be the part's only body (for now)")

    # Cells any body touches: the occupancy computation at whole-cell resolution
    cells = tuple(cell for cell, _ in part_regions(bodies, (1, 1, 1)))
    if min(c[0] for c in cells) != 0 or min(c[1] for c in cells) != 0 or min(c[2] for c in cells) != 0:
        raise PartError(f"{part_id}: cells must start at the origin (min corner at 0, 0, 0)")
    stud_tops: List[Cell] = []
    for b in bodies:
        if b.studs:
            top = b.lo[2] + b.size[2] - 1
            # A rounded corner that cuts away a cell's centre takes its stud with it
            stud_tops += [(x, y, top) for x in range(b.lo[0], b.lo[0] + b.size[0])
                          for y in range(b.lo[1], b.lo[1] + b.size[1])
                          if not (b.rounded and outside_rounding(b, x + 0.5, y + 0.5))]
    # A stud covered by another body isn't a stud. Derived studs sit at the cell's top centre.
    cell_set = set(cells)
    studs = [(x + 0.5, y + 0.5, z + 1.0) for x, y, z in dict.fromkeys(stud_tops)
             if (x, y, z + 1) not in cell_set]
    # Explicit stud sockets go anywhere, e.g. on a cell boundary (single-stud parts)
    raw_sockets = data.get("socket", [])
    if not isinstance(raw_sockets, list):
        raise PartError(f"{part_id}: 'socket' must be an array of tables ([[socket]])")
    sockets = [_parse_socket(f"{part_id}: socket[{n}]", s) for n, s in enumerate(raw_sockets)]
    joints = tuple(seg for kind, seg, _ in sockets if kind in _JOINT_TYPES)
    sockets = [s for s in sockets if s[0] not in _JOINT_TYPES]
    stud_axes = [UP] * len(studs) + [axis for kind, _, axis in sockets if kind == "stud"]
    studs += [seg[0] for kind, seg, _ in sockets if kind == "stud"]
    mode = data.get("antistuds", "derived")
    if mode not in _ANTISTUD_MODES:
        raise PartError(f"{part_id}: 'antistuds' must be one of {sorted(_ANTISTUD_MODES)}")
    derived = _derived_antistuds(bodies, cell_set, underside) if mode == "derived" else []
    antistuds = tuple(derived + [seg for kind, seg, _ in sockets if kind == "antistud"])
    antistud_axes = tuple([UP] * len(derived) + [axis for kind, _, axis in sockets if kind == "antistud"])
    return PartDef(part_id, data["name"], category, bodies, cells, tuple(studs), antistuds,
                   tuple(stud_axes), antistud_axes, round_bodies, joints)


def _walk(folder: Traversable, category: List[str], profile: Profile, out: Dict[str, PartDef]) -> None:
    profile_id = profile.id
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if entry.is_dir():
            _walk(entry, category + [entry.name], profile, out)
        elif entry.name.endswith(".toml"):
            stem = entry.name[:-len(".toml")]
            if not ID_PATTERN.fullmatch(stem):
                raise PartError(f"part file {entry.name!r}: names may only use a-z, 0-9 and _ (they become ids)")
            part_id = f"{profile_id}:{stem}"
            if part_id in out:
                raise PartError(f"duplicate part id {part_id}")
            with entry.open("rb") as f:
                try:
                    data = tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    raise PartError(f"{part_id}: {e}") from None
            out[part_id] = part_from_dict(part_id, "/".join(category), data, profile.underside)


def load_builtin_library(profile: Union[Profile, str]) -> Dict[str, PartDef]:
    """All built-in parts for a profile (or a built-in profile's id), keyed by part id."""
    if isinstance(profile, str):
        profile = load_builtin_profile(profile)
    root = resources.files("brickbuilder") / "parts" / profile.id
    parts: Dict[str, PartDef] = {}
    if root.is_dir():
        _walk(root, [], profile, parts)
    return parts
