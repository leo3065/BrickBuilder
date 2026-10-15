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


@dataclass(frozen=True)
class RemoveOp:
    part_id: int
    part: PartDef
    pos: Sub
    turns: int
    color: str
    frame: int = 0


@dataclass(frozen=True)
class ColorOp:
    part_id: int
    old: str
    new: str


Op = Union[AddOp, RemoveOp, ColorOp]
Command = List[Op]

_UNREACHABLE: Command = []  # a clean point that undo can never return to


def _snapshot(cls, placed: PlacedPart):
    return cls(placed.id, placed.part, placed.pos, placed.turns, placed.color, placed.frame)


def _inverse(op: Op) -> Op:
    if isinstance(op, AddOp):
        return RemoveOp(op.part_id, op.part, op.pos, op.turns, op.color, op.frame)
    if isinstance(op, RemoveOp):
        return AddOp(op.part_id, op.part, op.pos, op.turns, op.color, op.frame)
    return ColorOp(op.part_id, op.new, op.old)


def _apply(model: Model, op: Op) -> None:
    if isinstance(op, AddOp):
        if model.add_part(op.part, op.pos, op.turns, op.color, op.part_id, op.frame) is None:
            # Can't happen if every edit goes through History
            raise RuntimeError(f"history out of sync: can't re-add part {op.part_id}")
    elif isinstance(op, RemoveOp):
        model.remove_part(op.part_id)
    else:
        model.set_color(op.part_id, op.new)


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

    def remove_part(self, part_id: int) -> None:
        placed = self.model.parts.get(part_id)
        if placed is None:
            return
        self.model.remove_part(part_id)
        self._push([_snapshot(RemoveOp, placed)])

    def set_color(self, part_id: int, color: str) -> None:
        old = self.model.parts[part_id].color
        if old == color:
            return
        self.model.set_color(part_id, color)
        self._push([ColorOp(part_id, old, color)])

    def remove_parts(self, part_ids) -> None:
        """Remove several parts as one undo step."""
        command = []
        for part_id in sorted(set(part_ids)):
            placed = self.model.parts.get(part_id)
            if placed is not None:
                self.model.remove_part(part_id)
                command.append(_snapshot(RemoveOp, placed))
        if command:
            self._push(command)

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
