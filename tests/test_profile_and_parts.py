import re

import glm
import pytest

from brickbuilder.core.parts import PartError, load_builtin_library, part_from_dict
from brickbuilder.core.profile import ProfileError, load_builtin_profile, profile_from_dict


@pytest.fixture(scope="module")
def profile():
    return load_builtin_profile()


def minimal_profile(**overrides):
    data = {
        "id": "x", "name": "X", "cell": [4, 4, 3], "subdiv": [2, 2, 1],
        "stud": {"diameter": 2, "height": 1},
        "palette": {"red": {"name": "Red", "rgb": "#ff0000"}},
    }
    data.update(overrides)
    return data


def test_builtin_profile(profile):
    assert profile.id == "nanoblock"
    assert tuple(profile.cell) == (4.0, 4.0, 3.125)
    assert len(profile.palette) == 45
    assert profile.palette["cobalt_blue"].name == "Cobalt Blue"
    assert profile.palette["clear_red"].clear and not profile.palette["red"].clear
    assert profile.palette["clear_red"].alpha == 0.75 and profile.palette["red"].alpha == 1.0
    assert profile.palette["clear"].alpha == 0.5 and tuple(profile.palette["clear"].rgb) == (1.0, 1.0, 1.0)


def test_grid_to_world(profile):
    lo, hi = profile.cell_box(glm.ivec3(2, -1, 3))
    assert tuple(lo) == (6.0, -6.0, 9.375) and tuple(hi) == (10.0, -2.0, 12.5)
    # Sub-cell 1 is the upper half of cell 0 in X/Y
    assert tuple(profile.sub_to_world((1, 1, 0))) == (0.0, 0.0, 0.0)
    assert profile.world_to_cell(glm.vec3(5.9, -2.1, 3.2)) == glm.ivec3(1, -1, 1)
    assert profile.world_to_cell(glm.vec3(0, 0, -0.1)).z == -1


@pytest.mark.parametrize("overrides, message", [
    ({"cell": [4, 4]}, "cell"),
    ({"cell": [4, -4, 3]}, "positive"),
    ({"subdiv": [2, 1, 1]}, "subdiv"),
    ({"palette": {}}, "palette"),
    ({"palette": {"red": {"name": "Red", "rgb": "red"}}}, "rrggbb"),
    ({"stud": {"height": 1}}, "stud.diameter"),
    ({"palette": {"c": {"name": "C", "rgb": "#ffffff", "alpha": 1.5}}}, "alpha"),
    ({"palette": {"Blue×": {"name": "B", "rgb": "#0000ff"}}}, "a-z"),
    ({"id": "Nano block"}, "a-z"),
])
def test_bad_profiles_rejected(overrides, message):
    with pytest.raises(ProfileError, match=message):
        profile_from_dict(minimal_profile(**overrides))


def test_starter_library():
    lib = load_builtin_library("nanoblock")
    plain = [k for k in lib if re.fullmatch(r"nanoblock:brick_\d+x\d+", k)]
    sizes = sorted(k.split("_")[1] for k in plain)
    assert sizes == sorted(["1x1", "1x2", "1x3", "1x4", "1x6", "2x2", "2x3", "2x4", "2x8"])
    b = lib["nanoblock:brick_2x4"]
    assert b.name == "Brick 2×4" and b.category == "Bricks" and b.ldraw == "NB204.dat"
    assert len(b.cells) == 8 and len(b.studs) == 8
    assert {c[0] for c in b.cells} == {0, 1} and {c[1] for c in b.cells} == {0, 1, 2, 3}


def test_part_validation():
    with pytest.raises(PartError, match="reserved"):
        part_from_dict("t:p", "", {"name": "P", "params": {}, "body": []})
    with pytest.raises(PartError, match="unknown keys"):
        part_from_dict("t:p", "", {"name": "P", "colour": 1, "body": [{"shape": "box", "size": [1, 1, 1]}]})
    with pytest.raises(PartError, match="unsupported shape"):
        part_from_dict("t:p", "", {"name": "P", "body": [{"shape": "slope", "size": [1, 2, 1]}]})
    with pytest.raises(PartError, match="origin"):
        part_from_dict("t:p", "", {"name": "P", "body": [{"shape": "box", "size": [1, 1, 1], "at": [1, 0, 0]}]})


def test_studs_derived_and_hidden_by_bodies():
    # A 2x1 base with a 1x1 on top of its first cell: studs on the top brick and the uncovered base cell.
    p = part_from_dict("t:p", "", {"name": "P", "body": [
        {"shape": "box", "size": [2, 1, 1]},
        {"shape": "box", "size": [1, 1, 1], "at": [0, 0, 1]},
    ]})
    assert sorted(p.studs) == [(0, 0, 1), (1, 0, 0)]
    flat = part_from_dict("t:f", "", {"name": "F", "body": [{"shape": "box", "size": [1, 2, 1], "studs": "none"}]})
    assert flat.studs == ()


def test_base_plates():
    lib = load_builtin_library("nanoblock")
    for size in (10, 20):
        plate = lib[f"nanoblock:plate_{size}x{size}"]
        assert plate.category == "Plates"
        assert len(plate.cells) == size * size and {c[2] for c in plate.cells} == {0}  # brick height
        assert len(plate.studs) == size * size                                        # every top cell


def test_flat_bricks():
    lib = load_builtin_library("nanoblock")
    for size, cells in (("1x2", 2), ("2x4", 8)):
        flat = lib[f"nanoblock:flat_{size}"]
        assert flat.category == "Bricks" and len(flat.cells) == cells
        assert {c[2] for c in flat.cells} == {0}   # brick height
        assert flat.studs == ()                    # no studs


def test_l_and_t_bricks():
    lib = load_builtin_library("nanoblock")
    l_shape = lib["nanoblock:brick_2x2_l"]
    assert sorted(l_shape.cells) == [(0, 0, 0), (0, 1, 0), (1, 0, 0)] and len(l_shape.studs) == 3
    t_shape = lib["nanoblock:brick_2x3_t"]
    assert sorted(t_shape.cells) == [(0, 0, 0), (0, 1, 0), (0, 2, 0), (1, 1, 0)] and len(t_shape.studs) == 4
