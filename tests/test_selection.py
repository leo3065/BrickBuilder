import pytest

from brickbuilder.core import picking
from brickbuilder.core.camera import Camera
from brickbuilder.core.model import Model
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture
def model():
    return Model(load_builtin_profile(), load_builtin_library("nanoblock"))


def test_project_matches_mouse_ray(model):
    cam = Camera()
    w, h = 800, 600
    import glm
    p = glm.vec3(5, -3, 2)
    sx, sy = picking.project(p, w, h, cam)
    ray = picking.get_mouse_ray(sx, sy, w, h, cam)
    # The ray through the projected pixel passes through the point
    to_p = p - ray.origin
    closest = ray.origin + ray.direction * glm.dot(to_p, ray.direction)
    assert glm.distance(closest, p) < 1e-3


def test_box_select(model):
    brick = model.library["nanoblock:brick_1x1"]
    a = model.add_part(brick, (0, 0, 0), 0, "red").id
    b = model.add_part(brick, (40, 0, 0), 0, "red").id      # 20 cells along +X
    cam = Camera()
    w, h = 800, 600
    ax, ay = picking.project((model.parts[a].box[0] + model.parts[a].box[1]) * 0.5, w, h, cam)
    # A small box around a's centre selects only a; a box over the whole view selects both
    assert picking.parts_in_rect(model, cam, ax - 5, ay - 5, ax + 5, ay + 5, w, h) == [a]
    assert sorted(picking.parts_in_rect(model, cam, w, h, 0, 0, w, h)) == sorted([a, b])  # any corner order
