import time

import pytest

from brickbuilder.core.connections import groups
from brickbuilder.core.model import Model
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture(scope="module")
def profile():
    return load_builtin_profile()


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.fixture
def model(profile, library):
    return Model(profile, library)


def add(model, name, sub, turns=0):
    placed = model.add_part(model.library[f"nanoblock:{name}"], sub, turns, "red")
    assert placed is not None, f"{name} at {sub} didn't fit"
    return placed.id


def linked(model, a, b):
    return b in model.connections()[a] and a in model.connections()[b]


def test_stacked_bricks_connect(model):
    a = add(model, "brick_1x1", (0, 0, 0))
    b = add(model, "brick_1x1", (0, 0, 1))
    c = add(model, "brick_1x1", (2, 0, 0))          # beside a, touching only its side
    assert linked(model, a, b)
    assert model.connections()[c] == set()


def test_1xn_slot_takes_half_offset_studs(model):
    base = add(model, "brick_1x3", (0, 0, 0))       # studs at y = 0.5, 1.5, 2.5 cells
    top = add(model, "brick_1x2", (0, 1, 1))         # half a cell along: its slot spans y 1.0..2.0
    assert linked(model, base, top)


def test_2xn_rib_blocks_sideways_half_offset(model):
    base = add(model, "brick_2x2", (0, 0, 0))
    # Half a cell across the rows: the studs land on the rib between its two slots
    top = add(model, "brick_2x2", (1, 0, 1))
    assert not linked(model, base, top)
    # Half a cell along the rows: the studs slide along the slots
    other = add(model, "brick_2x2", (8, 0, 0))
    along = add(model, "brick_2x2", (8, 1, 1))
    assert linked(model, other, along)


def test_slot_direction_follows_rotation(model):
    base = add(model, "brick_1x3", (0, 0, 0), turns=1)  # turned: runs along -X, studs y = 0.5 cells
    top = add(model, "brick_1x2", (-1, 0, 1), turns=1)   # also turned, half a cell along X
    assert linked(model, base, top)


def test_inverted_slope_wall_splits_its_underside(model):
    base = add(model, "brick_1x2_1_stud", (0, 0, 0))   # one stud on the boundary, y = 1.0 cells
    top = add(model, "slope_1x2_wedge_1x1_inverted", (0, 0, 1))
    assert not linked(model, base, top)                 # the wall sits right on that line
    plain = add(model, "brick_1x2", (2, 0, 1))
    under = add(model, "brick_1x2_1_stud", (2, 0, 0))
    assert linked(model, under, plain)                  # a plain 1x2's slot takes it


def test_round_2x2_centre_and_diagonal_slots(model):
    one_stud = add(model, "brick_2x2_1_stud", (0, 0, 0))  # stud at the 2x2's centre
    rnd = add(model, "round_2x2", (0, 0, 1))              # centre over centre
    assert linked(model, one_stud, rnd)
    # A stud under one of the round's cell centres: the start of a diagonal slot
    base = add(model, "brick_1x1", (8, 0, 0))             # stud at cells (4.5, 0.5)
    rnd2 = add(model, "round_2x2", (8, 0, 1))             # its -x-y cell centre is (4.5, 0.5)
    assert linked(model, base, rnd2)
    # A stud under the middle of the round's edge, 1 cell out along an axis: not on any slot
    base2 = add(model, "brick_1x1", (15, 0, 0))           # stud at cells (8.0, 0.5)
    rnd3 = add(model, "round_2x2", (12, -1, 1))           # centre at cells (7.0, 0.5)
    assert not linked(model, base2, rnd3)


def test_plates_and_groups(model):
    plate = add(model, "plate_10x10", (0, 0, 0))
    on = add(model, "brick_2x4", (2, 2, 1))
    floating = add(model, "brick_1x1", (40, 40, 3))
    assert linked(model, plate, on)
    found = groups(model.connections())
    assert found[0] == {plate, on} and {floating} in found


def test_cache_follows_edits(model):
    a = add(model, "brick_1x1", (0, 0, 0))
    b = add(model, "brick_1x1", (0, 0, 1))
    assert linked(model, a, b)
    model.remove_part(a)
    assert model.connections() == {b: set()}


def test_connections_fast_enough(model, library):
    # 1000 2x4 bricks stacked in a running-bond-free grid: well under a second
    for i in range(1000):
        add(model, "brick_2x4", ((i % 10) * 4, ((i // 10) % 10) * 8, i // 100))
    start = time.perf_counter()
    links = model.connections()
    assert time.perf_counter() - start < 1.0
    assert len(groups(links)) == 100   # 100 columns, each a stack of 10
