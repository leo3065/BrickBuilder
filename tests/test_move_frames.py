"""History.move_parts: turning parts creates, reuses, merges and removes frames."""

import glm
import pytest

from brickbuilder.core.history import History
from brickbuilder.core.model import Model, turn_about_z
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.fixture
def model(library):
    return Model(load_builtin_profile(), library)


def lib(model, name):
    return model.library[f"nanoblock:{name}"]


turn = turn_about_z  # turning about a vertical axis through a pivot


def close(a, b, eps=1e-3):
    return glm.distance(glm.vec3(a), glm.vec3(b)) < eps


def snapshot(model):
    return model.to_dict()


def on_one_stud(model, h):
    """A 2x2 one-stud brick with a 1x4 sitting on its stud by one end cell's slot."""
    base = h.add_part(lib(model, "brick_2x2_1_stud"), (0, 0, 0), 0, "gray")
    stud = base.studs[0]
    # The 1x4's slot runs along its middle; put its first cell centre on the stud
    arm = h.add_part(lib(model, "brick_1x4"), (1, 1, 1), 0, "red")
    assert arm is not None and model.connections()[arm.id] == {base.id}
    return base, arm, stud


def test_turn_creates_reuses_and_merges_a_frame(model):
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    before = snapshot(model)
    tip = arm.studs[-1]

    assert h.move_parts([arm.id], turn(stud, 30)) is None
    arm = model.parts[arm.id]
    assert arm.frame != 0 and model.frames[arm.frame].parent == 0
    assert arm.pos == (1, 1, 1) and arm.turns == 0          # same place on its (turned) grid
    assert close(model.parts[arm.id].studs[-1], glm.vec3(turn(stud, 30) * glm.vec4(tip, 1)))
    assert model.connections()[arm.id] == {base.id}         # still on the stud
    frame = arm.frame

    # Turning again moves the same frame rather than nesting a new one
    assert h.move_parts([arm.id], turn(stud, 15)) is None
    assert model.parts[arm.id].frame == frame and len(model.frames) == 2
    assert close(model.parts[arm.id].studs[-1], glm.vec3(turn(stud, 45) * glm.vec4(tip, 1)))

    # Back to straight: merged into the root grid, frame gone
    assert h.move_parts([arm.id], turn(stud, -45)) is None
    assert model.parts[arm.id].frame == 0 and set(model.frames) == {0}
    assert snapshot(model)["parts"] == before["parts"]

    # Undo all three, redo all three
    for _ in range(3):
        h.undo()
    assert snapshot(model) == before
    for _ in range(3):
        h.redo()
    assert set(model.frames) == {0} and model.parts[arm.id].pos == (1, 1, 1)


def test_quarter_turn_stays_on_the_grid(model):
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    assert h.move_parts([arm.id], turn(stud, 90)) is None
    arm = model.parts[arm.id]
    assert arm.frame == 0 and set(model.frames) == {0}
    assert arm.turns == 1 and model.connections()[arm.id] == {base.id}


def test_frame_with_other_parts_gets_a_child_frame(model):
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    h.move_parts([arm.id], turn(stud, 30))
    frame = model.parts[arm.id].frame
    # A second part on the turned arm, in its frame; turn only that one about the arm's last stud
    top = h.add_part(lib(model, "brick_1x2"), (1, 7, 2), 0, "cobalt_blue", frame)
    assert top is not None and top.frame == frame
    pivot = model.parts[arm.id].studs[-1]
    assert h.move_parts([top.id], turn(pivot, 15)) is None
    top = model.parts[top.id]
    assert top.frame not in (0, frame) and model.frames[top.frame].parent == frame
    assert top.pos == (1, 7, 2)

    # Turning the arm and everything on it moves only the arm's frame; the child frame follows
    child = top.frame
    top_stud = top.studs[0]
    assert h.move_parts([arm.id, top.id], turn(stud, 10)) is None
    assert model.parts[top.id].frame == child and len(model.frames) == 3
    assert close(model.parts[top.id].studs[0], glm.vec3(turn(stud, 10) * glm.vec4(top_stud, 1)))


def test_moved_frames_follow_a_new_frame(model):
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    top = h.add_part(lib(model, "brick_1x2"), (1, 7, 2), 0, "cobalt_blue")
    h.move_parts([top.id], turn(model.parts[arm.id].studs[-1], 30))
    child = model.parts[top.id].frame
    # The arm is on the root grid with the base, so it gets a new frame; top's frame goes into it
    assert h.move_parts([arm.id, top.id], turn(stud, 20)) is None
    new = model.parts[arm.id].frame
    assert new != 0 and model.frames[child].parent == new


def test_overlapping_turn_is_refused(model):
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    h.add_part(lib(model, "brick_1x1"), (3, 3, 1), 0, "white")   # beside the arm, same layer
    before = snapshot(model)
    steps = len(h._undo)
    reason = h.move_parts([arm.id], turn(stud, -45))  # swings into it
    assert reason and "overlap" in reason
    assert snapshot(model) == before and len(h._undo) == steps
    # A quarter turn the other way is clear
    assert h.move_parts([arm.id], turn(stud, 90)) is None


