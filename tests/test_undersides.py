"""Where a stud from below fits under each kind of part (antistud slots and points)."""
import pytest

from brickbuilder.core.parts import PartError, load_builtin_library, part_from_dict


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


def segs(library, name):
    return sorted(library[f"nanoblock:{name}"].antistuds)


def seg(a, b, z=0.0):
    return ((a[0], a[1], z), (b[0], b[1], z))


@pytest.mark.parametrize("name, expected", [
    ("brick_1x1", [seg((0.5, 0.5), (0.5, 0.5))]),                                  # a point
    ("brick_1x4", [seg((0.5, 0.5), (0.5, 3.5))]),                                  # one long slot
    ("brick_2x4", [seg((0.5, 0.5), (0.5, 3.5)), seg((1.5, 0.5), (1.5, 3.5))]),     # one per row
    ("brick_2x2", [seg((0.5, 0.5), (0.5, 1.5)), seg((1.5, 0.5), (1.5, 1.5))]),     # equal sides: along Y
    ("flat_1x2", [seg((0.5, 0.5), (0.5, 1.5))]),                                   # same as the brick
    ("brick_1x2_1_stud", [seg((0.5, 0.5), (0.5, 1.5))]),
    ("brick_1x3_2_studs", [seg((0.5, 0.5), (0.5, 2.5))]),
    ("brick_2x2_l", [seg((0.5, 0.5), (1.5, 0.5)), seg((0.5, 1.5), (0.5, 1.5))]),          # 1x2 along X + 1x1
    ("brick_2x3_t", [seg((0.5, 0.5), (0.5, 2.5)), seg((1.5, 1.5), (1.5, 1.5))]),
    ("slope_1x2_wedge_1x1", [seg((0.5, 0.5), (0.5, 1.5))]),                       # base box only
    ("slope_2x4_wedge_1x1", [seg((0.5, 0.5), (3.5, 0.5)), seg((0.5, 1.5), (3.5, 1.5))]),  # long side is X
    ("slope_1x2_wedge_1x1_inverted", [seg((0.5, 0.5), (0.5, 0.5)), seg((0.5, 1.5), (0.5, 1.5))]),  # wall between
    ("slope_1x2_wedge_1x2_inverted", [seg((0.5, 0.5), (0.5, 0.5)), seg((0.5, 1.5), (0.5, 1.5))]),
    ("round_1x3", [seg((0.5, 0.5), (0.5, 2.5))]),
    ("round_2x2_fan", [seg((0.5, 0.5), (0.5, 0.5)), seg((0.5, 1.5), (0.5, 1.5)), seg((1.5, 0.5), (1.5, 0.5))]),
    ("plate_10x10", []),
])
def test_undersides(library, name, expected):
    assert segs(library, name) == sorted(expected)


def test_round_2x2_diagonal_slots(library):
    slots = segs(library, "round_2x2")
    assert seg((1, 1), (1, 1)) in slots
    diagonal = [s for s in slots if s[0] != s[1]]
    assert len(diagonal) == 4
    for (ax, ay, _), (bx, by, _) in diagonal:
        assert abs(abs(ax - 1) - 0.5) < 1e-9 and abs(abs(ay - 1) - 0.5) < 1e-9       # from a cell centre
        assert abs(((bx - 1) ** 2 + (by - 1) ** 2) ** 0.5 - 1) < 1e-5                 # to the rim
        assert abs(abs(bx - 1) - abs(by - 1)) < 1e-9                                  # along the diagonal


def test_slot_sockets_validated():
    with pytest.raises(PartError, match="only antistud"):
        part_from_dict("t:s", "", {"name": "S", "body": [{"shape": "box", "size": [1, 2, 1]}],
                                   "socket": [{"type": "stud", "at": [0, 0, 1], "to": [0, 1, 1]}]})
    with pytest.raises(PartError, match="level"):
        part_from_dict("t:s", "", {"name": "S", "body": [{"shape": "box", "size": [1, 2, 1]}],
                                   "socket": [{"type": "antistud", "at": [0, 0, 0], "to": [0, 1, 1]}]})
    with pytest.raises(PartError, match="antistuds"):
        part_from_dict("t:s", "", {"name": "S", "antistuds": "some", "body": [{"shape": "box", "size": [1, 1, 1]}]})
