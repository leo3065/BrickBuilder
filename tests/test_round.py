import math

import glm
import pytest

from brickbuilder.core import picking
from brickbuilder.core.geometry import Body, _rounded_footprint, part_outline
from brickbuilder.core.model import Model, placement_target
from brickbuilder.core.parts import PartError, load_builtin_library, part_from_dict
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture(scope="module")
def profile():
    return load_builtin_profile()


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.mark.parametrize("n", [2, 3, 4])
def test_round_1xn(library, profile, n):
    part = library[f"nanoblock:round_1x{n}"]
    assert part.category == "Round" and len(part.studs) == n and len(part.cells) == n
    points, tangents = _rounded_footprint(part.bodies[0], profile.subdiv)
    # Two semicircles; the straight sides meet them at 4 tangent points
    assert len(tangents) == 4
    # Every footprint point lies within the part's cells (x 0..2, y 0..2n sub-cells)
    assert all(-1e-9 <= x <= 2 + 1e-9 and -1e-9 <= y <= 2 * n + 1e-9 for x, y in points)
    # The ends are semicircles of radius 1 sub-cell around the end cells' centres
    for x, y in points:
        if y < 1:
            assert math.dist((x, y), (1, 1)) == pytest.approx(1)
    # Outline: top and bottom loops, plus one vertical line per tangent point
    assert len(part_outline(part.bodies, profile.subdiv)) == 2 * len(points) + 4


def test_full_circle_has_no_vertical_lines(profile):
    disc = Body("box", (0, 0, 0), (2, 2, 1), True, radius=1.0)
    points, tangents = _rounded_footprint(disc, profile.subdiv)
    assert tangents == [] and len(points) == 32
    assert len(part_outline([disc], profile.subdiv)) == 64


@pytest.mark.parametrize("body, message", [
    ({"shape": "box", "size": [1, 2, 1], "corner_radius": 0.6}, "half the shorter side"),
    ({"shape": "box", "size": [1, 2, 1], "corner_radius": -1}, ">= 0"),
])
def test_bad_corner_radius(body, message):
    with pytest.raises(PartError, match=message):
        part_from_dict("t:r", "", {"name": "R", "body": [body]})


def test_rounded_box_must_be_the_only_body():
    with pytest.raises(PartError, match="only body"):
        part_from_dict("t:r", "", {"name": "R", "body": [
            {"shape": "box", "size": [1, 2, 1], "corner_radius": 0.5},
            {"shape": "box", "size": [1, 1, 1], "at": [1, 0, 0]}]})


def test_round_part_occupies_whole_cells(library, profile):
    model = Model(profile, library)
    model.add_part(library["nanoblock:round_1x2"], (0, 0, 0), 0, "red")
    assert len(model.occupancy) == 8  # 2 cells x 4 half-cells: the corner gaps stay blocked
    assert not model.can_place(library["nanoblock:brick_1x1"], (0, 0, 0), 0)


def test_curved_end_places_beside_the_part(library, profile):
    model = Model(profile, library)
    model.add_part(library["nanoblock:round_1x2"], (0, 0, 0), 0, "red")  # cells y 0..1, x 0
    # A ray from -Y into the rounded end (its tip is at world y=-2, x=0)
    ray = picking.Ray(glm.vec3(0.3, -100, 1.5), glm.vec3(0, 1, 0))
    hit, normal, point = picking.intersect_model(ray, model)
    assert hit is not None and tuple(normal) == (0, -1, 0)  # the flat bounding face, not the curve
    assert placement_target(profile, point, normal, half=False) == profile.cell_to_sub((0, -1, 0))


def test_round_1x1_and_2x2(library, profile):
    one = library["nanoblock:round_1x1"]
    assert len(one.cells) == 1 and one.studs == ((0.5, 0.5, 1.0),) and one.antistuds == ()
    two = library["nanoblock:round_2x2"]
    assert len(two.cells) == 4 and len(two.studs) == 4
    # The extra antistud in the centre of the underside, half a cell off the cell centres
    assert two.antistuds == ((1.0, 1.0, 0.0),)
    # Full circles: top and bottom loops only, no straight sides
    for part in (one, two):
        assert len(part_outline(part.bodies, profile.subdiv)) == 64
