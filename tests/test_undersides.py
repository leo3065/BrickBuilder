"""Where a stud from below fits under each kind of part (antistud slots and points)."""
import pytest

from brickbuilder.core.parts import PartError, load_builtin_library, part_from_dict
from brickbuilder.core.profile import load_builtin_profile


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
    ("plate_10x10", [seg((0.5, 0.5), (9.5, 0.5)), seg((9.5, 0.5), (9.5, 9.5)),       # four 9-cell slots
                     seg((9.5, 9.5), (0.5, 9.5)), seg((0.5, 9.5), (0.5, 0.5))]),      # on the sides
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
    with pytest.raises(PartError, match="across its axis"):
        part_from_dict("t:s", "", {"name": "S", "body": [{"shape": "box", "size": [1, 2, 1]}],
                                   "socket": [{"type": "antistud", "at": [0, 0, 0], "to": [0, 1, 1]}]})
    with pytest.raises(PartError, match="antistuds"):
        part_from_dict("t:s", "", {"name": "S", "antistuds": "some", "body": [{"shape": "box", "size": [1, 1, 1]}]})


def test_underside_rules_come_from_the_profile():
    """How undersides take studs is system specific: the profile's [[underside]] rules decide,
    parts only override with explicit sockets."""
    from brickbuilder.core.profile import UndersideRule
    body = {"name": "B", "body": [{"shape": "box", "size": [2, 4, 1]}]}
    rows = (UndersideRule(2, "rows"), UndersideRule(None, "none"))
    nanoblock = (UndersideRule(2, "rows"), UndersideRule(None, "perimeter"))
    assert len(part_from_dict("t:b", "", body, rows).antistuds) == 2          # one slot per row
    assert part_from_dict("t:b", "", body, (UndersideRule(1, "rows"),)).antistuds == ()  # too wide
    assert part_from_dict("t:b", "", body).antistuds == ()                    # no rules: none
    # The built-in Nanoblock profile carries the measured rules
    profile = load_builtin_profile()
    assert profile.underside == nanoblock


def test_bad_underside_rules():
    from brickbuilder.core.profile import ProfileError, profile_from_dict
    data = {"id": "x", "name": "X", "cell": [4, 4, 3], "subdiv": [2, 2, 1],
            "stud": {"diameter": 2, "height": 2}, "palette": {"red": {"name": "Red", "rgb": "#ff0000"}}}
    for bad in ([{"slots": "tubes"}], [{"max_short_side": 0, "slots": "rows"}], [{"slots": "rows", "x": 1}], {}):
        with pytest.raises(ProfileError):
            profile_from_dict({**data, "underside": bad})
    assert profile_from_dict(data).underside == ()


def test_base_plate_grips_on_its_sides_and_lets_studs_into_the_middle(library):
    from brickbuilder.core.model import Model
    plate = library["nanoblock:plate_10x10"]
    assert plate.hollows == (((1.5, 1.5, 0.0), (8.5, 1.5, 0.0), (1.5, 8.5, 0.0)),)   # a 7x7 middle
    profile = load_builtin_profile()
    model = Model(profile, library)
    brick = library["nanoblock:brick_1x1"]
    corner = model.add_part(brick, (0, 0, 0), 0, "red")          # its stud under the plate's corner cell
    middle = model.add_part(brick, (8, 8, 0), 0, "red")          # its stud at (4.5, 4.5) in plate cells
    assert model.can_place(plate, (0, 0, 1), 0)
    placed = model.add_part(plate, (0, 0, 1), 0, "white")
    links = model.connections()
    assert corner.id in links[placed.id] and middle.id not in links[placed.id]   # the middle doesn't grip
    # Between a side slot and the middle (a stud at (1.0, 2.0) in plate cells): blocked by the ribs
    model.add_part(brick, (31, 3, 0), 0, "red")
    assert not model.can_place(plate, (30, 0, 1), 0)
