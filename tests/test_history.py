import pytest

from brickbuilder.core.history import History
from brickbuilder.core.model import Model
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.fixture
def model(library):
    return Model(load_builtin_profile(), library)


def brick(library, size="1x1"):
    return library[f"nanoblock:brick_{size}"]


def state(model):
    return model.to_dict()["parts"]


def test_undo_redo_add_remove_color(model, library):
    h = History(model)
    h.reset()
    a = h.add_part(brick(library, "2x4"), (0, 0, 0), 1, "red")
    s1 = state(model)
    h.set_color(a.id, "yellow")
    s2 = state(model)
    h.remove_part(a.id)
    assert state(model) == []

    assert h.undo() and state(model) == s2      # back with the same id and color
    assert h.undo() and state(model) == s1
    assert h.undo() and state(model) == []
    assert not h.undo()
    assert h.redo() and h.redo() and h.redo() and state(model) == []
    assert not h.redo()


def test_new_edit_clears_redo(model, library):
    h = History(model)
    h.add_part(brick(library), (0, 0, 0), 0, "red")
    h.undo()
    assert h.can_redo()
    h.add_part(brick(library), (4, 0, 0), 0, "red")
    assert not h.can_redo()


def test_refused_or_noop_edits_are_not_recorded(model, library):
    h = History(model)
    a = h.add_part(brick(library), (0, 0, 0), 0, "red")
    assert h.add_part(brick(library), (0, 0, 0), 0, "red") is None  # overlap
    h.set_color(a.id, "red")                                       # same color
    h.remove_part(999)                                             # no such part
    assert h.undo() and not h.can_undo()


def test_modified_follows_saved_point(model, library):
    h = History(model)
    h.reset()
    assert not model.modified
    a = h.add_part(brick(library), (0, 0, 0), 0, "red")
    assert model.modified
    h.mark_clean()                 # saved here
    assert not model.modified
    h.set_color(a.id, "cobalt_blue")
    assert model.modified
    h.undo()
    assert not model.modified      # back at the saved state
    h.undo()
    assert model.modified          # before the saved state
    h.redo()
    assert not model.modified


def test_saved_point_lost_when_history_overflows(model, library):
    h = History(model, limit=3)
    h.reset()                      # clean = empty document
    for i in range(4):             # the first step drops off
        h.add_part(brick(library), (4 * i, 0, 0), 0, "red")
    while h.undo():
        pass
    assert len(model.parts) == 1   # the oldest step can't be undone any more...
    assert model.modified          # ...so this is not the saved (empty) state


def test_group_edits_undo_in_one_step(model, library):
    h = History(model)
    h.reset()
    ids = [h.add_part(brick(library), (4 * i, 0, 0), 0, "red").id for i in range(3)]
    h.set_colors(ids, "yellow")
    assert {p.color for p in model.parts.values()} == {"yellow"}
    h.remove_parts(ids[:2])
    assert set(model.parts) == {ids[2]}
    assert h.undo() and set(model.parts) == set(ids)                     # both back in one step
    assert h.undo() and {p.color for p in model.parts.values()} == {"red"}
    h.set_colors(ids, "red")                                              # no change: no step
    assert h.can_redo()
