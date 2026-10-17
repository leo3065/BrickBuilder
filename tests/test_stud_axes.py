"""Studs and slots have a direction: side studs, and contacts that must point the right way."""
import glm
import pytest

from brickbuilder.core.model import Model
from brickbuilder.core.parts import PartError, load_builtin_library, part_from_dict
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture
def model():
    profile = load_builtin_profile()
    return Model(profile, load_builtin_library(profile))


SIDE = {"name": "Side", "body": [{"shape": "box", "size": [1, 1, 1]}],
        "socket": [{"type": "stud", "at": [1.0, 0.5, 0.28], "axis": "+x"}]}


def test_socket_axes():
    part = part_from_dict("t:side", "", SIDE)
    assert part.studs[-1] == (1.0, 0.5, 0.28) and part.stud_axes == ((0, 0, 1), (1, 0, 0))
    with pytest.raises(PartError, match="axis"):
        part_from_dict("t:x", "", {**SIDE, "socket": [{"type": "stud", "at": [1, 0.5, 0.5], "axis": "x"}]})
    # A slot lies across its axis: for +x that means constant x
    ok = part_from_dict("t:s", "", {"name": "S", "body": [{"shape": "box", "size": [1, 2, 1]}], "antistuds": "none",
                                    "socket": [{"type": "antistud", "at": [0, 0.5, 0.5], "to": [0, 1.5, 0.5],
                                                "axis": "+x"}]})
    assert ok.antistud_axes == ((1, 0, 0),)


def test_side_stud_turns_with_the_part(model):
    side = part_from_dict("t:side", "", SIDE)
    placed = model.add_part(side, (0, 0, 0), 1, "red")      # a quarter turn: +x becomes +y
    assert glm.distance(placed.stud_axes[-1], glm.vec3(0, 1, 0)) < 1e-6
    assert glm.distance(placed.stud_axes[0], glm.vec3(0, 0, 1)) < 1e-6


def test_contacts_need_matching_axes(model):
    """A stud on a slot only connects if it points the way the slot expects: a side stud that
    merely touches an underside slot doesn't count."""
    from types import SimpleNamespace
    from brickbuilder.core.connections import iter_contacts
    stud = SimpleNamespace(id=1, studs=[glm.vec3(2, 2, 1.5)], stud_axes=[glm.vec3(1, 0, 0)])
    for slot_axis, expected in ((glm.vec3(0, 0, 1), 0), (glm.vec3(1, 0, 0), 1)):
        slot = SimpleNamespace(id=2, antistuds=[(glm.vec3(2, 2, 1.5), glm.vec3(2, 6, 1.5))],
                               antistud_axes=[slot_axis])
        assert len(list(iter_contacts(model.profile, [stud], [slot]))) == expected
