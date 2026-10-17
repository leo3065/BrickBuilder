"""motion.plan_turn: what turns, and about which axis."""
import glm
import pytest

from brickbuilder.core.history import History
from brickbuilder.core.model import Model
from brickbuilder.core.motion import moving_set, plan_turn
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.fixture
def model(library):
    return Model(load_builtin_profile(), library)


def add(model, name, pos, turns=0):
    placed = model.add_part(model.library[f"nanoblock:{name}"], pos, turns, "red")
    assert placed is not None, (name, pos)
    return placed.id


def xy_close(a, b):
    return abs(a.x - b.x) < 1e-3 and abs(a.y - b.y) < 1e-3


def test_arm_on_one_stud_turns_about_it(model):
    base = add(model, "brick_2x2_1_stud", (0, 0, 0))
    arm = add(model, "brick_1x4", (1, 1, 1))
    plan = plan_turn(model, {arm})
    assert plan.kind == "turn" and plan.moving == {arm} and plan.fixed == {base}
    assert xy_close(plan.pivot, model.parts[base].studs[0])


def test_arm_on_two_studs_is_locked(model):
    add(model, "brick_2x2", (0, 0, 0))
    arm = add(model, "brick_1x4", (0, 0, 1))      # its slot over one row: two studs in it
    plan = plan_turn(model, {arm})
    assert plan.kind == "locked" and "sliding" in plan.reason


def test_wedged_between_two_grounded_pieces_is_locked(model):
    left = add(model, "brick_1x1", (0, 0, 0))
    right = add(model, "brick_1x1", (0, 6, 0))
    arm = add(model, "brick_1x4", (0, 0, 1))      # bridges both, end cells on their studs
    assert moving_set(model, {arm}) == ({arm}, {left, right})
    assert plan_turn(model, {arm}).kind == "locked"


def test_lone_part_is_free(model):
    brick = add(model, "brick_2x4", (0, 0, 0))
    plan = plan_turn(model, {brick})
    assert plan.kind == "free" and plan.moving == {brick}


def test_stud_hinge_turns_about_the_column(model):
    # Side A: round 1x2 along X in layers 0 and 2, ends at cells 0 and 1; tied at cell 1 by a 1x1
    a1 = add(model, "round_1x2", (0, 0, 0), 3)    # turned so it runs along X
    cells_a1 = {(round(s.x), round(s.y)) for s in model.parts[a1].studs}
    tie_cell = max(cells_a1)                      # the end away from the column
    column = min(cells_a1)
    # Find sub positions for the other parts from the stud positions (cells are 4 mm)
    to_sub = lambda xy: (int(model.profile.world_to_sub(glm.vec3(xy[0], xy[1], 0))[0]) - 1,
                         int(model.profile.world_to_sub(glm.vec3(xy[0], xy[1], 0))[1]) - 1)
    tx, ty = to_sub(tie_cell)
    tie = add(model, "brick_1x1", (tx, ty, 1))
    a2 = add(model, "round_1x2", (0, 0, 2), 3)
    # Side B: a round 1x2 in layer 1 running the other way from the column
    cx, cy = to_sub(column)
    b1 = add(model, "round_1x2", (cx + 2, cy, 1), 1)
    links = model.connections()
    assert b1 in links[a1] and b1 in links[a2] and tie in links[a1] and tie in links[a2]

    plan = plan_turn(model, {b1})
    assert plan.kind == "turn" and plan.moving == {b1} and plan.fixed == {a1, tie, a2}
    assert xy_close(plan.pivot, glm.vec3(column[0], column[1], 0))
    # Contacts both ways round: A's stud in B's slot, B's stud in A's slot
    assert {c.stud_part for c in plan.contacts} == {a1, b1}

    # The selection always moves, even when it holds the ground: turning side A turns A, B stays
    plan = plan_turn(model, {a1, tie, a2})
    assert plan.kind == "turn" and plan.moving == {a1, tie, a2} and plan.fixed == {b1}

    # And the turn keeps every contact
    h = History(model)
    pivot = plan_turn(model, {b1}).pivot
    t = (glm.translate(glm.mat4(1.0), pivot) * glm.mat4_cast(glm.angleAxis(glm.radians(52.5), glm.vec3(0, 0, 1)))
         * glm.translate(glm.mat4(1.0), -pivot))
    assert h.move_parts({b1}, t) is None
    links = model.connections()
    assert b1 in links[a1] and b1 in links[a2]


def test_round_1x3_hinge_keeps_turning_at_any_angle(model):
    """From a user's file: two round 1x3s (layers 0 and 2, tied by a 1x2) and a round 1x3 in
    layer 1 hinged on their end studs. Float noise in the turned frame used to lock it at some
    angles (and then Shift+R couldn't put it back)."""
    a1 = add(model, "round_1x3", (-2, -6, 0))      # sub-cells (the file has cells)
    a2 = add(model, "round_1x3", (-2, -6, 2))
    add(model, "brick_1x2", (-2, -6, 1))
    b = add(model, "round_1x3", (-2, -2, 1))
    links = model.connections()
    assert b in links[a1] and b in links[a2]
    h = History(model)

    def turn_by(degrees):
        plan = plan_turn(model, {b})
        assert plan.kind == "turn", (degrees, plan.reason)
        t = (glm.translate(glm.mat4(1.0), plan.pivot)
             * glm.mat4_cast(glm.angleAxis(glm.radians(degrees), glm.vec3(0, 0, 1)))
             * glm.translate(glm.mat4(1.0), -plan.pivot))
        return h.move_parts({b}, t)

    total = 0.0
    for step in [7.5] * 12 + [13.7, -3.1, 22.5, 0.4] + [-7.5] * 6:
        if turn_by(step) is None:
            total += step
        links = model.connections()
        assert b in links[a1] and b in links[a2], total
    # Back to straight: on the root grid again
    assert turn_by(-total) is None
    assert model.parts[b].frame == 0 and set(model.frames) == {0}
