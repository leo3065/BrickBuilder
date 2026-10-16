import json
from pathlib import Path

import glm
import pytest

from brickbuilder.core import picking
from brickbuilder.core.model import (Model, ModelError, anchor_cells, default_anchor_index, footprint, origin_for_anchor,
                                     placement_target,
                                     v1_color_to_palette)
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def profile():
    return load_builtin_profile()


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.fixture
def model(profile, library):
    return Model(profile, library)


def part(library, size):
    return library[f"nanoblock:brick_{size}"]


def cells_of(profile, subcells):
    """Collapse sub-cells back to whole cells (for readable assertions)."""
    nx, ny, nz = profile.subdiv
    return sorted({(x // nx, y // ny, z // nz) for x, y, z in subcells})


@pytest.mark.parametrize("turns, expected", [
    (0, [(0, 0, 0), (0, 1, 0)]),     # 1x2 along +Y
    (1, [(-2, 0, 0), (-1, 0, 0)]),   # turned CCW about the origin corner: along -X
    (2, [(-1, -2, 0), (-1, -1, 0)]),
    (3, [(0, -1, 0), (1, -1, 0)]),
])
def test_footprint_rotates_about_origin_corner(profile, library, turns, expected):
    subs = footprint(profile, part(library, "1x2"), (0, 0, 0), turns)
    assert len(subs) == 2 * 4  # 2 cells x (2x2x1 sub-cells)
    assert cells_of(profile, subs) == expected


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
@pytest.mark.parametrize("anchor_index", [0, 1, 2])
def test_anchor_cell_stays_on_target(profile, library, turns, anchor_index):
    # Whatever the rotation, the chosen anchor cell of a 1x3 lands on the target cell (5, -3, 2)
    p = part(library, "1x3")
    anchor = anchor_cells(p)[anchor_index]
    target = profile.cell_to_sub((5, -3, 2))
    pos = origin_for_anchor(profile, anchor, turns, target)
    cells = cells_of(profile, footprint(profile, p, pos, turns))
    assert (5, -3, 2) in cells and len(cells) == 3


def test_anchor_cells_order_for_1x3(library):
    # End, middle, other end: cycling goes along the brick
    assert anchor_cells(part(library, "1x3")) == [(0, 0, 0), (0, 1, 0), (0, 2, 0)]


@pytest.mark.parametrize("size, expected", [
    ("1x1", (0, 0, 0)),
    ("1x2", (0, 1, 0)),   # tie -> +Y
    ("1x3", (0, 1, 0)),   # true middle
    ("2x2", (1, 1, 0)),   # four-way tie -> +X, then +Y
    ("2x3", (1, 1, 0)),   # middle row, tie in X -> +X
    ("2x4", (1, 2, 0)),
])
def test_default_anchor_is_nearest_centre(library, size, expected):
    p = part(library, size)
    assert anchor_cells(p)[default_anchor_index(p)] == expected


def test_overlap_refused_and_occupancy(model, library):
    a = model.add_part(part(library, "2x4"), (0, 0, 0), 0, "red")
    assert a is not None and len(model.occupancy) == 32
    # 1x1 inside the 2x4's footprint, same layer -> refused; one layer up -> fine
    assert model.add_part(part(library, "1x1"), (2, 4, 0), 0, "red") is None
    assert model.add_part(part(library, "1x1"), (2, 4, 1), 0, "red") is not None
    # Half-cell offset overlapping the 2x4's edge is refused too
    assert not model.can_place(part(library, "1x1"), (3, -1, 0), 0)
    model.remove_part(a.id)
    assert len(model.occupancy) == 4 and model.parts_at((0, 0, 0)) == []


def test_part_box_world_space(model, library):
    p = model.add_part(part(library, "2x4"), (0, 0, 0), 1, "red")
    lo, hi = p.box
    # Turned once: 4 cells along -X, 2 along +Y, origin corner at world (-2, -2, 0)
    assert tuple(lo) == (-18.0, -2.0, 0.0) and tuple(hi) == (-2.0, 6.0, 3.125)


def test_stud_positions_follow_rotation(model, library):
    p = model.add_part(part(library, "1x2"), (0, 0, 0), 1, "red")
    # Turned once: cells (-2, 0) and (-1, 0) -> stud centres at cell-space x -2 and -1, y 0
    assert sorted(tuple(s) for s in p.studs) == [(-8.0, 0.0, 3.125), (-4.0, 0.0, 3.125)]
    # Half-offset 1x1 one layer up: stud centre sits on the cell boundary
    q = model.add_part(part(library, "1x1"), (1, 1, 1), 0, "red")
    assert [tuple(s) for s in q.studs] == [(2.0, 2.0, 6.25)]


def test_off_centre_stud_follows_rotation(model, library):
    one_stud = library["nanoblock:brick_1x2_1_stud"]
    # Unturned at the origin: the stud is between the two cells, at world (0, 2), on top
    assert [tuple(s) for s in model.add_part(one_stud, (0, 0, 0), 0, "red").studs] == [(0.0, 2.0, 3.125)]
    # Turned once about the origin corner (world (-2, -2)): the part now runs along -X
    assert [tuple(s) for s in model.add_part(one_stud, (0, 0, 1), 1, "red").studs] == [(-6.0, 0.0, 6.25)]


def test_save_roundtrip_including_half_offset(model, library, profile, tmp_path):
    model.add_part(part(library, "2x4"), (0, 0, 0), 1, "cobalt_blue")
    model.add_part(part(library, "1x2"), (3, 1, 1), 0, "red")  # half-cell offset in X and Y
    path = tmp_path / "m.json"
    model.save_to_file(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 4 and data["profile"] == "nanoblock"
    assert data["parts"][1]["pos"] == [1.5, 0.5, 1]

    loaded = Model(profile, library)
    loaded.load_from_file(str(path))
    assert loaded.to_dict() == model.to_dict()
    assert not loaded.modified
    # New ids continue after the loaded ones
    assert loaded.add_part(part(library, "1x1"), (10, 10, 0), 0, "red").id == 3


def test_failed_save_keeps_old_file(model, library, tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    path.write_text("old contents", encoding="utf-8")
    model.add_part(part(library, "1x1"), (0, 0, 0), 0, "red")

    def boom(*_):
        raise OSError("disk full")
    monkeypatch.setattr("brickbuilder.core.model.os.replace", boom)
    with pytest.raises(OSError):
        model.save_to_file(str(path))
    assert path.read_text(encoding="utf-8") == "old contents"
    assert not (tmp_path / "m.json.tmp").exists()
    assert model.modified


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.update(version=99), "version"),
    (lambda d: d.update(profile="lego"), "profile"),
    (lambda d: d["parts"][0].update(part="nanoblock:nope"), "unknown part"),
    (lambda d: d["parts"][0].update(color="chartreuse"), "unknown color"),
    (lambda d: d["parts"][0].update(pos=[0.25, 0, 0]), "sub-grid"),
    (lambda d: d["parts"][0].update(turns=4), "turns"),
    (lambda d: d["parts"][1].update(pos=[0, 0, 0]), "overlaps"),
    (lambda d: d["parts"][1].update(id=1), "duplicate"),
    (lambda d: d.update(frames=[{"id": 0}, {"id": 1}]), "needs id, parent"),
    (lambda d: d.update(frames=[{"id": 1}]), "root frame"),
])
def test_bad_saves_rejected_and_model_untouched(model, library, mutate, message):
    model.add_part(part(library, "1x1"), (0, 0, 0), 0, "red")
    model.add_part(part(library, "1x1"), (0, 0, 1), 0, "red")
    data = model.to_dict()
    before = json.dumps(data)
    mutate(data)
    with pytest.raises(ModelError, match=message):
        model.from_dict(data)
    assert json.dumps(model.to_dict()) == before


def test_v1_load(model):
    v1 = {"version": 1, "bricks": [
        {"x": 0, "y": 0, "z": 0, "r": 0.800000011920929, "g": 0.10000000149011612, "b": 0.10000000149011612},
        {"x": 0, "y": 0, "z": 1, "r": 0.10000000149011612, "g": 0.30000001192092896, "b": 0.800000011920929},
        {"x": 3, "y": -2, "z": 0, "r": 0.0, "g": 0.0, "b": 0.0},
    ]}
    model.from_dict(v1)
    parts = sorted(model.parts.values(), key=lambda p: p.id)
    assert [p.color for p in parts] == ["red", "cobalt_blue", "black"]  # last one: nearest match
    assert all(p.part.id == "nanoblock:brick_1x1" for p in parts)
    assert model.to_dict()["parts"][2]["pos"] == [3, -2, 0]


def test_v1_color_mapping_falls_back_to_nearest(profile):
    # Nearest *opaque* color: v1 had no translucent bricks, even though "clear" is pure white
    assert v1_color_to_palette(profile, (1.0, 1.0, 1.0)) == "white"


@pytest.mark.parametrize("sample", sorted((REPO / "test_model").glob("*.json")), ids=lambda p: p.name)
def test_sample_saves_load(model, sample):
    model.load_from_file(str(sample))
    assert model.parts


def test_picking_multicell_part_target(model, library, profile):
    model.add_part(part(library, "2x4"), (0, 0, 0), 0, "red")  # cells x 0..1, y 0..3
    # Straight down onto cell (1, 2): the target is the cell above that spot
    ray = picking.Ray(glm.vec3(4.0, 8.5, 100), glm.vec3(0, 0, -1))
    hit, normal, point = picking.intersect_model(ray, model)
    assert hit is not None
    assert placement_target(profile, point, normal, half=False) == profile.cell_to_sub((1, 2, 1))
    # From the +X side at cell y=3: the cell beside it
    ray = picking.Ray(glm.vec3(100, 12.0, 1.0), glm.vec3(-1, 0, 0))
    hit, normal, point = picking.intersect_model(ray, model)
    assert placement_target(profile, point, normal, half=False) == profile.cell_to_sub((2, 3, 0))


@pytest.mark.parametrize("point, normal, half, expected", [
    # Ground: whole cells vs half-cell steps (cell 0 spans x -2..2; centres every 2 mm when half)
    ((1.1, 0.0, 0.0), (0, 0, 1), False, (0, 0, 0)),
    ((1.1, 0.0, 0.0), (0, 0, 1), True, (1, 0, 0)),     # centre at x=2 is nearest
    ((0.9, 0.0, 0.0), (0, 0, 1), True, (0, 0, 0)),     # centre at x=0 is nearest
    ((-3.2, 5.3, 0.0), (0, 0, 1), True, (-2, 3, 0)),   # nearest centres: x=-4, y=6
    # -X side face of a part whose face is at x=-2: flush against it, whole or half in Y
    ((-2.0, 4.4, 1.0), (-1, 0, 0), False, (-2, 2, 0)),
    ((-2.0, 4.4, 1.0), (-1, 0, 0), True, (-2, 2, 0)),
    ((-2.0, 5.1, 1.0), (-1, 0, 0), True, (-2, 3, 0)),
    # Bottom face: one layer below
    ((0.0, 0.0, 0.0), (0, 0, -1), True, (0, 0, -1)),
    # +X face of a half-offset part (face at x=0, mid-cell): flush at sub-cell 1; Z stays whole
    ((0.0, 0.0, 4.0), (1, 0, 0), True, (1, 0, 1)),
])
def test_placement_target(profile, point, normal, half, expected):
    assert placement_target(profile, glm.vec3(*point), glm.vec3(*normal), half) == expected


def test_picking_hits_part_at_origin(model, library):
    model.add_part(part(library, "1x1"), (0, 0, 0), 0, "red")
    hit, _, _ = picking.intersect_model(picking.Ray(glm.vec3(0, 0, 100), glm.vec3(0, 0, -1)), model)
    assert hit is not None
