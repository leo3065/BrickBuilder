import glm

from brickbuilder.core import picking
from brickbuilder.core.camera import Camera


def look_direction(cam):
    view = cam.get_view_matrix()
    return -glm.vec3(view[0][2], view[1][2], view[2][2])


def test_preset_views():
    cam = Camera()
    cam.set_view("front")
    assert glm.distance(look_direction(cam), glm.vec3(0, 1, 0)) < 1e-6 and cam.is_view("front")
    cam.set_view("right")
    assert glm.distance(look_direction(cam), glm.vec3(-1, 0, 0)) < 1e-6
    cam.set_view("top")
    assert look_direction(cam).z < -0.999 and not cam.is_view("front")
    # Top keeps +Y up on screen and +X to the right
    view = cam.get_view_matrix()
    right, up = glm.vec3(view[0][0], view[1][0], view[2][0]), glm.vec3(view[0][1], view[1][1], view[2][1])
    assert right.x > 0.99 and up.y > 0.99
    cam.set_view("isometric")
    d = look_direction(cam)
    assert abs(abs(d.x) - abs(d.y)) < 1e-6 and abs(abs(d.x) - abs(d.z)) < 1e-6   # equal angles


def test_fit_puts_a_box_in_view():
    cam = Camera()
    cam.set_aspect_ratio(1.5)
    lo, hi = glm.vec3(100, 100, 0), glm.vec3(140, 120, 30)
    cam.fit(lo, hi)
    w, h = 900, 600
    for corner in (lo, hi, glm.vec3(lo.x, hi.y, hi.z), glm.vec3(hi.x, lo.y, lo.z)):
        x, y = picking.project(corner, w, h, cam)
        assert 0 <= x <= w and 0 <= y <= h
    assert cam.scale < 200  # zoomed in on it, not the default far view
