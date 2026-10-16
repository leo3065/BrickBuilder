import json
import math

import glm
import pytest

from brickbuilder.core import picking
from brickbuilder.core.model import Model, ModelError, placement_target
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


def lib(library, name):
    return library[f"nanoblock:{name}"]


def turn_z(degrees):
    return glm.angleAxis(math.radians(degrees), glm.vec3(0, 0, 1))


def close(a, b):
    return glm.distance(glm.vec3(a), glm.vec3(b)) < 1e-4


def stud_frame(model, degrees):
    """A frame turned about the single stud of a 2x2 one-stud brick at the root origin, with its
    own origin on that stud (so a part whose centre antistud is at the frame origin sits on it)."""
    base = model.add_part(model.library["nanoblock:brick_2x2_1_stud"], (0, 0, 0), 0, "gray")
    stud = base.studs[0]
    assert close(stud, (2.0, 2.0, 3.125))
    return base, model.add_frame(0, stud, turn_z(degrees))


def test_part_in_a_turned_frame(model, library):
    _, frame = stud_frame(model, 30)
    # Round 2x2 with its centre antistud (cells (1, 1, 0)) on the frame origin: pos (-1, -1, 0)
    rnd = model.add_part(lib(library, "round_2x2"), (-1, -1, 0), 0, "red", frame=frame.id)
    assert rnd.frame == frame.id
    # Its centre antistud is on the stud whatever the angle...
    centre = [a for a, b in rnd.antistuds if close(a, b)][0]
    assert close(centre, (2.0, 2.0, 3.125))
    # ...and its studs are turned 30 degrees about it
    s = min(rnd.studs, key=lambda p: (p.x, p.y))
    off = glm.vec3(-2, -2, 0)   # the -x-y stud's offset from the centre, before turning
    expected = glm.vec3(2, 2, 6.25) + glm.vec3(glm.mat3_cast(turn_z(30)) * off)
    assert any(close(p, expected) for p in rnd.studs), (s, expected)


def test_connection_across_frames(model, library):
    base, frame = stud_frame(model, 22.5)
    rnd = model.add_part(lib(library, "round_2x2"), (-1, -1, 0), 0, "red", frame=frame.id)
    assert rnd.id in model.connections()[base.id]


def test_each_frame_has_its_own_grid(model, library):
    _, frame = stud_frame(model, 45)
    brick = lib(library, "brick_1x1")
    # The same grid position in the root and in the frame: both fine (not checked across frames)
    assert model.add_part(brick, (10, 10, 0), 0, "red")
    assert model.add_part(brick, (10, 10, 0), 0, "red", frame=frame.id)
    # But within the frame, overlap is refused as usual
    assert not model.can_place(brick, (10, 10, 0), 0, frame=frame.id)


def test_placing_onto_a_turned_part_uses_its_grid(model, profile, library):
    _, frame = stud_frame(model, 30)
    top = model.add_part(lib(library, "brick_2x2"), (-2, -2, 0), 0, "red", frame=frame.id)
    # A ray straight down onto the turned 2x2's top, near its middle
    hit_point = glm.vec3(2.3, 2.4, 100)
    hit, normal, point = picking.intersect_model(picking.Ray(hit_point, glm.vec3(0, 0, -1)), model)
    assert hit is top
    local_point, local_normal = model.to_frame(top.frame, point, normal)
    assert close(local_normal, (0, 0, 1))
    target = placement_target(profile, local_point, local_normal, half=False)
    # One layer up, on the frame's own grid (a cell of the 2x2 under the cursor)
    assert target[2] == 1 and target[0] in (-2, 0) and target[1] in (-2, 0)


def test_frames_save_and_load(model, profile, library, tmp_path):
    _, frame = stud_frame(model, 30)
    child = model.add_frame(frame.id, glm.vec3(0, 4, 3.125), turn_z(-15))
    model.add_part(lib(library, "round_2x2"), (-1, -1, 0), 0, "red", frame=frame.id)
    model.add_part(lib(library, "brick_1x2"), (0, 0, 0), 1, "yellow", frame=child.id)
    path = tmp_path / "f.json"
    model.save_to_file(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 4 and [f["id"] for f in data["frames"]] == [0, frame.id, child.id]
    loaded = Model(profile, library)
    loaded.load_from_file(str(path))
    assert loaded.to_dict() == model.to_dict()
    for pid, p in model.parts.items():
        assert all(close(a, b) for a, b in zip(p.studs, loaded.parts[pid].studs))


@pytest.mark.parametrize("frames, message", [
    ([{"id": 0}, {"id": 1, "parent": 5, "origin": [0, 0, 0], "rotation": [1, 0, 0, 0]}], "listed before"),
    ([{"id": 0}, {"id": 1, "parent": 0, "origin": [0, 0], "rotation": [1, 0, 0, 0]}], "origin"),
    ([{"id": 0}, {"id": 1, "parent": 0, "origin": [0, 0, 0], "rotation": [2, 0, 0, 0]}], "unit quaternion"),
])
def test_bad_frames_rejected(model, frames, message):
    with pytest.raises(ModelError, match=message):
        model.from_dict({"version": 3, "profile": "nanoblock", "frames": frames, "parts": []})


def test_v2_files_still_load_but_only_with_the_root(model):
    model.from_dict({"version": 2, "profile": "nanoblock", "frames": [{"id": 0}], "parts": []})
    with pytest.raises(ModelError, match="v2"):
        model.from_dict({"version": 2, "profile": "nanoblock", "frames": [
            {"id": 0}, {"id": 1, "parent": 0, "origin": [0, 0, 0], "rotation": [1, 0, 0, 0]}], "parts": []})


def test_remove_frame_only_when_empty(model, library):
    _, frame = stud_frame(model, 30)
    p = model.add_part(lib(library, "brick_1x1"), (0, 0, 0), 0, "red", frame=frame.id)
    with pytest.raises(ModelError, match="still has parts"):
        model.remove_frame(frame.id)
    model.remove_part(p.id)
    model.remove_frame(frame.id)
    assert frame.id not in model.frames


def test_undo_keeps_the_frame(model, library):
    from brickbuilder.core.history import History
    _, frame = stud_frame(model, 30)
    h = History(model)
    p = h.add_part(lib(library, "round_2x2"), (-1, -1, 0), 0, "red", frame=frame.id)
    h.remove_part(p.id)
    h.undo()
    assert model.parts[p.id].frame == frame.id