def test_deleting_the_last_part_of_a_frame_removes_it(model):
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    h.move_parts([arm.id], turn(stud, 30))
    turned = snapshot(model)
    h.remove_part(arm.id)
    assert set(model.frames) == {0}
    h.undo()
    assert snapshot(model) == turned


def test_placing_a_turned_part(model):
    h = History(model)
    base = h.add_part(lib(model, "brick_2x2_1_stud"), (0, 0, 0), 0, "gray")
    stud = base.studs[0]
    arm = lib(model, "brick_1x4")
    local = turn(glm.vec3(stud.x, stud.y, 0), 30)
    assert model.turned_placement_problem(arm, (1, 1, 1), 0, local) is None
    # Not on anything: has to sit on a stud
    assert "stud" in model.turned_placement_problem(arm, (11, 11, 1), 0, turn(glm.vec3(24, 24, 0), 30))
    # On a full 2x4's studs: blocked
    h.add_part(lib(model, "brick_2x4"), (10, 0, 0), 0, "white")
    centre = glm.vec3(model.profile.sub_to_world((12, 2, 0)))
    assert "stud" in model.turned_placement_problem(lib(model, "brick_2x4"), (10, 0, 1), 0, turn(centre, 30))

    before = snapshot(model)
    from brickbuilder.core.model import decompose
    placed = h.add_part_in_new_frame(arm, (1, 1, 1), 0, "red", 0, *decompose(local))
    assert placed is not None and placed.frame != 0 and model.connections()[placed.id] == {base.id}
    h.undo()
    assert snapshot(model) == before


def test_dropping_onto_another_grid(model):
    """A drag puts parts down on the target's grid (move_parts with target_frame)."""
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    h.move_parts([arm.id], turn(stud, 30))
    turned = model.parts[arm.id].frame
    loose = h.add_part(lib(model, "brick_1x1"), (20, 20, 0), 0, "white")

    # The loose brick onto the turned arm's grid: lined up with it, so it joins that frame
    w_t = model.frame_matrix(turned)
    src = model.profile.sub_to_world((21, 21, 0))         # its cell centre (root grid)
    dst = model.profile.sub_to_world((2, 6, 2))           # a cell centre on the arm's top (arm grid)
    t = w_t * glm.translate(glm.mat4(1.0), dst - src)
    assert h.move_parts([loose.id], t, turned) is None
    moved = model.parts[loose.id]
    assert moved.frame == turned and moved.pos == (1, 5, 2) and len(model.frames) == 2
    assert model.connections()[loose.id] == {arm.id}

    # The arm back onto the root grid's ground: its frame lines up with the root, so it merges
    # into it and the brick on it comes along (frame emptied and removed)
    w_a = model.frame_matrix(turned)
    t = glm.translate(glm.mat4(1.0), glm.vec3(40, 0, -model.profile.cell.z)) * glm.inverse(w_a)
    assert h.move_parts([arm.id, loose.id], t, 0) is None
    assert set(model.frames) == {0}
    assert model.parts[arm.id].frame == 0 and model.parts[loose.id].frame == 0

    # Dropped with a fine turn: a new frame, child of the target
    lone = h.add_part(lib(model, "brick_1x1"), (30, 30, 0), 0, "white")
    t = turn(model.profile.sub_to_world((31, 31, 0)), 15)
    assert h.move_parts([lone.id], t, 0) is None
    f = model.parts[lone.id].frame
    assert f != 0 and model.frames[f].parent == 0


def test_turns_reuse_a_frame_that_lines_up(model):
    """Parts turned alike end up on one grid, so something can bridge them."""
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    h.move_parts([arm.id], turn(stud, 30))
    frame = model.parts[arm.id].frame
    frames = set(model.frames)

    # A loose brick far away, turned about the same axis by the same angle: its grid is the arm's
    # grid, so it joins that frame instead of getting its own
    lone = h.add_part(lib(model, "brick_1x1"), (20, 0, 0), 0, "white")
    assert h.move_parts([lone.id], turn(stud, 30)) is None
    assert model.parts[lone.id].frame == frame and set(model.frames) == frames

    # A brick in a frame of its own (10 degrees), turned on to 30: its frame merges into the arm's
    other = h.add_part(lib(model, "brick_1x1"), (0, 20, 0), 0, "white")
    h.move_parts([other.id], turn(stud, 10))
    own = model.parts[other.id].frame
    assert own not in frames
    assert h.move_parts([other.id], turn(stud, 20)) is None
    assert model.parts[other.id].frame == frame and own not in model.frames
    h.undo()
    assert model.parts[other.id].frame == own


def test_turned_placement_reuses_a_frame_that_lines_up(model):
    from brickbuilder.core.model import decompose
    h = History(model)
    base, arm, stud = on_one_stud(model, h)
    h.move_parts([arm.id], turn(stud, 30))
    frame = model.parts[arm.id].frame
    # A part placed on the root grid turned 30 degrees about the same axis: onto the arm's frame
    placed = h.add_part_in_new_frame(lib(model, "brick_1x1"), (20, 20, 0), 0, "white", 0,
                                     *decompose(turn(glm.vec3(stud.x, stud.y, 0), 30)))
    assert placed is not None and placed.frame == frame and len(model.frames) == 2
