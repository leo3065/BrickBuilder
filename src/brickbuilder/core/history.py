"""Undo/redo for model edits.

Every edit goes through History, which applies it to the model and records enough to reverse
it. One user action is one command (a list of operations), so multi-part actions (deleting or
recolouring a selection, grouping, moving, turning) undo in one step. Commands that can fail
(moves, turns, turned placement) go through _try_run, which rolls back and returns the reason.
"""
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Union

import glm

from brickbuilder.core.model import Model, ModelError, PlacedPart, Sub, decompose, to_parent_grid
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


@dataclass(frozen=True)
class AddFrameOp:
    frame_id: int
    parent: int
    origin: glm.vec3
    rotation: glm.quat


@dataclass(frozen=True)
class RemoveFrameOp:
    """Removes an empty frame with no child frames."""
    frame_id: int
    parent: int
    origin: glm.vec3
    rotation: glm.quat


@dataclass(frozen=True)
class SetFrameOp:
    frame_id: int
    old: tuple  # (parent, origin, rotation)
    new: tuple


Op = Union[AddOp, RemoveOp, ColorOp, AddGroupOp, RemoveGroupOp, PartGroupOp, GroupParentOp, RenameGroupOp,
           AddFrameOp, RemoveFrameOp, SetFrameOp]
Command = List[Op]

_UNREACHABLE: Command = []  # a clean point that undo can never return to


def _snapshot(cls, placed: PlacedPart):
    return cls(placed.id, placed.part, placed.pos, placed.turns, placed.color, placed.frame, placed.group)


_INVERSE = {AddOp: RemoveOp, RemoveOp: AddOp, AddGroupOp: RemoveGroupOp, RemoveGroupOp: AddGroupOp,
            AddFrameOp: RemoveFrameOp, RemoveFrameOp: AddFrameOp}


class OutOfSync(RuntimeError):
    """An op couldn't be applied (e.g. a re-added part overlaps)."""


def _inverse(op: Op) -> Op:
    if type(op) in _INVERSE:
        return _INVERSE[type(op)](**vars(op))
    if isinstance(op, ColorOp):
        return ColorOp(op.part_id, op.new, op.old)
    return type(op)(next(iter(vars(op).values())), op.new, op.old)  # (id, old, new) swapped


