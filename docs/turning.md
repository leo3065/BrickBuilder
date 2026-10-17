# How turning is checked (reference)

What happens between "the user drags a part with the Turn tool" and "the turn is committed or
refused", and which tolerances decide it. Design reasons are in `part_format.md` ("Pins", "Step B",
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
All contacts must share one stud axis (top studs: vertical; a side stud: horizontal), else the
plan is **locked** ("held by studs pointing different ways"). Everything below happens in the
plane across that axis, with coordinates (u, v) from `model.plane_basis(axis)` (X and Y for a
vertical axis). The moving set moves rigidly in that plane: angle θ about the axis through a
reference point `c` (the first contact's stud), plus a translation (x, y). For each contact, the
error that must stay zero is:
- a stud in a long slot: the stud's distance from the slot's line, i.e. `n · stud` with `n` the
  slot's normal in the plane: **one row**;
- a stud in a point antistud: both coordinates: **two rows**.

The stud's velocity for a motion (ω, vx, vy) is `(vx − ω·r.y, vy + ω·r.x)` with `r = stud − c`, so
each row is `n · [[−r.y, 1, 0], [r.x, 0, 1]]`. It doesn't matter which side the stud is on: only
the relative motion counts, and the sign of a row doesn't change its null space.

Stack the rows into `A` (k × 3) and take its singular values:
- **rank 3**: nothing moves: **locked** ("held by studs on different axes").
- Otherwise look for a turn about one of the contact studs: turning about point `p` is the motion
  `q = (1, r.y, −r.x)` with `r = p − c`. If `|A·q| < EPS·|q|`, that turn keeps every contact to
  first order, and since `p` is a stud on the axis it keeps it exactly. The first stud that passes
  (nearest the cursor when a hint is given) is the **pivot**: plan **turn**.
- Rank below 3 but no stud passes: the contacts only allow sliding (e.g. two studs in one long
  slot): **locked** ("only sliding").

Examples:

| Situation | Rows | Result |
|---|---|---|
| 1×4 on a 2×2 one-stud brick | 1 (slot line) | turn about the stud (sliding along the slot also free, not offered) |
| 1×4 on two studs of a 2×2 | 2, same normal | slide only → locked |
| Stud hinge (Seregios fold): A's stud in B's slot and B's stud in A's slot, one column | 2, different normals, both at the axis | turn about the column |
| Arm bridging two grounded 1×1s | 2, same normal | locked (wedged) |

### 4. Drag and snap (`Viewport._start_turn`, `_drag_turn`, `_finish_turn`)
The cursor ray meets the horizontal plane through the pivot; its angle around the pivot is
tracked with unwrapping, so the drag can go round more than once. The angle is rounded to
`rotation_snap` (7.5°) unless Shift is held. `[` / `]` turn by one step without dragging.
**Shift+R** (`realign_selection`) measures the moving part's frame rotation against the frame of
the part it's held by (the first contact's other side; the root grid if free) and turns by the
difference to the nearest multiple of 90°.

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

Op order: add frames, remove parts, set frames, add parts, remove frames (so parts never collide
with their own old positions). `_try_run` applies the ops one by one; if any fails (same-grid
overlap via the occupancy map, or a model error), or any moved part clashes with any part that
stayed (the full clash test, on its own grid too, the same as the preview), everything applied is
undone and the reason is returned. Nothing is pushed then. `move_parts` also does plain moves:
nudges (no target) and drags (`target_frame`: the grid it's put down on becomes every part's home,
see part_format.md "Moving the selection").

## The clash test (`collision.py`)
Used by the turn preview, `move_parts`, `can_place` (across frames), turned placement and
View > Highlight Colliding Parts. On one grid the sub-cell occupancy map decides instead (exact).
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
- One shared stud axis per turn: a part held by studs pointing different ways is locked. Ball
  joints will need their own contact rows (ball centre on cup pivot) and joint limits.
- Merging back onto the parent grid only happens for quarter turns about Z (parts only store Z
  turns), so a part on a side stud keeps its own frame.
- Only one moving body: the free-motion step doesn't solve chains or closed loops yet (the
  planned snapping solver does).
- Sliding along a slot is detected (it's in the null space) but not offered.
- Explicit pins don't exist yet; only grounded / largest.
- Placing on one grid doesn't run the stud part of the clash test (moves and turns do): a
  half-offset part placed so its studs miss the slots above isn't caught.
