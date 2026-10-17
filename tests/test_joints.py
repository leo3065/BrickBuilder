"""Ball joints: round bodies, ball / cup sockets, joint contacts and the clash between them."""
import glm
import pytest

from brickbuilder.core.connections import within_limits
from brickbuilder.core.history import History
from brickbuilder.core.model import Model, decompose, turn_about
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture
def model():
    profile = load_builtin_profile()
    return Model(profile, load_builtin_library(profile))


def lib(model, name):
    return model.library[f"nanoblock:{name}"]


def test_joint_parts_load(model):
    cup, ball = lib(model, "joint_1x2_cup"), lib(model, "joint_1x2_ball")
    assert [j.kind for j in cup.joints] == ["cup"] and [j.kind for j in ball.joints] == ["ball"]
    assert [rb.kind for rb in ball.round_bodies] == ["cylinder", "sphere"]
    assert cup.cells == lib(model, "brick_1x2").cells          # round bodies stay off the grid
    assert len(cup.studs) == 2 and len(cup.antistuds) == 1     # like the plain brick
    placed = model.add_part(cup, (0, 0, 0), 0, "red")
    kind, pivot, axis, slot = placed.joints[0]
    # Pivot 4.25 mm out from the +x face (x = 2 mm), on the line between the cells, at mid-height
    assert glm.distance(pivot, glm.vec3(6.25, 2.0, 3.125 / 2)) < 1e-5 and glm.distance(axis, glm.vec3(1, 0, 0)) < 1e-6
    assert placed.box[1].x > 2.0 + 5.9 - 1e-4                    # the cup counts in the box


def straight_on(model, h, cup):
    """A 1x2 ball part placed straight on a cup: ball centre on the pivot, arm into the cup,
    tops the same way."""
    kind, pivot, axis, slot = cup.joints[0]
    ball = lib(model, "joint_1x2_ball")
    # Ball part's own grid: its +x (the ball's axis) turned to -cup axis = a half turn about Z
    m = turn_about(glm.vec3(0), glm.vec3(0, 0, 1), 180)
    local_pivot = glm.vec3(2.0 + 3.75, 2.0, 3.125 / 2)  # its pivot: 2 mm face + 3.75 mm, mid cell line
    grid = glm.translate(glm.mat4(1.0), pivot - glm.vec3(m * glm.vec4(local_pivot, 1.0))) * m
    return h.add_part_in_new_frame(ball, (0, 0, 0), 0, "white", 0, *decompose(grid))


def test_ball_in_cup_connects_and_may_overlap(model):
    h = History(model)
    cup = h.add_part(lib(model, "joint_1x2_cup"), (0, 0, 0), 0, "red")
    ball = straight_on(model, h, cup)
    assert ball is not None, "a joined ball and cup may overlap"
    assert model.connections()[ball.id] == {cup.id}
    assert glm.distance(ball.joints[0][1], cup.joints[0][1]) < 1e-4
    # 8 mm between the faces when straight
    assert abs(min(p.x for s in ball.solids[:1] for f in s for p in f) - 2.0 - 8.0) < 1e-4
    assert model.collisions() == set()


def test_a_ball_not_in_the_cup_clashes(model):
    h = History(model)
    cup = h.add_part(lib(model, "joint_1x2_cup"), (0, 0, 0), 0, "red")
    # A plain brick where the cup sticks out: refused
    assert not model.can_place(lib(model, "brick_1x1"), (2, 1, 0), 0)
    ball = straight_on(model, h, cup)
    # Pull the ball part 1 mm back along the axis: no longer joined, so its ball hits the cup
    pulled = glm.translate(glm.mat4(1.0), glm.vec3(-1.0, 0, 0))
    assert model.moved_overlaps({ball.id}, pulled) is not None


def test_joint_limits():
    cup_axis, slot = glm.vec3(1, 0, 0), glm.vec3(0, 0, 1)
    straight = glm.vec3(-1, 0, 0)
    tilt = lambda deg, about: glm.vec3(glm.mat4_cast(glm.angleAxis(glm.radians(deg), about)) * glm.vec4(straight, 0))
    assert within_limits(straight, cup_axis, slot, 30, 90)
    assert within_limits(tilt(25, glm.vec3(0, 0, 1)), cup_axis, slot, 30, 90)      # sideways, in the cone
    assert not within_limits(tilt(40, glm.vec3(0, 0, 1)), cup_axis, slot, 30, 90)  # sideways, too far
    assert within_limits(tilt(80, glm.vec3(0, 1, 0)), cup_axis, slot, 30, 90)      # up, in the slot
    assert not within_limits(tilt(100, glm.vec3(0, 1, 0)), cup_axis, slot, 30, 90)