def _apply(model: Model, op: Op) -> None:
    if isinstance(op, AddOp):
        if model.add_part(op.part, op.pos, op.turns, op.color, op.part_id, op.frame, op.group) is None:
            # Can't happen for undo/redo if every edit goes through History
            raise OutOfSync(f"part {op.part_id} would overlap a part on the same grid")
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
    elif isinstance(op, AddFrameOp):
        model.add_frame(op.parent, op.origin, op.rotation, op.frame_id)
    elif isinstance(op, RemoveFrameOp):
        model.remove_frame(op.frame_id)
    elif isinstance(op, SetFrameOp):
        model.set_frame(op.frame_id, *op.new)
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
            prune += self._prune_frames()
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

    def add_part_in_new_frame(self, part: PartDef, pos: Sub, turns: int, color: str, parent: int,
                              origin: glm.vec3, rotation: glm.quat) -> Optional[PlacedPart]:
        """Place a part on a grid of its own (a child of `parent`), as one undo step; None if it
        would overlap something (nothing changes then). If an existing frame lines up with that
        grid, the part goes into it instead (so parts turned alike can be bridged)."""
        part_id = self.model._next_id
        grid = self.model.frame_matrix(parent) * glm.translate(glm.mat4(1.0), origin) * glm.mat4_cast(rotation)
        for frame, o, r in self.model.lined_up_frames(grid):
            converted = to_parent_grid(self.model.profile, o, r, pos, turns)
            if converted is not None:
                command = [AddOp(part_id, part, converted[0], converted[1], color, frame)]
                break
        else:
            frame_id = max(self.model.frames) + 1
            command = [AddFrameOp(frame_id, parent, glm.vec3(origin), glm.quat(rotation)),
                       AddOp(part_id, part, pos, turns, color, frame_id)]
        if self._try_run(command, [part_id]) is not None:
            return None
        return self.model.parts[part_id]

    # --- moving parts across frames ----------------------------------------------------------

    def move_parts(self, part_ids, transform: glm.mat4, target_frame: Optional[int] = None) -> Optional[str]:
        """Move parts rigidly by a world transform, as one undo step. Returns None if done, or
        why it can't be (nothing changes then).

        `target_frame`: the grid they're being put down on (a drag). Without it (turning,
        nudging) each part's home is the grid it's on; with it, that frame is everyone's home:
        parts lined up with it go onto it, new frames and moved frames become its children.

        Frames: a frame whose parts (with everything in its child frames) all move is moved
        itself. Other moving parts get a new frame, their old grid moved, as a child of it, so
        they keep their grid positions; moved frames hanging off that grid go into the new frame.
        Anything that ends up lined up with its parent's grid (a multiple of 90 degrees, on the
        sub-grid) goes onto that grid instead, else onto any other frame it lines up with (so parts
        turned alike share a grid), and an emptied frame is removed."""
        m = self.model
        moving = set(part_ids) & set(m.parts)
        if not moving:
            return "nothing to move"

        def subtree_parts(f):
            inside = m.frame_subtree(f)
            return {p.id for p in m.parts.values() if p.frame in inside}
        owned = {f for f in m.frames if f != 0 and subtree_parts(f) and subtree_parts(f) <= moving}
        tops = sorted(f for f in owned if m.frames[f].parent not in owned)
        under_owned = set().union(*(m.frame_subtree(f) for f in owned)) if owned else set()
        loose: Dict[int, List[int]] = {}
        for pid in sorted(moving):
            if m.parts[pid].frame not in under_owned:
                loose.setdefault(m.parts[pid].frame, []).append(pid)

        # Removes before adds, so moved parts never collide with their own old positions
        add_frames: Command = []
        removes: Command = []
        set_frames: Command = []
        adds: Command = []
        remove_frames: Command = []
        next_frame = max(m.frames) + 1
        new_frame_for: Dict[int, int] = {}

        def frame_tuple(f):
            fr = m.frames[f]
            return (fr.parent, fr.origin, fr.rotation)

        def move_into(pids, frame, converted=None):
            for pid in pids:
                p = m.parts[pid]
                removes.append(_snapshot(RemoveOp, p))
                pos, turns = converted[pid] if converted else (p.pos, p.turns)
                adds.append(AddOp(pid, p.part, pos, turns, p.color, frame, p.group))

        def on_parent_grid(origin, rotation, pids):
            out = {pid: to_parent_grid(m.profile, origin, rotation, m.parts[pid].pos, m.parts[pid].turns)
                   for pid in pids}
            return out if all(c is not None for c in out.values()) else None

        def lined_up_elsewhere(grid, pids, skip):
            """A frame that stays put and that `grid` lines up with, and the parts' positions on it."""
            for frame, o, r in m.lined_up_frames(grid, exclude=under_owned | {skip}):
                converted = on_parent_grid(o, r, pids)
                if converted is not None:
                    return frame, converted
            return None

        def merge(g, into, rel, converted):
            """Frame g's parts onto frame `into` (rel: g's moved grid in `into`'s space), its child
            frames re-parented, g removed."""
            frame = m.frames[g]
            for child in sorted(f.id for f in m.frames.values() if f.parent == g):
                set_frames.append(SetFrameOp(child, frame_tuple(child),
                                             (into, *decompose(rel * m.frames[child].local_matrix()))))
            move_into([p.id for p in m.parts.values() if p.frame == g], into, converted)
            remove_frames.append(RemoveFrameOp(g, frame.parent, frame.origin, frame.rotation))

        for f, pids in sorted(loose.items()):
            home = f if target_frame is None else target_frame
            origin, rotation = decompose(glm.inverse(m.frame_matrix(home)) * transform * m.frame_matrix(f))
            converted = on_parent_grid(origin, rotation, pids)
            elsewhere = None if converted is not None else \
                lined_up_elsewhere(transform * m.frame_matrix(f), pids, home)
            if converted is not None:
                move_into(pids, home, converted)  # e.g. a quarter turn: stays on (or lands on) the grid
            elif elsewhere is not None:
                move_into(pids, *elsewhere)
            else:
                new_frame_for[f] = next_frame
                add_frames.append(AddFrameOp(next_frame, home, origin, rotation))
                move_into(pids, next_frame)
                next_frame += 1

        for g in tops:
            frame = m.frames[g]
            if frame.parent in new_frame_for:
                parent = new_frame_for[frame.parent]
                origin, rotation = frame.origin, frame.rotation
            else:
                parent = frame.parent if target_frame is None else target_frame
                origin, rotation = decompose(glm.inverse(m.frame_matrix(parent)) * transform * m.frame_matrix(g))
            own = [p.id for p in m.parts.values() if p.frame == g]
            moved_grid = transform * m.frame_matrix(g)
            converted = None if parent in new_frame_for.values() else on_parent_grid(origin, rotation, own)
            elsewhere = None
            if converted is None and parent not in new_frame_for.values():
                elsewhere = lined_up_elsewhere(moved_grid, own, parent)
            if converted is not None:
                # Lined up with its parent again: merge into it
                merge(g, parent, glm.translate(glm.mat4(1.0), origin) * glm.mat4_cast(rotation), converted)
            elif elsewhere is not None:
                # Lined up with another grid that stays put: merge into that
                merge(g, elsewhere[0], glm.inverse(m.frame_matrix(elsewhere[0])) * moved_grid, elsewhere[1])
            else:
                set_frames.append(SetFrameOp(g, frame_tuple(g), (parent, origin, rotation)))
        return self._try_run(add_frames + removes + set_frames + adds + remove_frames, moving)

    def _try_run(self, command: Command, moved=()) -> Optional[str]:
        """Apply a command; if an op fails or a moved part ends up overlapping a part on another
        grid, undo what was applied and return why."""
        done: Command = []
        reason = None
        try:
            for op in command:
                _apply(self.model, op)
                done.append(op)
        except (OutOfSync, ModelError) as e:
            reason = str(e)
        if reason is None:
            # Against everything that stayed, not only other grids: the same test as the preview
            # (Model.moved_overlaps), so a stud outside a slot blocks on one grid too
            moved = set(moved)
            for pid in sorted(moved):
                shape = self.model.part_shape(pid)
                hit = self.model.clashes(shape, lambda q: q.id in moved)
                if hit:
                    reason = self.model.clash_reason(shape, hit[0])
                    break
        if reason is not None:
            for op in reversed(done):
                _apply(self.model, _inverse(op))
            return reason
        self._push(command)
        return None

    def _run(self, command: Command) -> None:
        for op in command:
            _apply(self.model, op)
        self._push(command)

    def _prune_frames(self) -> Command:
        """Remove the frames left with no parts and no child frames (innermost first); applied."""
        ops: Command = []
        while True:
            used = {p.frame for p in self.model.parts.values()} | {f.parent for f in self.model.frames.values()}
            empty = sorted(f for f in self.model.frames if f != 0 and f not in used)
            if not empty:
                return ops
            for f in empty:
                fr = self.model.frames[f]
                op = RemoveFrameOp(f, fr.parent, fr.origin, fr.rotation)
                _apply(self.model, op)
                ops.append(op)

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
