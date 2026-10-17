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


@pytest.mark.parametrize("cup_name, ball_name", [("joint_1x2_cup", "joint_1x2_ball"), ("joint_2x2_cup", "joint_2x2_ball"),
                                                 ("joint_1x2_cup", "joint_2x2_ball")])
def test_joint_grid_puts_a_part_straight_on_a_joint(model, cup_name, ball_name):
    h = History(model)
    cup = h.add_part(lib(model, cup_name), (0, 0, 0), 0, "red")
    ball = lib(model, ball_name)
    for turns in (0, 1):  # whichever way the part was turned, the joint decides
        grid = model.joint_grid(ball, turns, 0, cup.joints[0], glm.vec3(0, 0, 1))
        assert model.turned_placement_problem(ball, (0, 0, 0), turns, grid) is None
    placed = h.add_part_in_new_frame(ball, (0, 0, 0), 0, "white", 0,
                                     *decompose(model.joint_grid(ball, 0, 0, cup.joints[0], glm.vec3(0, 0, 1))))
    assert placed is not None and model.connections()[placed.id] == {cup.id}
    assert glm.distance(placed.joints[0][2], -cup.joints[0][2]) < 1e-5              # straight
    up = glm.vec3(model.frame_matrix(placed.frame) * glm.vec4(0, 0, 1, 0))
    assert glm.distance(up, glm.vec3(0, 0, 1)) < 1e-5                               # tops the same way
    # And the other way round: a cup part onto a ball
    other = h.add_part(lib(model, "joint_1x2_ball"), (20, 0, 0), 0, "white")
    cup_part = lib(model, "joint_1x2_cup")
    grid = model.joint_grid(cup_part, 0, 0, other.joints[0], glm.vec3(0, 0, 1))
    assert model.turned_placement_problem(cup_part, (0, 0, 0), 0, grid) is None


def test_one_joint_poses_two_on_a_line_hinge(model):
    from brickbuilder.core.motion import plan_turn
    h = History(model)
    cup = h.add_part(lib(model, "joint_1x2_cup"), (0, 0, 0), 0, "red")
    ball = straight_on(model, h, cup)
    plan = plan_turn(model, {ball.id})
    assert plan.kind == "pose" and glm.distance(plan.pivot, cup.joints[0][1]) < 1e-4

    # A second cup / ball pair next to it (cups 2 cells along Y), the two ball parts tied by a brick
    # on top: two joints on one line make a hinge about it
    cup2 = h.add_part(lib(model, "joint_1x2_cup"), (0, 4, 0), 0, "red")
    ball2 = straight_on(model, h, cup2)
    assert ball2.frame == ball.frame                                   # lined up: one grid
    tie = h.add_part(lib(model, "brick_1x4"), (ball2.pos[0], ball2.pos[1], 1), ball2.turns, "white", ball2.frame)
    assert tie is not None and {ball.id, ball2.id} <= model.connections()[tie.id]
    plan = plan_turn(model, {ball.id, ball2.id, tie.id})
    assert plan.kind == "turn"
    line = glm.normalize(cup2.joints[0][1] - cup.joints[0][1])
    assert abs(abs(glm.dot(plan.axis, line)) - 1) < 1e-5
    # The pivot is on that line
    off = plan.pivot - cup.joints[0][1]
    assert glm.length(off - line * glm.dot(off, line)) < 1e-3


def test_clamp_arm_to_the_cone_or_the_slot():
    from brickbuilder.core.motion import clamp_arm, joint_angles
    cup_axis, slot = glm.vec3(1, 0, 0), glm.vec3(0, 0, 1)
    straight = glm.vec3(-1, 0, 0)
    sideways_40 = glm.vec3(-glm.cos(glm.radians(40)), glm.sin(glm.radians(40)), 0)
    arm, theta, phi = clamp_arm(sideways_40, cup_axis, slot, 30, 90, 7.5)
    # Too far sideways for the cone: it goes into the slot's plane instead (up, since φ = ±90 -> 0)
    assert abs(arm.y) < 1e-6 and phi in (0.0, 180.0) and theta == 37.5
    up_100 = glm.vec3(glm.cos(glm.radians(80)), 0, glm.sin(glm.radians(80)))   # 100° from straight
    arm, theta, phi = clamp_arm(up_100, cup_axis, slot, 30, 90, 7.5)
    assert theta == 90.0 and phi == 0.0
    assert joint_angles(straight, cup_axis, slot)[0] < 1e-6
