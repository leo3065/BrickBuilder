# Design decisions

The decisions behind the editor, and why, with the worked examples that tested them. The data
formats are in `part_format.md`, how the code does it in `architecture.md` and `turning.md`. ✅ =
built.

## Placing ✅
- The cell under the cursor is where the part's **anchor cell** goes: one of its bottom-layer cells,
  cycled with A / Shift+A (end / middle / end of a 1×3), starting nearest the centre (ties: +X, then
  +Y, in part coordinates). Rotation keeps the anchor under the cursor. Purely an editor aid: data
  stores the origin, and 90° turns pivot on the origin (an origin on a cell corner always maps the
  grid onto itself).
- Pointing at a sloped face targets the empty part of that face's own cell: nothing attaches to a
  slope, but that's where a complementary wedge goes.
- **Side-face placement is allowed**, even though such a part isn't held by anything (View >
  Highlight Unconnected Parts shows them).
- **No hard floor at layer 0.** A global floor makes no sense for parts in other frames, and building
  down from the top is legitimate. The Z = 0 grid is only a reference plane for ground placement.
- A placement that would put a stud somewhere it can't go (outside the slots above, flush against a
  side stud) is refused, like an overlap; the preview shows its slots and rings the studs in the way.

## Frames and contacts ✅
- A **frame** is a grid of its own: a transform (origin, rotation) relative to a parent frame. The
  root grid is frame 0. A placed part = (frame, position on that frame's sub-grid, quarter turns,
  part id, colour id).
- A socket type's `dof` decides what a connection does: `fixed` (a stud) keeps the parts on one grid
  in whole steps; `spherical` (a ball) gives the jointed part its own frame anchored at the joint, and
  parts built on it share that frame (this covers the Skarmory wings).
- **Free rotation** gives the turned part a new frame; bricks built on it snap to that frame. The
  angle is continuous; the **UI snaps** to the editor setting `rotation_snap` (default 7.5°, chosen
  because it divides 90° evenly). An editor preference, **not** a profile value.
