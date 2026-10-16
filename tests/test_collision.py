import math

import glm
import pytest

from brickbuilder.core.model import Model
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


def turned_about(model, centre: glm.vec3, degrees: float):
    """A frame that is the root grid turned about a vertical axis through `centre`."""
    rot = glm.angleAxis(math.radians(degrees), glm.vec3(0, 0, 1))
    return model.add_frame(0, centre - glm.vec3(glm.mat3_cast(rot) * centre), rot)


def cell_centre(model, pos):
    probe = model.add_part(lib(model, "brick_1x1"), pos, 0, "red")
    c = (probe.box[0] + probe.box[1]) * 0.5
    model.remove_part(probe.id)
    return c


def ring_of_neighbours(model):
    """1x1 bricks on the four sides of cell (0, 0, 0), in the root frame."""
    return [model.add_part(lib(model, "brick_1x1"), pos, 0, "white").id
            for pos in ((2, 0, 0), (-2, 0, 0), (0, 2, 0), (0, -2, 0))]


@pytest.mark.parametrize("degrees", [7.5 * i for i in range(13)])
def test_round_1x1_turns_freely_between_neighbours(model, degrees):
    ring_of_neighbours(model)
    frame = turned_about(model, cell_centre(model, (0, 0, 0)), degrees)
    assert model.can_place(lib(model, "round_1x1"), (0, 0, 0), 0, frame.id)
    model.add_part(lib(model, "round_1x1"), (0, 0, 0), 0, "red", frame=frame.id)
    assert model.collisions() == set()


def test_turned_square_hits_its_neighbours(model):
    neighbours = ring_of_neighbours(model)
    frame = turned_about(model, cell_centre(model, (0, 0, 0)), 45)
    assert not model.can_place(lib(model, "brick_1x1"), (0, 0, 0), 0, frame.id)
    placed = model.add_part(lib(model, "brick_1x1"), (0, 0, 0), 0, "red", frame=frame.id)
    assert model.collisions() == set(neighbours) | {placed.id}
    assert sorted(model.cross_frame_overlaps(frame.id, model.part_shape(placed.id))) == sorted(neighbours)
    # An unturned frame lines up with the root grid: the bricks only touch
    model.remove_part(placed.id)
    flat = turned_about(model, cell_centre(model, (0, 0, 0)), 0)
    model.add_part(lib(model, "brick_1x1"), (0, 0, 0), 0, "red", frame=flat.id)
    assert model.collisions() == set()


@pytest.mark.parametrize("degrees", [10, 30, 45, 77.5])
def test_turned_part_on_a_flat_top_only_touches(model, degrees):
    centre = cell_centre(model, (2, 2, 0))
    model.add_part(lib(model, "flat_2x4"), (0, 0, 0), 0, "white")
    frame = turned_about(model, centre, degrees)
    assert model.can_place(lib(model, "brick_2x4"), (0, 0, 1), 0, frame.id)
    # One layer lower it would cut into the brick below
    assert not model.can_place(lib(model, "brick_2x4"), (0, 0, 0), 0, frame.id)


@pytest.mark.parametrize("degrees", [10, 45])
def test_studs_block_a_turned_part_unless_in_its_slots(model, degrees):
    # On a studded 2x4 the other studs would poke into the turned brick's body
    centre = cell_centre(model, (2, 2, 0))
    model.add_part(lib(model, "brick_2x4"), (0, 0, 0), 0, "white")
    frame = turned_about(model, centre, degrees)
    assert not model.can_place(lib(model, "brick_2x4"), (0, 0, 1), 0, frame.id)
    # Unturned, every stud is in a slot: fine
    flat = turned_about(model, centre, 0)
    assert model.can_place(lib(model, "brick_2x4"), (0, 0, 1), 0, flat.id)


def test_arm_turns_freely_on_a_single_stud(model):
    model.add_part(lib(model, "brick_2x2_1_stud"), (0, 0, 0), 0, "gray")
    stud = glm.vec3(2.0, 2.0, 0.0)  # the single stud's axis, at the 2x2's centre
    for degrees in (7.5, 30, 60, 82.5):
        frame = turned_about(model, stud, degrees)
        assert model.can_place(lib(model, "brick_1x4"), (1, 1, 1), 0, frame.id), degrees
