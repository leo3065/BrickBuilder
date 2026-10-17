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


def side_frame(model, stud: glm.vec3, axis: glm.vec3):
    """A frame whose Z is `axis` and whose Y is world up, with its origin on the stud: a grid
    for parts built on a side stud (cell (0, 0)'s centre on the stud, layer 0 against the face)."""
    from brickbuilder.core.model import decompose
    z = glm.normalize(axis)
    y = glm.vec3(0, 0, 1)
    x = glm.cross(y, z)
    m = glm.mat4(glm.vec4(x, 0), glm.vec4(y, 0), glm.vec4(z, 0), glm.vec4(stud, 1))
    return model.add_frame(0, *decompose(m))


def test_part_on_a_side_stud_turns_about_it(model):
    from brickbuilder.core.history import History
    from brickbuilder.core.model import turn_about
    from brickbuilder.core.motion import plan_turn
    side = model.add_part(part_from_dict("t:side", "", SIDE, model.profile.underside), (0, 0, 0), 0, "red")
    stud, axis = side.studs[-1], side.stud_axes[-1]
    frame = side_frame(model, stud, axis)
    brick = model.add_part(model.library["nanoblock:brick_1x2"], (0, 0, 0), 0, "white", frame=frame.id)
    assert brick is not None and model.connections()[brick.id] == {side.id}

    plan = plan_turn(model, {brick.id})
    assert plan.kind == "turn" and abs(abs(glm.dot(plan.axis, glm.vec3(1, 0, 0))) - 1) < 1e-6
    assert glm.distance(plan.pivot, stud) < 1e-3

    h = History(model)
    assert h.move_parts({brick.id}, turn_about(plan.pivot, plan.axis, 30)) is None
    assert model.connections()[brick.id] == {side.id}     # still on the stud
    moved = model.parts[brick.id]
    assert moved.frame == frame.id                         # its own grid turned, not merged
