import glm
import pytest

from brickbuilder.core import picking
from brickbuilder.core.geometry import Body, classify, compatible, part_regions, wedge_cut
from brickbuilder.core.model import Model, placement_target
from brickbuilder.core.parts import PartError, load_builtin_library, part_from_dict
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


def lib(library, name):
    return library[f"nanoblock:{name}"]


def sub(profile, cell):
    return profile.cell_to_sub(cell)


# --- geometry -----------------------------------------------------------------------------

def test_complementary_wedges_share_a_plane_with_opposite_sides():
    lower = Body("wedge", (0, 0, 0), (1, 1, 2), False, "lower", 1, 1)   # tall +y
    upper = Body("wedge", (0, 0, 0), (1, 1, 2), True, "upper", 1, -1)   # tall -y
    a, b = wedge_cut(lower, (2, 2, 1)), wedge_cut(upper, (2, 2, 1))
    assert a.plane == b.plane and a.side == -b.side
    assert compatible(a, b) and not compatible(a, a) and not compatible(None, b)


def test_lower_wedge_keeps_the_corner_below_its_slope():
    lower = Body("wedge", (0, 0, 0), (1, 1, 1), False, "lower", 1, 1)  # rises towards +y
    cut = wedge_cut(lower, (1, 1, 1))
    assert cut.value(0.5, 0.9, 0.1) < 0      # low, near the tall side: inside
    assert cut.value(0.5, 0.1, 0.9) > 0      # high, near the short side: outside


def test_wedge_regions_on_the_half_cell_grid(profile):
    # A 1-layer wedge over one cell is 2 sub-cells long: both are cut by the slope
    lower = Body("wedge", (0, 0, 0), (1, 1, 1), False, "lower", 1, 1)
    regions = part_regions([lower], profile.subdiv)
    assert len(regions) == 4 and all(cut is not None for _, cut in regions)
    # A 1-cell x 2-layer wedge is 2x2 half-cells, cut corner to corner: next to the tall side the
    # bottom one is full, on the short side the top one is empty (not registered)
    tall = Body("wedge", (0, 0, 0), (1, 1, 2), False, "lower", 1, 1)
    regions = dict(part_regions([tall], profile.subdiv))
    assert regions[(0, 1, 0)] is None and regions[(0, 0, 0)] is not None and regions[(0, 1, 1)] is not None
    assert (0, 0, 1) not in regions
    assert classify(wedge_cut(tall, profile.subdiv), (0, 0, 1)) == "empty"


# --- parts --------------------------------------------------------------------------------

def test_slope_parts_cells_and_studs(library):
    assert lib(library, "slope_1x2").studs == ((0, 1, 0),)
    assert lib(library, "slope_1x2x2").cells == ((0, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 2))
    assert lib(library, "slope_inverted_1x2").studs == ((0, 0, 0), (0, 1, 0))
    assert lib(library, "slope_inverted_1x2x2").studs == ((0, 0, 0), (0, 1, 1))


@pytest.mark.parametrize("body, message", [
    ({"shape": "wedge", "size": [1, 1, 1], "keep": "middle", "tall": "+y"}, "keep"),
    ({"shape": "wedge", "size": [1, 1, 1], "keep": "lower", "tall": "up"}, "tall"),
    ({"shape": "wedge", "size": [1, 1, 1], "keep": "lower", "tall": "+y", "studs": "top"}, "sloped"),
])
def test_bad_wedges_rejected(body, message):
    with pytest.raises(PartError, match=message):
        part_from_dict("t:w", "", {"name": "W", "body": [body]})


# --- occupancy: the pairs from real sets ----------------------------------------------------

@pytest.mark.parametrize("slope, inverted", [("slope_1x2", "slope_inverted_1x2"),
                                             ("slope_1x2x2", "slope_inverted_1x2x2")])
