# How turning is checked (reference)

What happens between "the user drags a part with the Turn tool" and "the turn is committed or
refused", and which tolerances decide it. Design reasons are in `design.md` ("Groups and pins", "Turning (step B)",
"Snapping solver"); this file describes the code as built (turns about any stud axis).

## Pipeline

```
selection ──► moving set ──► contacts ──► free motion ──► drag / snap ──► preview ──► commit
            motion.moving_set  iter_contacts  motion.plan_turn  Viewport._drag_turn  moved_overlaps  History.move_parts
```

### 1. Moving set: what turns (`motion.moving_set`)
1. Take the connected component(s) the selection belongs to (`Model.connections()`, the
   stud-in-slot graph).
2. Remove the selection; split what's left (the **rest**) into pieces that stay connected
   without going through the selection.
3. **The selection always moves.** Of the rest, the pieces that are pinned stay: grounded ones
   (a part on the root grid with `pos.z == 0`). If none is grounded, the largest piece stays (ties:
   the piece with the smaller part id). Explicit pins aren't built yet.
4. Moving = component − staying. So pieces that hang only off the selection come along, and
   if several grounded pieces hold the selection from different sides, they all stay (the free
   motion step then usually finds it locked: "wedged").

No staying pieces (the selection is a whole component, or only touches the rest through itself):
the plan is **free**, and the Turn tool turns about the centre of the moving parts' bounding box.

### 2. Contacts (`connections.iter_contacts`, `contacts_between`)
A contact is a stud of one part whose base lies on an antistud slot of another (a segment; a
point slot has zero length), with the stud pointing the way the slot expects (their axes within
`AXIS_TOLERANCE`; a side stud touching an underside doesn't count). The base may also be up to
half a stud height *below* the slot's plane: the underside is hollow, and half a stud in still holds. Positions and axes are world
space, so contacts work across frames, tilted ones too. Studs are bucketed by cell-sized world
boxes; a slot looks at the boxes it passes through.
`contacts_between(moving, staying)` collects both directions: moving studs in staying slots and
staying studs in moving slots.

### 3. Free motion (`motion.plan_turn`)
The moving set moves rigidly: a turn **w** (about any axis) plus a shift **v** of a reference
point `c` (the first contact), six numbers. Each contact, linearised, gives rows that must stay
zero (the velocity of a point `r` away from `c` is `v + w × r`, so along a direction `d` it's
`d·v + w·(r × d)`):
- **a stud in a long slot**: its base doesn't move across the slot or along the stud's axis (two
  rows), and the stud doesn't tilt off the slot's axis (`w` has no part across the axis: two rows);
- **a stud in a point antistud**: its base doesn't move at all (three rows) and doesn't tilt (two);
- **a ball in a cup**: its centre doesn't move (three rows).

Stack the rows into `A` (k × 6); the free motions are its null space (singular values ≤ `EPS`).
What's left decides the plan, from the turning parts of the free motions:
- **one turning axis** → **turn** about it: a stud or several on one axis (the Seregios fold), a
  side stud, two ball joints on one line (a hinge). The pivot is a contact on that line if turning
  about it is free (so the contact holds exactly, not just to first order); else a point worked out
  from the free motion. The axis points the way the holding studs do.
- **turning every way about a joint's centre** → **pose** (a single ball joint).
- **no turning** → **locked**; "only sliding" if a shift is free, else "held by studs on different
  axes" (e.g. two studs in one slot, or a top stud and a side stud).
- two turning axes, or three not about one joint: locked for now ("can't be posed yet").
Separately, a free motion with no turning in it (`TurnPlan.slide`) is a slide along a slot. Ctrl+drag in
the Turn tool offers it, in half-cell steps (Shift: free), and stops where the last stud would leave
its slot (`_slide_range`), so the part stays held.

| Situation | Rows | Free | Result |
|---|---|---|---|
| 1×4 on a 2×2 one-stud brick | 4 | turn about the stud, slide | turn (Ctrl+drag slides) |
| 1×4 on two studs of a 2×2 | 8, rank 5 | slide | locked, slides |
| Stud hinge (Seregios fold) | 8, rank 5 | turn about the column | turn |
| Arm bridging two grounded 1×1s | 8, rank 5 | slide (along the arm) | locked |
| One ball joint | 3 | turn any way about its centre | pose |
| Two ball joints on a line (Dragon wing) | 6, rank 5 | turn about the line | turn (a hinge) |

### 4. Drag and snap (`Viewport._start_turn`, `_drag_turn`, `_finish_turn`)
The cursor ray meets the horizontal plane through the pivot; its angle around the pivot is
tracked with unwrapping, so the drag can go round more than once. The angle is rounded to
`rotation_snap` (7.5°) unless Shift is held. `[` / `]` turn by one step without dragging.
**Shift+R** (`realign_selection`) measures the moving part's frame rotation against the frame of
the part it's held by (the first contact's other side; the root grid if free) and turns by the
difference to the nearest multiple of 90°.

