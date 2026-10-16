"""Undo/redo for model edits.

Every edit goes through History, which applies it to the model and records enough to reverse
it. One user action is one command (a list of operations), so future multi-part actions
(multi-select, shift-all) undo in one step.
"""
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Union

from brickbuilder.core.model import Model, PlacedPart, Sub
from brickbuilder.core.parts import PartDef

DEFAULT_UNDO_LIMIT = 500  # TODO(preferences): make configurable


@dataclass(frozen=True)
class AddOp:
    part_id: int
    part: PartDef
    pos: Sub
    turns: int
    color: str
    frame: int = 0
    group: Optional[int] = None


@dataclass(frozen=True)
class RemoveOp:
    part_id: int
    part: PartDef
    pos: Sub
    turns: int
    color: str
    frame: int = 0
    group: Optional[int] = None


@dataclass(frozen=True)
class ColorOp:
    part_id: int
    old: str
    new: str


@dataclass(frozen=True)
class AddGroupOp:
    group_id: int
    name: str
    parent: Optional[int]


@dataclass(frozen=True)
class RemoveGroupOp:
    """Removes an empty group."""
    group_id: int
    name: str
    parent: Optional[int]


@dataclass(frozen=True)
class PartGroupOp:
    part_id: int
    old: Optional[int]
    new: Optional[int]


@dataclass(frozen=True)
class GroupParentOp:
    group_id: int
    old: Optional[int]
    new: Optional[int]


@dataclass(frozen=True)
class RenameGroupOp:
    group_id: int
    old: str
    new: str


Op = Union[AddOp, RemoveOp, ColorOp, AddGroupOp, RemoveGroupOp, PartGroupOp, GroupParentOp, RenameGroupOp]
Command = List[Op]

_UNREACHABLE: Command = []  # a clean point that undo can never return to


def _snapshot(cls, placed: PlacedPart):
    return cls(placed.id, placed.part, placed.pos, placed.turns, placed.color, placed.frame, placed.group)


_INVERSE = {AddOp: RemoveOp, RemoveOp: AddOp, AddGroupOp: RemoveGroupOp, RemoveGroupOp: AddGroupOp}


def _inverse(op: Op) -> Op:
    if type(op) in _INVERSE:
        return _INVERSE[type(op)](**vars(op))
    if isinstance(op, ColorOp):
        return ColorOp(op.part_id, op.new, op.old)
    return type(op)(next(iter(vars(op).values())), op.new, op.old)  # (id, old, new) swapped


def _apply(model: Model, op: Op) -> None:
    if isinstance(op, AddOp):
        if model.add_part(op.part, op.pos, op.turns, op.color, op.part_id, op.frame, op.group) is None:
            # Can't happen if every edit goes through History
            raise RuntimeError(f"history out of sync: can't re-add part {op.part_id}")
    elif isinstance(op, RemoveOp):
        model.remove_part(op.part_id)
    elif isinstance(op, ColorOp):
        model.set_color(op.part_id, op.new)
    elif isinstance(op, AddGroupOp):
        model.add_group(op.name, op.parent, op.group_id)
    elif isinstance(op, RemoveGroupOp):
        model.remove_group(op.group_id)
    elif isinstance(op, PartGroupOp):
        model.set_part_group(op.part_id, op.new)
    elif isinstance(op, GroupParentOp):
        model.set_group_parent(op.group_id, op.new)
    else:
        model.rename_group(op.group_id, op.new)