- Parts on one frame form a rigid subassembly. Two subassemblies are **held** together if at least
  one contact links them: a stud in an antistud slot or point, or a ball in a cup. Sturdiness isn't
  modelled, only held or not. What a contact leaves free:

  | Contact | Fixes | Leaves free |
  |---|---|---|
  | Stud in a slot | the axes parallel, the stud on the slot's line | turning about the stud, sliding along the slot |
  | Stud in a point antistud | as above, plus the position | turning about the stud |
  | Ball in cup | the ball centre on the cup's pivot | roll, swing within the cone or the slot plane |
  | Several contacts | everything any of them fixes | only what all of them leave free |

  E.g. two coaxial ball/cup pairs make a **hinge**. Two studs of A on one level, both in slots of B
  (one long slot, or two parallel ones like a 2×N's rows), fix B's angle: B turns about the first
  stud until the second lands on a slot. That's how a 1×N sits **at an angle across two studs**,
  and what the planned "align" tool works out (one slot: the direction between the studs; two
  slots: a circle meets a line).
- **A local snapping solver, no physics.** It only moves the frames being dragged, only to satisfy
  contacts (see "Snapping solver"). Saves store each frame's transform; contacts are re-derived.
- **Snapping** (editor settings), on by default, Shift to move freely: sliding along a slot in
  half-cell steps; turning about an axis (a stud, a hinge) in `rotation_snap` steps; ball joints in
  three angles, each snapped like a rotation:
  - **tilt θ**: how far the arm tilts from straight (cone: θ ≤ 30° any way; slot: θ ≤ 90° only with
    φ along the slot, either way);
  - **direction φ**: which way it tilts, around the cup's axis;
  - **roll ψ**: about the ball part's own arm, applied before the swing so it doesn't change when φ
    does. At θ = 0, φ is meaningless.

  Saves store the joint as a rotation; the editor converts to θ, φ, ψ for display and dragging, so
  files don't depend on this choice of angles. Later on top: "land on a grid" (swing until a part on
  the moving side lines up with a nearby frame's grid).
- **Frames don't have to form a tree.** A part can bridge two frames; Koraidon/Miraidon-style
  bracing (bricks reaching past a joint) makes a closed loop. Connections form a **graph**, and frame
  parent links are only one spanning tree of it. Loops are allowed in the data and checked for
  consistency; nothing in the format assumes a tree.
- **Frame reuse ✅:** anything turned, moved, placed turned or placed on a side stud goes onto an
  existing frame whose grid lines up (quarter turns about its Z, whole sub-cells) before a new frame is
  made, so parts turned alike, or side studs in one plane, share a grid and can be bridged.

## Groups and pins ✅
Two separate trees:
- **Groups** (organising): named, nestable subassemblies made by the user, e.g. Rayquaza > Body >
  I-segment > its rings. They decide what a click selects and what a name refers to (later: parts
  lists per group, instances). Connectivity alone can't: a chain of ball joints makes a whole body
  one connected component.
- **Frames** (movement): a frame's parent is what it hangs on, so a chain of joints is a chain of
  frames. A group may hold several frames (a segment's rings at 0° and 45°), and a chain crosses many
  groups, so the two trees are kept apart.

**Selecting:** click selects the outermost group around the part, double-click drills one level in,
Alt+click always picks a single part. The outermost group under the cursor gets a soft outline on
hover; the Groups dock lists the tree with part counts and follows the selection; the status bar
names the selection's group. Clicking outside the drilled-into group (or Esc) goes back to the top.

**Grouping:** Ctrl+G takes the selection's largest whole groups as child groups and its loose parts
directly; the new group goes inside the deepest group they all share. Ungroup dissolves the
selection's whole groups one level. Deleting parts removes groups left empty (same undo step).
Placing a part doesn't group it.

**Pins:** every connected component has one pin, and components never affect each other. The pin is:
an explicitly pinned group in it (planned); else whatever touches the ground (root grid, layer 0);
else the side with more parts. Turning at a joint cuts the component there: the pinned side stays,
the other side moves.

**The selection always moves.** If the selection itself holds the pin, that pin is ignored for this
move: the selection plus whatever hangs only off it moves, and the pin rule, applied to the rest,
decides which side of the rest stays. E.g. body B on the ground with a tail T on one stud: turning T
turns T; turning B turns B about the stud and T stays. A move is refused only when the selection is
wedged between parts of the rest (a brace on both sides).

## Moving the selection ✅
- **Exactly the selection moves.** Moving is an edit, not a physical motion (unlike turning, nothing
  that hangs off it comes along); groups and Select Connected make it easy to take a whole
  subassembly. Contacts it leaves behind are broken.
- **Keyboard nudge never changes frames.** Arrow keys move it half a cell or a cell (following H)
  along the axis of its own grid nearest the screen direction; PgUp / PgDown a layer. Its own grid =
  the frame most selected parts are in (a turned arm slides along its turned grid).
- **Drag = pick up and put down**, like placing several parts at once: the grabbed part's bottom-layer
  cell under the cursor is the anchor; the target is found as for placing (a face, a side stud, else
  the working grid's ground). The selection's grid snaps onto the target's, so it **can change
  frames**, taking the target's orientation with its quarter turn kept (a fine turn is dropped).
  Space turns it 90°, [ / ] a fine turn relative to the target, Shift+R clears that.
- What moves stays rigid inside; groups don't change. Same validity as placing (no contact required).
  Emptied frames are removed. One undo step.
- Parts sitting half-offset on their grid (a 1×4 on a 2×2 one-stud) need H to drop things onto them.

## Turning (step B) ✅
The record of the step-B decisions; since extended to turning about any stud axis, side studs and
ball joints (how it works now: `turning.md`).
- **Turn tool (T).** Press on a part or the selection; the moving set follows the selection rule.
  Its contacts with the rest give the free motion; one stud or several on one axis: turn about it,
  otherwise locked with the reason. Drag turns in `rotation_snap` steps (Shift: free), [ / ] a step,
  Shift+R realigns to the nearest quarter turn of the grid it's held on (merging it back). R stays
  Erase outside the Turn tool. Red preview on overlap; one undo step per turn.
- **Frames.** A turned set gets its old grid turned about the pivot, so parts keep `pos` and `turns`
  and only the frame is new. A set that owns its frame turns that frame. Back to a multiple of 90° (on
  the parent's sub-grid): merged into the parent, the frame deleted. Frames hanging off the moving
  set come along.
- **Overlap across frames:** exact test on the convex solids; touching allowed (the Seregios round
  ends touch at every angle). The test also covers studs: one may be inside another body only through
  its slots.
- **Placing turned:** [ / ] turn the preview about the centre of its anchor cell (on a stud at a cell
  corner, e.g. a 2×2 one-stud, that needs H); placing creates the frame and needs a stud contact.
  **Working grid:** F over a part makes its grid the one used (and drawn) for empty space.
- **Sliding** along a slot: Ctrl+drag in the Turn tool, half-cell steps.

## Side studs ✅
Hovering the face a side stud sticks out of (one whose axis isn't the part's own up) targets the
stud's grid: Z along the stud, Y along the part's up (so parts stand upright in the wall plane), origin
on the stud's base, so cell (0, 0)'s centre is on the stud and layer 0 lies against the face. Side
studs in one plane share a frame (frame reuse), so a part can bridge them. A part on a side stud turns
about it. A stud a little below a slot's plane (e.g. a side stud 0.25 mm under the top stud a 1×3
sits on) goes into the hollow underside less deep; with at least half its height in, it holds.

## Ball joints ✅
Parts: nanoblock.info JO-C (cup) and JO-D (ball), each on a 1×2 (centred on a long side) or a 2×2
(centred on a side, pointing along its slots, in line with the ridge between them), at mid-height.
The Kawada manual calls them NAJO-C / NAJO-D.

**Range of movement** (from the real parts and the manual). Hold the cup fixed and look at the ball
side's arm direction `d`, relative to the cup's axis `a` and its slot direction `s`:
1. **Roll** about the arm itself: always free.
2. **Cone:** any `d` within about **30°** of straight, in any direction (the cup's rim).
3. **Slot:** `d` may also lie in the plane of `a` and `s`, tilted up to about **90° either way** (the
   slot is two-sided), with no sideways freedom there.

The slot runs **vertically**: its plane holds the cup's axis and the cup part's up, so mounting the cup
part on its side turns the 90° range from up/down into left/right (the manual's "横向き" 30° vs "縦向き"
90° pictures). The limits belong to the profile's `cup` socket type.

**Placing:** with a joint part chosen, hovering a matching joint puts it on straight: pivots together,
arm into the cup, tops the same way.

**Posing:** the turn finder works in full 3D (a turn about any axis plus a shift). A ball joint pins its
centre, so one joint gives turning any way about it (posing), two on a line a hinge, three off a line
nothing. Posing one joint: drag points the part at the cursor (on the plane facing the camera through
the joint: a joystick, not a fixed plane), θ and φ snapped and kept inside the cone, else in the
slot; Ctrl+drag rolls; [ / ] roll a step; Shift+R straightens (keeping the roll), Ctrl+Shift+R also
undoes the roll. Turns that would bend a joint past its limits are refused.

## Snapping solver (decided, partly built)
Local and geometric, not physics: it moves only the frames being dragged. Built: step 3 for one moving
body (`motion.plan_turn`). Not yet: least-squares snapping over several frames, chains, closed loops.
1. Every contact is an error to minimise: a stud's distance from its slot line and how far its axis
   tilts from the slot's, a ball's distance from its cup centre.
2. Snapping = least squares on those errors over the moving frames' 6 numbers each, starting from
   where the user dragged (numpy; a few frames and contacts, so fast). Limits and snap angles on top.
3. Free motions come from the same setup: the directions in which the errors don't change (the
   constraint Jacobian's null space). Collinear balls give one (a hinge), non-collinear none, one stud
   turning about it plus sliding along its slot. No special cases.
4. After solving: contacts within tolerance, limits respected, no overlap; otherwise refused with the
   reason. Dragging inside a closed loop (Koraidon) keeps it closed instead of being refused.

Later: **instances** (define a subassembly once, place it several times, edits update all, like the
manual's "×3" or LDraw multi-part files).

## Worked examples
**Stud hinge (Seregios wing fold).** Two rigid halves built in layers meet in a **fold column**. In
each layer one side's round 1×N end sits in that column, alternating between the sides (bottom to
top: A, B, A, A, B, A). The A–B contacts (A studs in B slots, B studs in A slots) are all on one
vertical axis through the column. Shared freedom: turning about that axis. Because slots from both
sides take part, sliding locks as soon as it bends. Within half a cell of the axis everything is a
round end, and plain ends start half a cell from it, so the parts touch but never overlap. ✅ Tested.

**Two ball joints as a hinge, in a chain (Dragon wing).** Group G has two cups, group H two balls.
Together the joints leave only turning about the line through both centres (if equally spaced). The
range is where **both** joints stay within limits: an axis across the cups' slot planes swings the
arms inside their slots (about ±90°); an axis along them swings them sideways (±30°). The wing is a
chain, body → G → H: frames nest along it (H's frame a child of G's) while the groups stay separate.
With the body pinned, turning H moves only H; turning G moves G and H. ✅ The two-joint hinge is
tested; turning inside a chain needs the solver.

**Use cases from real sets** (each becomes a test):
| Case | Contacts | Freedom left | Solver's job |
|---|---|---|---|
| Blue-Eyes White Dragon DX: 3 balls in a line | 3 fixed centres, collinear | hinge (1) | check equal spacing |
| …3 balls not in a line | 3 fixed centres | none: locked | the one pose where all meet |
| Koraidon: chain of 3 parts by ball joints, both ends on the body | closed loop of 4 joints | ~3, plus each middle link spinning about its two-joint axis | keep the loop closed while posing |
| Miraidon: a subassembly on its side, 2 studs into 2 slots | 2 stud contacts, different axes | none if spacing fits | place it so both line up |
| Dragon: 2×2 round as a 45° adapter | studs in its centre hole and diagonal slots | none | find the 45° turn |
| Seregios wing fold, Dragon wing (above) | stud hinge; 2 ball joints | hinge (1) | one snapped angle within limits |

## Build history
1. Profile file + a single cell-to-world function used by the renderer, picking and camera.
2. Parts limited to boxes with derived studs; occupancy map; placed-part model; save v2.
3. Library panel (Parts tree by category).
4. Slopes, rounded bodies, explicit sockets, connections; frames (step A); groups; the Turn tool and
   turned placement (step B); moving the selection; side studs and tilted frames; ball joints and
   posing; camera views. Next: copy/paste, the full solver, circular arrays, modifiers, mesh bodies.