**Posing a joint** (`_drag_pose`): the cursor's spot on the plane facing the camera through the
joint's centre gives a direction; the moving part points that way (a ball part's arm points away
from it, a cup part's body toward it). The arm direction relative to the cup is split into tilt θ
(from straight) and direction φ (around the cup's axis, from its slot), snapped to `rotation_snap`
(Shift: free) and clamped by `motion.clamp_arm`: inside the cone, else in the slot's plane (φ = 0 or
180) up to the slot's range. The turn is the smallest rotation that gets there, so the roll stays.
Ctrl+drag rolls about the arm (`_drag_roll`); `[ / ]` roll a step; Shift+R straightens; Ctrl+Shift+R
also undoes the roll (`reset_joint`: back the way it was placed, tops the same way). Any turn
that moves a joint (posing, rolling, a hinge, a turn elsewhere that drags a joint along) must keep
every joint within its limits (`Model.joints_within_limits`), else it's refused.

### 5. Preview (`Model.moved_overlaps`)
The moving parts' world geometry is transformed by the turn and tested with the **clash test**
(below) against every other part, cheap enough for every mouse move. The parts are drawn with
their own display lists under the turn matrix; red film if blocked.

### 6. Commit (`History.move_parts`, `_try_run`)
Builds one command (list of ops) for the world transform:
- **Owned frames** (every part in them and their child frames moves): the topmost ones get a
  `SetFrameOp` with the new transform; parts keep `pos`/`turns`.
- **Other moving parts**, per frame F: if the turn puts them on F's grid again
  (`model.to_parent_grid`: a multiple of 90° about Z and on the sub-grid) they're re-added on F
  with new `pos`/`turns`; otherwise a new frame (child of F, F's grid moved by the turn) is added
  and they move into it unchanged. Owned frames hanging off F move into that new frame.
- An owned frame that ends up lined up with its parent is merged into it (its child frames are
  re-parented, its parts converted, the frame removed).
- Frame reuse: parts or frames that don't line up with their home grid are checked against every
  other frame that stays put (`Model.lined_up_frames`). If one lines up, they go onto it instead of
  a new frame, so parts turned alike share a grid and can be bridged. Turned placement
  (`add_part_in_new_frame`) does the same.

Op order: add frames, remove parts, set frames, add parts, remove frames (so parts never collide
with their own old positions). `_try_run` applies the ops one by one; if any fails (same-grid
overlap via the occupancy map, or a model error), or any moved part clashes with any part that
stayed (the full clash test, on its own grid too, the same as the preview), everything applied is
undone and the reason is returned. Nothing is pushed then. `move_parts` also does plain moves:
nudges (no target) and drags (`target_frame`: the grid it's put down on becomes every part's home,
see design.md "Moving the selection").

## The clash test (`collision.py`)
Used by the turn preview, `move_parts`, `can_place`, turned placement and View > Highlight
Colliding Parts. On one grid the sub-cell occupancy map decides body overlap (exact), and the clash
test adds the studs.
- **Bodies**: every body is convex (box, rounded box, wedge), so two bodies are apart iff an axis
  separates them: a face normal of either, or the cross product of an edge direction from each
  (separating axis test, numpy). They clash only if they overlap by more than `PENETRATION` along
  **every** axis, so touching faces and round ends touching at a hinge are fine.
- **Studs**: the solids are solid, but real undersides are hollow along their slots. Each stud is
  an octagonal prism (profile stud diameter and height), along its own axis. A stud inside another
  part's body is fine only if it goes into one of that part's slots (`collision.in_slot`): pointing
  the slot's way, its centre line through the slot, and its base on or *below* the slot's plane. A
  lower stud just goes in less deep (e.g. a side stud 0.25 mm below the top stud a 1×3 sits on);
  a higher one would push into the ceiling and clashes, as does a stud off the slots (a part turned
  on a brick with several studs: the others poke into it). A stud counts as a contact (it holds)
  when at least half its height is in: base no more than half a stud height below the slot's plane.
- Broad phase: bounding boxes (part boxes widened by the stud height).

## Tolerances

| Name | Where | Value | Decides |
|---|---|---|---|
| `TOLERANCE` | connections.py | 1e-3 mm | a stud is in a slot |
| `EPS` | motion.py | 1e-4 mm | a contact error counts as zero (rank, pivot test). Float32 positions in turned frames are ~1e-6 mm off; 1e-6 here made hinges lock at some angles |
| `PENETRATION` | collision.py | 0.05 mm | overlap shallower than this is touching |
| angle / sub-grid | `model.to_parent_grid` | 1e-3° / 1e-3 sub-cell | a frame is lined up with its parent's grid (merge back) |
| quaternion length | `model.unit_quat` | 1e-6 | re-normalise only if off by more (avoids drift on save/load) |

## Placing a turned part (`turned_placement_problem`, `add_part_in_new_frame`)
The Place tool's `ghost_angle` turns the preview about the centre of its anchor cell (on the hit
part's grid). It's valid if it doesn't clash with anything and has at least one stud contact
(either way round). Placing adds a frame (that grid turned about the anchor cell centre) and the
part in it, as one undo step.

## Limits
- One moving body: chains of joints (turning inside a chain) and closed loops (Koraidon) need the
  full snapping solver, which would also solve for several frames at once.
- Merging back onto the parent grid only happens for quarter turns about Z (parts only store Z
  turns), so a part on a side stud keeps its own frame.
- Explicit pins don't exist yet; only grounded / largest.
