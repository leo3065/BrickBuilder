import pytest

from brickbuilder.core.history import History
from brickbuilder.core.model import Model, ModelError
from brickbuilder.core.parts import load_builtin_library
from brickbuilder.core.profile import load_builtin_profile


@pytest.fixture(scope="module")
def library():
    return load_builtin_library("nanoblock")


@pytest.fixture
def model(library):
    return Model(load_builtin_profile(), library)


def bricks(model, history, n):
    """n separate 1x1 bricks in a row, added through history."""
    brick = model.library["nanoblock:brick_1x1"]
    return [history.add_part(brick, (4 * i, 0, 0), 0, "red").id for i in range(n)]


def snapshot(model):
    data = model.to_dict()
    return data["groups"], data["parts"]


def test_group_nest_and_selection_units(model):
    h = History(model)
    a, b, c, d = bricks(model, h, 4)
    inner = h.group([a, b], "wing tip")
    outer = h.group([a, b, c], "wing")       # the whole inner group goes in as a child
    assert model.groups[inner].parent == outer and model.parts[c].group == outer
    assert model.parts[a].group == inner and model.parts[d].group is None
    assert model.group_parts(outer) == {a, b, c}
    assert model.group_chain(a) == [outer, inner]

    # Click: the outermost group; drilling in goes one level at a time, then the part
    assert model.selection_unit(a) == ({a, b, c}, outer)
    assert model.selection_unit(a, outer) == ({a, b}, inner)
    assert model.selection_unit(a, inner) == ({a}, None)
    assert model.selection_unit(c, outer) == ({c}, None)
    assert model.selection_unit(d, outer) == ({d}, None)  # not inside the context: top level

    assert model.top_units({a, b, c, d}) == ({outer}, {d})
    assert model.top_units({a, c}) == (set(), {a, c})


def test_group_inside_a_partly_selected_group(model):
    h = History(model)
    a, b, c = bricks(model, h, 3)
    outer = h.group([a, b, c], "body")
    new = h.group([a, b], "head")            # lands inside "body", where a and b already were
    assert model.groups[new].parent == outer and model.parts[c].group == outer


def test_group_ungroup_rename_undo(model):
    h = History(model)
    a, b, c = bricks(model, h, 3)
    before = snapshot(model)
    inner = h.group([a, b], "g1")
    outer = h.group([a, b, c], "g2")
    h.rename_group(outer, "wing")
    grouped = snapshot(model)
    assert model.groups[outer].name == "wing"

    h.ungroup([outer])                       # one level: g1 and c move up to the top
    assert outer not in model.groups and model.groups[inner].parent is None
    assert model.parts[c].group is None and model.parts[a].group == inner

    h.undo()
    assert snapshot(model) == grouped
    for _ in range(3):
        h.undo()
    assert snapshot(model) == before
    for _ in range(4):
        h.redo()
    assert outer not in model.groups and model.groups[inner].parent is None


def test_whole_groups_go_in_as_children(model):
    h = History(model)
    a, b = bricks(model, h, 2)
    g = h.group([a], "solo")
    h.group([b], "other")
    # Both groups are wholly selected, so both go in as child groups, never emptied
    new = h.group([a, b], "both")
    assert model.groups[g].parent == new
    h.ungroup([g])
    assert g not in model.groups and model.parts[a].group == new


def test_deleting_parts_removes_empty_groups_and_undo_restores(model):
    h = History(model)
    a, b, c = bricks(model, h, 3)
    inner = h.group([a, b], "inner")
    outer = h.group([a, b, c], "outer")
    grouped = snapshot(model)
    h.remove_parts([a, b])
    assert inner not in model.groups and outer in model.groups
    h.remove_part(c)
    assert model.groups == {}
    h.undo()
    h.undo()
    assert snapshot(model) == grouped


def test_groups_save_and_load(model):
    h = History(model)
    a, b, c = bricks(model, h, 3)
    inner = h.group([b, c], "tip")
    outer = h.group([a, b, c], "wing")
    data = model.to_dict()
    assert data["version"] == 4
    assert [g["id"] for g in data["groups"]] == [outer, inner]   # parent first
    assert "group" not in data["parts"][0] or data["parts"][0]["group"] == outer

    loaded = Model(model.profile, model.library)
    loaded.from_dict(data)
    assert snapshot(loaded) == snapshot(model)
    assert loaded.group_parts(outer) == {a, b, c}


def test_bad_groups_are_rejected(model):
    h = History(model)
    a, = bricks(model, h, 1)
    h.group([a], "g")
    data = model.to_dict()
    for bad in (
        {**data, "groups": [{"id": 1, "name": "g", "parent": 7}]},           # parent unknown
        {**data, "groups": [{"id": 0, "name": "g", "parent": None}]},        # id not positive
        {**data, "groups": []},                                               # part's group missing
        {**data, "version": 3},                                               # v3 has no groups
    ):
        fresh = Model(model.profile, model.library)
        with pytest.raises(ModelError):
            fresh.from_dict(bad)
        assert fresh.parts == {} and fresh.groups == {}


def test_group_cycles_refused(model):
    outer = model.add_group("outer").id
    inner = model.add_group("inner", outer).id
    with pytest.raises(ModelError):
        model.set_group_parent(outer, inner)