def test_complementary_pairs_fit_together(model, profile, library, slope, inverted):
    # Slope's triangle is on cell (0, 0, 1+); the inverted part's triangle (its local cell y=1)
    # lands on the same cells when its origin is at cell (0, -1, 1)
    assert model.add_part(lib(library, slope), (0, 0, 0), 0, "red")
    assert model.can_place(lib(library, inverted), sub(profile, (0, -1, 1)), 0)
    assert model.add_part(lib(library, inverted), sub(profile, (0, -1, 1)), 0, "white")
    # Removing one frees exactly its share
    slope_id = next(p.id for p in model.parts.values() if p.part.id.endswith(slope))
    model.remove_part(slope_id)
    assert all(len(v) == 1 for v in model.occupancy.values())


def test_pair_still_fits_when_turned(model, profile, library):
    model.add_part(lib(library, "slope_1x2"), (0, 0, 0), 1, "red")
    # The inverted part's origin (0, -2) turned once about the slope's origin -> (2, 0)
    assert model.can_place(lib(library, "slope_inverted_1x2"), (2, 0, 1), 1)


def test_pair_fits_with_half_offset_along_the_extrusion(model, profile, library):
    model.add_part(lib(library, "slope_1x2"), (0, 0, 0), 0, "red")
    # Shifted half a cell in X: the overlapping half-cells are cut by the same plane
    assert model.can_place(lib(library, "slope_inverted_1x2"), (1, -2, 1), 0)


def test_other_overlaps_with_a_slope_are_refused(model, profile, library):
    model.add_part(lib(library, "slope_1x2"), (0, 0, 0), 0, "red")
    # A brick in the triangle's cell
    assert not model.can_place(lib(library, "brick_1x1"), sub(profile, (0, 0, 1)), 0)
    # The same slope again, one layer up and back: its base would cut into the triangle
    assert not model.can_place(lib(library, "slope_1x2"), sub(profile, (0, -1, 1)), 0)
    # An inverted slope turned the other way: a different plane through the same cell
    assert not model.can_place(lib(library, "slope_inverted_1x2"), sub(profile, (1, 2, 1)), 2)
    # But the empty space above the flat cell is free
    assert model.can_place(lib(library, "brick_1x1"), sub(profile, (0, 1, 1)), 0)


# --- picking --------------------------------------------------------------------------------

def test_picking_hits_the_slope_not_its_bounding_box(model, profile, library):
    model.add_part(lib(library, "slope_1x2"), (0, 0, 0), 0, "red")
    # Horizontal ray towards +y through the empty space above the low end of the triangle:
    # the triangle's cell spans y -2..2 and z 3.125..6.25, the slope rising towards +y
    ray = picking.Ray(glm.vec3(0, -100, 5.5), glm.vec3(0, 1, 0))
    hit, normal, point = picking.intersect_model(ray, model)
    assert hit is not None
    assert point.y == pytest.approx(-2 + (5.5 - 3.125) * 4 / 3.125, abs=1e-4)  # on the slope, not y=-2
    assert normal.z > 0 and normal.y < 0                                 # facing up and back
    # Pointing at the slope targets the empty part of its own cell (for a complementary wedge)
    target = placement_target(profile, point, normal, half=False)
    assert target == sub(profile, (0, 0, 1))
    assert model.can_place(lib(library, "slope_inverted_1x2"), (target[0], target[1] - 2, target[2]), 0)
    assert not model.can_place(lib(library, "brick_1x1"), target, 0)
    # The flat top of the other cell is a normal target
    ray = picking.Ray(glm.vec3(0, 4, 100), glm.vec3(0, 0, -1))
    hit, normal, point = picking.intersect_model(ray, model)
    assert placement_target(profile, point, normal, half=False) == sub(profile, (0, 1, 1))


def test_slopes_save_and_load(model, profile, library, tmp_path):
    model.add_part(lib(library, "slope_1x2x2"), (0, 0, 0), 0, "red")
    model.add_part(lib(library, "slope_inverted_1x2x2"), sub(profile, (0, -1, 1)), 0, "white")
    path = tmp_path / "s.json"
    model.save_to_file(str(path))
    loaded = Model(profile, library)
    loaded.load_from_file(str(path))
    assert loaded.to_dict() == model.to_dict()