class History:
    def __init__(self, model: Model, limit: int = DEFAULT_UNDO_LIMIT) -> None:
        self.model = model
        self._undo: Deque[Command] = deque(maxlen=limit)
        self._redo: List[Command] = []
        self._clean: Optional[Command] = None  # top of the undo stack when last saved/loaded

    # --- edits --------------------------------------------------------------------------

    def add_part(self, part: PartDef, pos: Sub, turns: int, color: str, frame: int = 0) -> Optional[PlacedPart]:
        placed = self.model.add_part(part, pos, turns, color, frame=frame)
        if placed is not None:
            self._push([_snapshot(AddOp, placed)])
        return placed

    def set_color(self, part_id: int, color: str) -> None:
        old = self.model.parts[part_id].color
        if old == color:
            return
        self.model.set_color(part_id, color)
        self._push([ColorOp(part_id, old, color)])

    def remove_parts(self, part_ids) -> None:
        """Remove several parts as one undo step. Groups left empty go too."""
        command: Command = []
        for part_id in sorted(set(part_ids)):
            placed = self.model.parts.get(part_id)
            if placed is not None:
                self.model.remove_part(part_id)
                command.append(_snapshot(RemoveOp, placed))
        if command:
            prune = self._prune_groups()
            for op in prune:
                _apply(self.model, op)
            self._push(command + prune)

    def remove_part(self, part_id: int) -> None:
        self.remove_parts([part_id])

    # --- groups -------------------------------------------------------------------------

    def group(self, part_ids, name: str) -> Optional[int]:
        """Put a selection into a new group, as one undo step. Whole groups in the selection
        go in as child groups; the new group sits where the selection's groups meet."""
        groups, loose = self.model.top_units(part_ids)
        if not groups and not loose:
            return None
        parents = [self.model.groups[g].parent for g in groups] + [self.model.parts[p].group for p in loose]
        chains = [self.model.group_ancestors(p) for p in parents]
        parent = None
        for level in zip(*chains):  # deepest group every unit is inside
            if len(set(level)) != 1:
                break
            parent = level[0]
        new_id = max(self.model.groups, default=0) + 1
        command: Command = [AddGroupOp(new_id, name, parent)]
        command += [GroupParentOp(g, self.model.groups[g].parent, new_id) for g in sorted(groups)]
        command += [PartGroupOp(p, self.model.parts[p].group, new_id) for p in sorted(loose)]
        command += self._prune_groups(command)
        self._run(command)
        return new_id

    def ungroup(self, group_ids) -> None:
        """Dissolve groups one level, as one undo step: their parts and child groups move up
        to the group's parent."""
        command: Command = []
        for gid in sorted(set(group_ids)):
            group = self.model.groups.get(gid)
            if group is None:
                continue
            command += [GroupParentOp(g.id, gid, group.parent)
                        for g in sorted(self.model.groups.values(), key=lambda g: g.id) if g.parent == gid]
            command += [PartGroupOp(p.id, gid, group.parent)
                        for p in sorted(self.model.parts.values(), key=lambda p: p.id) if p.group == gid]
            command.append(RemoveGroupOp(gid, group.name, group.parent))
        if command:
            self._run(command)

    def rename_group(self, group_id: int, name: str) -> None:
        old = self.model.groups[group_id].name
        if old != name:
            self._run([RenameGroupOp(group_id, old, name)])

    def _run(self, command: Command) -> None:
        for op in command:
            _apply(self.model, op)
        self._push(command)

    def _prune_groups(self, pending: Command = ()) -> Command:
        """Ops removing the groups that are (or, after the not yet applied `pending` ops, will
        be) empty, innermost first. Doesn't touch the model."""
        parent = {g.id: g.parent for g in self.model.groups.values()}
        names = {g.id: g.name for g in self.model.groups.values()}
        part_group = {p.id: p.group for p in self.model.parts.values()}
        for op in pending:
            if isinstance(op, AddGroupOp):
                parent[op.group_id], names[op.group_id] = op.parent, op.name
            elif isinstance(op, GroupParentOp):
                parent[op.group_id] = op.new
            elif isinstance(op, PartGroupOp):
                part_group[op.part_id] = op.new
        ops: Command = []
        while True:
            used = set(part_group.values()) | set(parent.values())
            empty = sorted(g for g in parent if g not in used)
            if not empty:
                return ops
            for g in empty:
                ops.append(RemoveGroupOp(g, names[g], parent[g]))
                del parent[g]

    def set_colors(self, part_ids, color: str) -> None:
        """Recolour several parts as one undo step."""
        command = []
        for part_id in sorted(set(part_ids)):
            old = self.model.parts[part_id].color
            if old != color:
                self.model.set_color(part_id, color)
                command.append(ColorOp(part_id, old, color))
        if command:
            self._push(command)

    # --- undo / redo --------------------------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        command = self._undo.pop()
        for op in reversed(command):
            _apply(self.model, _inverse(op))
        self._redo.append(command)
        self._sync_modified()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        command = self._redo.pop()
        for op in command:
            _apply(self.model, op)
        self._undo.append(command)
        self._sync_modified()
        return True

    # --- clean state (saved / loaded / new) ---------------------------------------------

    def mark_clean(self) -> None:
        """The model now matches what's on disk (or is a fresh document)."""
        self._clean = self._top()
        self._sync_modified()

    def reset(self) -> None:
        """Forget all history, e.g. after New or Open."""
        self._undo.clear()
        self._redo.clear()
        self.mark_clean()

    def _top(self) -> Optional[Command]:
        return self._undo[-1] if self._undo else None

    def _push(self, command: Command) -> None:
        if len(self._undo) == self._undo.maxlen:
            # The oldest step is about to drop off. If the saved state was before it (or was
            # that step), undo can no longer get back there.
            if self._clean is None or self._clean is self._undo[0]:
                self._clean = _UNREACHABLE
        self._undo.append(command)
        self._redo.clear()
        self._sync_modified()

    def _sync_modified(self) -> None:
        # Identity, not equality: two identical edits are still different points in history
        self.model.modified = self._top() is not self._clean
