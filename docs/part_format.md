# Profiles, part definitions and the part library — design

Status: **design notes, with ✅ marking what's implemented.** Built so far: profile + palette, box,
rounded box and wedge (slope) bodies, explicit stud/antistud sockets, placed-part model with exact
slope occupancy, connections, frames, groups, turning and moving (save v4). Part files carry `name` and `[[body]]` (`shape = "box"` with
`size`, optional `at`, `studs = "top" | "none"`; or `shape = "wedge"` with `keep` and `tall`
too); id and category come from the file path.

## Goals
- Nanoblock is the only system we author parts for, but nothing system-specific lives in
  code (see "Scope" in `CLAUDE.md`).
- Part files are **hand-written and readable**. Meaning (occupancy, connections) comes
  first; render geometry is derived from it.
- Fix what LDraw lacks for this use: no occupancy, no connection semantics (LDCad bolts
  them on via a separate "shadow library" of `SNAP_*` metas), raw 12-number matrices,
  triangle-level authoring, Lego-specific units.
- Keep from LDraw: reusable sub-parts/primitives and a category-folder library.

## File format ✅
TOML. Python 3.13 reads it with the stdlib `tomllib`; files are hand-authored, so no
writer is needed.

## Layer 1 — Profile (one per brick system)
Everything that differs between brick systems. Parts and models refer to a profile by `id`.

```toml
id = "nanoblock"
name = "Nanoblock"
cell = [4.0, 4.0, 3.125]      # mm: stud pitch X/Y, stacking pitch Z (measured, see table)
subdiv = [2, 2, 1]            # placement sub-grid per cell: half-cells in XY, whole cells in Z
grid_rotation = 90.0          # rotations that keep a part on its frame's grid

clearance = 0.05              # cosmetic seam between bodies; real gap is below caliper resolution
body_height = 3.05            # rendering only; stacking pitch minus seating gap

[stud]                        # used to generate stud/antistud geometry
diameter = 2.45
height = 1.60
hollow_diameter = 0.0         # solid

[[underside]]                 # where studs fit under a body (first match by its short side)
max_short_side = 2            # 1xN and 2xN: one slot per row, along the long side
slots = "rows"
[[underside]]
slots = "none"                # wider (base plates): none for now

[socket_types]
stud     = { mates = ["antistud"], dof = "fixed" }
antistud = { mates = ["stud"],     dof = "fixed" }
ball     = { mates = ["cup"],      dof = "spherical" }
cup      = { mates = ["ball"],     dof = "spherical" }

[palette]                     # or a separate palette file referenced here
# id = { name = "...", rgb = "#rrggbb" }
```

`subdiv` is how other systems stay data-only: e.g. Lego plates would be `[1, 1, 3]` in a
Lego profile. Positions are stored as integers on this sub-grid, so there's no float drift.

`[[underside]]` ✅ is the other system-specific rule: how a part's underside takes studs when the
part file doesn't list antistud sockets. Rules are tried in order; the first whose `max_short_side`
the body's footprint fits (omitted = any) names a pattern. Patterns are implemented in code
(`profile.UNDERSIDE_PATTERNS`): `rows` (one slot per row of cells along the long side, Y on a tie;
a 1×N gets its middle line, a 1×1 a point) and `none`. A system with a different underside (e.g.
Lego's tubes between studs) adds a pattern when it's actually needed. No rules: no derived
antistuds, so every part would list its own.

## Layer 2 — Part definition
All lengths are in **cells** of the part's profile, not mm. That makes files readable, and if
a measurement is corrected in the profile, no part files need editing.

Origin: the minimum corner of the part's bounding cells, at the bottom. ✅ 90° rotations pivot
on the **part origin**. A footprint isn't well defined for every part (meshes, joints), and an
origin on a cell corner always maps the grid onto itself. The UI may re-anchor the part so it
doesn't appear to jump; that's a presentation detail, not part of the data.

```toml
profile = "nanoblock"
id = "brick_2x4"
name = "Brick 2×4"
category = "Basic/Bricks"
tags = ["brick"]

[[body]]
shape = "box"
size = [2, 4, 1]
studs = "top"         # derive stud sockets + geometry on every top cell
antistuds = "bottom"  # derive antistud sockets on every bottom cell
```

### Bodies
| shape      | purpose                                   | occupancy            |
|------------|-------------------------------------------|----------------------|
| `box`      | ordinary bricks                           | derived (all cells)  |
| `slope`    | box + right-triangle profile, extruded    | derived (whole cells)|
| `cylinder` | round parts                               | derived (bounding cells) |
| `mesh`     | escape hatch: `file = "ball.obj"`         | **must be declared** |

✅ A box can round its vertical edges with `corner_radius` (cells): one number for all four corners
(at most half the shorter side; `0.5` on a 1×N gives semicircular ends), or a table per corner,
e.g. `{ "+x+y" = 2 }` for the 2×2 fan's quarter circle (two corners on one side can't round more
than its length). Occupancy is decided per **sub-cell**: one entirely outside a rounded corner
(touching the curve at most) is free, any other counts as full; curves can't be exact on the
sub-grid. A derived stud is dropped when its cell's centre is cut away. A rounded box must be the
part's only body for now.

`studs` takes `"top"` or `"none"` (flat parts such as NB102F). Explicit stud sockets ✅ cover
irregular layouts (single-stud parts such as NB102S/NB202S1).

**Slope profile ✅:** seen from the side, a slope is a box (base) plus a right triangle sitting on
it, extruded along the other horizontal axis. Studs aren't part of the outline. ✅ Ignoring studs,
the triangle is always one of the two halves of an **m (cells) × n (layers) rectangle** cut along
its diagonal, so its corners are whole numbers on the sub-grid. Inverted slopes keep the upper
half instead (solid top, sloped underside).

So the body type is a **wedge**: a box cut along its diagonal, keeping the lower or upper half.
A slope part is a box body plus a wedge body (sketch, not final):
```toml
# NB102A, 1x2 slope: 1x2x1 base; on one cell a lower triangle 1 cell x 1 layer,
# its vertical face at the part's centre (the slope faces away from the centre)
[[body]]
shape = "box"
size = [1, 2, 1]
[[body]]
shape = "wedge"
size = [1, 1, 1]        # m x n of the rectangle, extruded across the slope
at = [0, 0, 1]
keep = "lower"          # lower = solid bottom, sloped top; upper = solid top, sloped underside
tall = "+y"             # side where the wedge is full height

# NB102B, inverted 1x2: one full cell, beside it an upper triangle 1 x 1, tall next to the box
[[body]]
shape = "box"
size = [1, 1, 1]
[[body]]
shape = "wedge"
size = [1, 1, 1]
at = [0, 1, 0]
keep = "upper"
tall = "-y"
```
NB10202A (1×2×2 slope) and NB10202V (1×2×2 offset, inverted) are the same with wedge size
`[1, 1, 2]`: a 2-layer triangle, so NB10202A peaks 3 layers above its bottom. ✅ This resolves the
earlier question: the LDraw NB10202A is drawn 2.5 LDU (1 mm) too short.

Each pair (NB102A + NB102B, NB10202A + NB10202V) fits together because the two wedges are the same
rectangle cut along the same diagonal, on opposite sides; complementary wedges have both `keep`
and `tall` flipped. Studs: a lower wedge's sloped top has none; an upper wedge's flat top does.

**Connections ✅:** a normal slope's sloped top is solid: no studs, and nothing attaches to it. An
**inverted slope's underside is open** (walls only on the sides, none along the slope), so it has
antistud sockets under its whole footprint, including under the slope, and a stud from below fits
into the hollow. If studs are ever collision-checked, that underside counts as open.

Occupancy is tracked per **sub-cell** of the profile's `subdiv` grid (so half-offset parts work).
Boxes fill whole sub-cells. **Slope occupancy ✅ (implemented):** each body is a box optionally cut by the
triangle's diagonal plane, stored exactly with integer sub-grid coefficients. Each sub-cell a part
touches is *full*, *empty* (not registered) or *partial* (cut by the plane: stores the plane and the
kept side), decided by testing the sub-cell's 8 corners. Two occupants may share a sub-cell only if
**neither is full and both are cut by the same plane on opposite sides**: exactly the two-colour
upper/lower triangle pairs that sets use for patterns. Any other partial combination counts as an
overlap (conservative; an exact convex-intersection test can replace this rule later without
changing the data). Picking tests the real wedge (ray vs convex solid), not the bounding box. ✅ Pointing at a
sloped face targets the empty part of that face's own cell: nothing attaches to a slope, but that's
where a complementary wedge goes (anything else is refused there by the occupancy rule).

**Reference:** `D:\Nanoblocks\LDrawData` (unofficial LDraw Nanoblock library, CCAL 2.0). Use it for
**shapes and the part list**, not dimensions: it assumes 10 LDU per pitch and 7.5 per layer
(nominal 4×4×3) and a Ø2.4 stud; our measured numbers win. Part files don't reference it (the
`ldraw` key was dropped); the matching LDraw file of each part is listed in `nanoblock_parts.md`.

### Sockets
```toml
[[socket]]
type = "stud"          # key into profile.socket_types
at = [0.5, 0.5, 1]     # cells
axis = "+z"            # which way the stud points
```
Ordinary bricks need no explicit sockets: `studs = "top"` / `antistuds = "bottom"` derive
them. Explicit sockets are for irregular layouts and joints.

✅ Implemented so far: `type = "stud"` with `at` (cells: x, y, and the height of the top the stud
sits on), e.g. the single centre stud of a 1×2 at `[0.5, 1.0, 1]`; and `type = "antistud"`
(the height of the bottom it's in), e.g. the extra centre antistud of the 2×2 round at
`[1.0, 1.0, 0]`. With `to`, an antistud is a **slot** (see below). ✅ `axis` (`+x` … `-z`,
default `+z`): which way the stud points; for an antistud, which way a stud sitting in it points
(so an underside slot is `+z`). A slot must lie across its axis. E.g. the side stud of the 1×1
"2凸": `at = [1.0, 0.5, 0.28]`, `axis = "+x"`. Joint socket types come later.

**Building on a side stud ✅.** Hovering the face a side stud sticks out of (one whose axis isn't
the part's own up) targets the stud's grid (`Model.side_stud_grid`): Z along the stud, Y along the
part's up, origin on the stud's base, so cell (0, 0)'s centre is on the stud and layer 0 lies
against the face. If an existing frame lines up with that grid (`Model.find_grid`: quarter turns
about Z, whole sub-cells), the part goes into it, so side studs in one plane share a frame and a
part can bridge them; otherwise placing creates the frame (one undo step). A part on a side stud
turns about the stud (Turn tool). Dragging the selection onto a side stud lands it on that grid too.

### Modifiers
A small, closed set that applies to both bodies and sockets:
```toml
array = { grid = { count = [2, 4], step = [1, 1] } }
array = { radial = { count = 8, axis = "z", center = [1, 1, 0] } }
mirror = "x"
```

### Sub-parts
`[[include]] part = "nanoblock:ball_head"` with an offset/rotation, so a shape is defined
once and reused (the LDraw idea, minus raw matrices).

### Parametric families — reserved, not implemented ✅
One file generating a size range (e.g. `brick(w, d)`). For now: the top-level key `params` is
reserved and the loader rejects files that use it. No expressions in values. Revisit only
once the hand-written library shows real duplication pain.

## Layer 3 — Placement, frames and rotation
- A placed part = `(frame, position on sub-grid as ints, quarter_turns, part id, color id)`.
  ✅ Implemented (save v3): frames with parent, origin (mm, in the parent's space) and rotation
  (unit quaternion `[w, x, y, z]`), listed parent-first. Each frame has its own grid and
  occupancy; overlap between frames isn't checked yet.
- A **frame** is a transform relative to a parent frame. The model's global grid is the root
  frame.
- A socket type's `dof` decides what a connection does:
  - `fixed` (stud): the child joins the parent's frame and only `grid_rotation` steps are
    allowed.
  - `spherical` (ball): the child gets its **own frame** anchored at the joint, and parts built
    on it share that frame. This covers the Skarmory wings.
- **Free Z rotation ✅:** rotating a part off-grid creates a new frame for it. Bricks built on it
  snap to that frame (as `feature_plan.md` describes). The angle itself is continuous; the
  **UI snaps** to an editor setting `rotation_snap` (default 7.5°, chosen because it divides
  90° evenly). This is an editor preference, **not** a profile value.
- ✅ **Subassemblies and contacts.** Parts on one frame form a rigid subassembly. Two
  subassemblies are **held** together if at least one contact links them: a stud in an antistud
  slot or point, or a ball in a cup. Sturdiness isn't modelled, only held or not. What a
  contact leaves free:

  | Contact | Fixes | Leaves free |
  |---|---|---|
  | Stud in a slot | the two Z axes parallel, the stud on the slot's line | turning about the stud, sliding along the slot |
  | Stud in a point antistud | as above, plus the position | turning about the stud |
  | Ball in cup | the ball centre on the cup's pivot | roll, swing within the cone or the slot plane |
  | Several contacts | everything any of them fixes | only what all of them leave free |

  E.g. two coaxial ball/cup pairs make a **hinge** (only rotation about their line). Two studs
  of subassembly A on the same local Z level, both in slots of subassembly B (one long slot, or
  two parallel ones like a 2×N's rows), fix B's angle: B turns about the first stud until the
  second lands on a slot. That's how a 1×N sits **at an angle across two studs**, and what the
  "align" tool works out (one slot: the direction between the studs; two slots: a circle meets
  a line).
- ✅ **A local snapping solver, no physics.** It only moves the frames being dragged, only to
  satisfy contacts (see "Snapping solver" below). Saves store each frame's transform; on load
  every contact is checked against it within tolerance.
- ✅ **Snapping** (editor settings, not profile values), by default on, with a key to move freely:
  - sliding along a slot: half-cell steps (the sub-grid);
  - turning about an axis (a stud, a hinge): `rotation_snap` steps (default 7.5°);
  - ball joints: three angles, each snapped like a rotation:
    - **swing θ**: how far the arm tilts away from straight (cone: θ ≤ 30° in any direction;
      slot: θ ≤ 90° only with φ along the slot, either way);
    - **swing direction φ**: which way it tilts, around the cup's axis (the plane it swings in);
    - **roll ψ**: about the ball part's own arm, applied before the swing so it doesn't change
      when φ does.

    At θ = 0, φ is meaningless; the editor keeps the last φ instead of jumping. Saves store the
    joint as a rotation, and the editor converts it to θ, φ, ψ for display and dragging, so files
    don't depend on this choice of angles;
  - later on top: "land on a grid", i.e. swing until a part on the moving side lines up with a
    nearby frame's grid (the Intermediate "same grid with minimal rotation" item).
- ✅ **Frames don't have to form a tree.** A part can bridge two frames. The Koraidon/Miraidon
  style of bracing (bricks reaching past a joint) makes a closed loop. So connections are
  stored as a **graph** (socket ↔ socket edges), and frame parent links are only one spanning
  tree of that graph. Loops are allowed in the data and checked for consistency (do the
  sockets still line up within tolerance?); the app does not solve for joint angles. v1 may
  only *create* tree-shaped frames, but nothing in the format should assume a tree.

## Moving the selection (decided ✅, built ✅)
- **What moves: exactly the selection.** Moving is an edit, not a physical motion (unlike
  turning, nothing that hangs off it comes along); groups and Select Connected make it easy to
  take a whole subassembly. Contacts it leaves behind are simply broken.
- **Keyboard nudge never changes frames.** Arrow keys move the selection half a cell or a whole
  cell (following H) along the axis of its own grid nearest the screen direction; PageUp / PageDown
  move it a layer. Its own grid = the frame most selected parts are in (a turned arm slides along its
  turned grid and stays turned).
- **Drag = pick up and put down**, like placing several parts at once: in the Select tool, dragging a
  selected part moves the selection (dragging from empty space still draws a box). The grabbed part's
  bottom-layer cell under the cursor is the anchor; the drop target is found as for placing (the face
  under the cursor, else the working grid's ground). The selection's grid snaps onto the target's
  grid, so it **can change frames**, taking the target's orientation with its quarter turn kept: a
  fine turn is dropped. Space turns it 90° while dragging; [ / ] give it a fine turn relative to the
  target (it then gets a grid of its own, as with turned placement); Shift+R clears that.
- What moves stays rigid inside: turned grids within the selection keep their relative angles.
  Groups don't change (they're separate from frames). Same validity as placing: red preview on a
  clash, no stud contact required. Emptied frames are removed. One undo step.
- As built: `History.move_parts(ids, transform, target_frame)`; a drag passes the target grid, a
  nudge doesn't. A moved part is checked with the full clash test against everything that stays,
  on its own grid too, so a sideways half-step that puts a stud outside a slot is refused. Parts that
  sit half-offset on their grid (e.g. a 1×4 on a 2×2 one-stud) need H to drop things onto them, as
  when placing.

## Groups, pins and moving subassemblies
Two separate trees ✅ (groups implemented, save v4):
- **Groups** (organising): named, nestable subassemblies made by the user (Group Ctrl+G,
  Ungroup Ctrl+Shift+G, rename in a Groups dock), e.g. Rayquaza > Body > I-segment > its rings.
  They decide what a click selects and what a name refers to (later: parts lists per group,
  instances). Connectivity alone can't: a chain of ball joints makes a whole body one connected
  component.
- **Frames** (movement): a frame's parent is what it hangs on, so a chain of joints is a chain of
  frames. A group may hold several frames (a segment's rings at 0° and 45°), and a chain crosses
  many groups, so the two trees are kept apart.

Selecting ✅: click selects the outermost group around the part, double-click drills one level in,
Alt+click always picks a single part. In the Select tool the outermost group under the cursor gets
a soft outline on hover; a Groups dock lists the tree with part counts (click to select, and it
follows viewport selections); the status bar names the selection's group.

Grouping ✅ (as built): Ctrl+G takes the selection's largest whole groups as child groups and its
loose parts directly; the new group goes inside the deepest group they all share. Ungroup dissolves
the selection's whole groups one level (contents move to the parent). Deleting parts removes groups
left empty, in the same undo step. Placing a part doesn't group it. Click and box select both pick
whole units at the current drill level; clicking outside the drilled-into group (or Esc) goes back
to the top level.

**Pins ✅**: every connected component has one pin, and components never affect each
other (separate subassemblies on the root grid are separate components). The pin is: an explicitly
pinned group in it; else whatever touches the ground (root grid, layer 0); else the side with more
parts. Turning at a joint cuts the component there: the pinned side stays, the other side (the
selection plus everything beyond it) moves; with two joints the pivot is the one toward the pin.
If pins end up on both sides (e.g. bracing loops), the move is refused with the reason. Turning a
selection that splits a frame gives the moved parts a new frame.

**The selection always moves ✅.** If the selection itself holds the pin (it's grounded or
pinned), that pin is ignored for this move: the selection plus whatever hangs only off it moves,
and the pin rule, applied to the rest without the selection, decides which side of the rest stays.
E.g. body B on the ground with a tail T on one stud: turning T turns T; turning B turns B about the
stud and T stays. A move is refused only when the selection is wedged between parts of the rest
that it would tear apart (a real lock, e.g. a brace on both sides).

## Step B: the Turn tool and turned frames (decided ✅, built ✅)
How the checks work as built, with tolerances: `docs/turning.md`.
Scope: turning about Z, and placing on turned frames. Ball joints and tilted frames reuse it later;
sliding along slots and general moving belong to "moving placed parts".
- **Turn tool (T).** Press on a part (or the selection); the moving set comes from the selection
  rule above. Its contacts with the rest give the free motion (a small version of the snapping
  solver: one moving body, angle + x + y, stud-in-slot errors, free motions from the null space;
  numpy). One stud or several on one axis: turn about it; otherwise locked, with the reason.
  Dragging around the pivot turns in `rotation_snap` steps; **Shift** turns freely (later also
  moves freely); **[ / ]** turn by one step; **Shift+R** realigns (a Z-turned set to the nearest
  90° of its parent grid, which merges it back; later a ball joint back to straight, keeping its
  roll). R is still Erase outside the Turn tool. The preview turns red on overlap; committing is
  one undo step.
- **Frames.** A turned set gets a frame that is its old grid turned about the pivot, so parts keep
  `pos` and `turns` and only the frame transform is new. A set that already owns its frame just
  changes that frame. Turning back to a multiple of 90° (when the parts land on the parent's
  sub-grid) merges them into the parent and deletes the empty frame. Frames hanging off the moving
  set are reparented with it.
- **Overlap across frames.** Exact test on the convex part solids after a bounding-box check;
  touching is allowed (the Seregios round ends touch at every angle). Also drives the "highlight
  colliding parts" view option.
- **Placing.** Against a turned part: that part's frame (already the case). The ghost can be turned
  by the snap step about the stud under its anchor; placing it creates the frame, valid only with a
  real stud contact. **Working frame:** make a hovered part's frame active, so empty space and the
  ground use its grid.
- Order: B1 overlap across frames, B2 frame bookkeeping (model + history), B3 free-motion finder,
  B4 Turn tool UI, B5 turned ghost and working frame.
- As built: the overlap test also covers **studs**. Bodies are solid in the test, so a stud may be
  inside another part's body only on one of that part's antistud slots; anywhere else it blocks
  (a part turned on a brick with several studs). The turned ghost turns about the centre of its
  anchor cell, so on a stud at a cell corner (2×2 one-stud) it needs half-cell snap, as unturned.
  The working grid is toggled with **F** over a part (F over empty space: back to the root grid);
  the grid drawn is the working one. Keys in the Place tool: **[ / ]** turn the preview, **Shift+R**
  puts it back.

**Worked example ✅: stud hinge (Seregios wing fold).** Two rigid halves built in layers meet in
a **fold column**. In each layer, one side's round 1×N end sits in that column, alternating
between the sides (e.g. bottom to top: A, B, A, A, B, A). The A–B contacts are all there, A studs
in B slots and B studs in A slots, on one vertical axis through the column's centre. Shared
freedom: turning about that axis (a hinge). Because slots from both sides take part, sliding locks
as soon as it bends. Clearance: within half a cell of the axis everything is a round end, and plain
ends start half a cell from it, so the parts touch but never overlap at any angle. Test for the
rotate tool: turning B finds the one axis, turns about it, and keeps every contact.

**Worked example ✅: two ball joints as a hinge, in a chain (Dragon wing).** Group G has two cups,
group H two balls. Each joint pins a ball centre to a cup centre; together they leave only turning
about the line through both centres (a hinge), if the two pairs are equally spaced (checked).
The range is the angles where **both** joints stay within their own limits: a hinge axis across the
cups' vertical slot planes swings the arms inside their slots (about ±90°); an axis along them
swings the arms sideways (the ±30° cone). The editor shows one snapped angle (θ/φ/ψ are only for a
single free joint). The wing is a chain, body → G → H, each link such a hinge: frames nest along
the chain (H's frame is a child of G's), while the groups (body, G, H) stay separate. With the body
pinned, turning H moves only H; turning G moves G and H, keeping the fold between them.

**Use cases from real sets ✅** (each becomes a test):
| Case | Contacts | Freedom left | Solver's job |
|---|---|---|---|
| Blue-Eyes White Dragon DX: 3 balls in a line | 3 fixed centres, collinear | hinge (1) | check equal spacing |
| …3 balls not in a line | 3 fixed centres | none: locked | the one pose where all meet |
| Koraidon: chain of 3 parts by ball joints, both ends on the body | closed loop of 4 ball joints | ~3, plus each middle link spinning about its two-joint axis | keep the loop closed while posing |
| Miraidon: a subassembly on its side, 2 studs into 2 slots | 2 stud contacts, different axes | none: locked if spacing fits | place it so both line up |
| Dragon: 2×2 round as a 45° adapter | studs in its centre hole and diagonal slots | none | find the 45° turn |
| Seregios wing fold, Dragon wing (above) | stud hinge; 2 ball joints | hinge (1) | one snapped angle within limits |

## Snapping solver (planned) ✅
Local and geometric, not physics: it moves only the frames being dragged.
1. Every contact is an error to minimise: a stud's distance from its slot line (point to segment)
   and how far its axis tilts from the slot's, a ball's distance from its cup centre.
2. Snapping = least squares on those errors over the moving frames' 6 numbers each, starting from
   where the user dragged (numpy; a few frames and contacts, so fast). Joint limits and snap angles
   apply on top.
3. Free motions come from the same setup: the directions in which the errors don't change (the
   constraint Jacobian's null space). Collinear balls give one (a hinge), non-collinear none
   (locked), one stud gives turning about it plus sliding along its slot. No special cases.
4. After solving: contacts within tolerance, limits respected, no overlap across frames; otherwise
   the move is refused with the reason. Dragging inside a closed loop (Koraidon) keeps it closed
   instead of being refused.

Later: **instances** (define a subassembly once, place it several times, edits update all, like the
manual's "×3" or LDraw multi-part files).

## Undersides: where studs fit ✅ (from the real parts)
An antistud is a **slot**: a stud fits anywhere along it (a point is a slot of length 0). Derived
from each body whose bottom isn't sitting on another body of the part, laid out by the profile's
`[[underside]]` rules; for Nanoblock (measured):
- **1×1**: a point at the cell centre.
- **1×N**: hollow, one slot along the middle line from the first cell's centre to the last. That's
  what lets a 1×N sit half-offset, or at an angle across two 1×1s.
- **2×N**: two slots, one per row, along the long side (the ribs between them block the middle);
  along Y when the sides are equal, like the other 2×N bricks.
- Wider footprints (base plates): none for now (real plates do grip studs in places).
- Lower wedges sit on their base, so a slope's underside is its base's. An upper (inverted) wedge
  is open below, but there's a wall between it and the box part: separate bodies, separate slots.
- Same footprint, same underside: flats, single-stud bricks, the 1×3 with 2 studs, round 1×N.
- L = a 1×2 slot + a 1×1 point, T = a 1×3 slot + a 1×1 point (their bodies are split that way).

A part can replace the derived ones with `antistuds = "none"` plus explicit `antistud` sockets
(`at`, and `to` for a slot): the 2×2 fan has three points at its cell centres; the 2×2 round has
a centre point plus four **diagonal** slots, from each cell centre out to the rim (the holes are
cut open at the rim, so e.g. a 1×3 lying diagonally across it fits).

## Ball joints (parts and placing built ✅; posing planned)
✅ Built: the four parts (`Joints/joint_{1x2,2x2}_{cup,ball}`), round bodies, ball / cup sockets,
joint contacts and placing straight onto a joint. Posing (turning a part about its joint) is next.

**Round bodies ✅.** `shape = "sphere"` or `"cylinder"`: `at` (cells, a point on the face it starts
from), `axis`, `offset_mm` (along the axis to where it starts; a sphere's centre), `length_mm`
(cylinder), `diameter_mm`, and `joint = true` for a joint's ball, arm or cup. Sized in mm, since a
sphere can't be sized in cells that aren't cubes. They aren't in the occupancy grid (the ball and cup
stick out past the brick's cells); the clash test covers them. A joined ball and cup may overlap
(the cup is modelled as a solid cylinder, inside ignored).

**Sockets ✅.** `type = "ball"` / `"cup"` with `at`, `axis` (a ball's from its part toward the ball;
a cup's out of the cup), `offset_mm` to the pivot, and for a cup `slot` (default `+z`, the part's
up). A ball is in a cup when its centre is on the cup's pivot (within the contact tolerance) and its
arm is within the cup's limits (profile: `cup = {…, cone = 30, slot = 90}`).

**Placing ✅.** With a joint part chosen, hovering a matching joint (a cup for its ball, or a ball
for its cup) puts it on straight: pivots together, arm into the cup, tops the same way
(`Model.joint_grid`). It gets a grid of its own (or a frame that lines up with it).

**Posing (planned, J5).** Turning a part held by a joint is locked for now. Plan: the turn finder
goes from turning in a plane to full 3D motion (a turn about any axis plus a shift); a ball joint
pins its centre, so one joint gives turning any way about it, two on a line a hinge, three off a
line nothing. One joint: drag points the arm at the cursor (on the plane facing the camera
through the ball), snapped as tilt θ and direction φ in 7.5° steps, limited to the cone or else
the slot; Ctrl+drag rolls; [ / ] roll a step; Shift+R straightens, keeping the roll.

Parts: nanoblock.info JO-C (cup / socket) and JO-D (ball), each on a 1×2 or a 2×2, with the cup or
ball on a side face. The Kawada manual calls them NAJO-C / NAJO-D.

**Range of movement ✅ (from the real parts and the manual).** Hold the cup fixed and look at the
ball side's arm direction `d`, relative to the cup's axis `a` (straight out of the cup) and its
slot direction `s` (perpendicular to `a`, the side the cup's U-shaped slot opens toward):
1. **Roll** about the arm itself: always free.
2. **Cone:** any `d` within about **30°** of `a`, in any direction (limited by the cup's rim).
3. **Slot:** `d` may also lie in the plane of `a` and `s`, tilted by up to about **90° either way**
   (the slot is two-sided ✅), with no sideways freedom there.

✅ The slot runs **vertically**: its plane contains the cup's axis and the cup part's local Z, so
`s` = ±local Z. The slot is fixed to the cup part, so mounting the cup part on its side turns the
90° range from up/down into left/right (the manual's "横向き" 30° vs "縦向き" 90° pictures).

Data: the limits belong to the socket type in the profile, e.g.
`cup = { mates = ["ball"], dof = "spherical", cone = 30, slot = 90 }`; each part's `[[socket]]`
gives the position, axis and slot direction. A connected ball gives its part its own grid frame
(see "Layer 3"); poses are valid inside the cone or in the slot, and the UI's rotation snap applies
to the joint angles too.

**Dimensions ✅ (measured with calipers):**
- Straightened, the two parts' faces are exactly 2 cells (8 mm) apart. The pivot (ball centre) is
  **4.25 mm from the cup part's face** and **3.75 mm from the ball part's face** (1.0625 and
  0.9375 cells): not on the half-cell grid, which is fine since a jointed part gets its own frame.
- Ball and cup sit at **mid-height** of the brick: a joint pair with one side rolled 180° lines up
  with the other side's top and bottom swapped. Use half a layer (half body height differs by
  0.04 mm).
- Ball diameter **4.00–4.05 mm**. The arm from the brick to the ball is a tapered cylinder; model it
  as a plain cylinder of its narrowest diameter, **1.95 mm** (at the ball end).
- The LDraw files (NB201B/S, NB202B/S) disagree: ball centre 3.6 mm and cup centre 3.24 mm from
  the faces (6.84 mm total instead of 8), ball Ø ≈ 3.4 mm, arm Ø 1.6 mm. Treat them as rough shapes
  only; the measurements win.

## Library
- A folder tree of part files; the folders are the categories. Ids are namespaced
  (`nanoblock:brick_2x4`).
- Thumbnails are rendered and cached outside the library.
- Favorites live in user settings, not in the library.

## Runtime model ✅
```python
PartDef      # from a part TOML: id, name, category, bodies, cells, studs, antistud slots
Frame        # id, parent, origin (mm, parent space), rotation (quaternion); 0 = the root grid
Group        # id, name, parent: user-made subassemblies, separate from frames
PlacedPart   # id (stable int), part, frame, pos (SUB-GRID ints), turns (0..3), color (palette id),
             # group, plus derived world geometry (solids, outline edges, studs, slots, box)
Model        # parts, frames, groups; occupancy: dict[(frame, sub-cell), [(part id, cut)]]
             # add_part(...) -> PlacedPart | None (refused on same-grid overlap), remove_part,
             # can_place, connections(), collisions(), frame/group edits, save/load
History      # every UI edit as undoable commands, incl. move_parts (turning, moving)
```
- Connections aren't stored: they're re-derived from world positions (they work across Z-turned
  frames). Stored edges may arrive with joints.
- Placing: the cell under the cursor is where the part's **anchor cell** goes. The anchor is
  one of the part's bottom-layer cells, cycled with A / Shift+A (e.g. end / middle / end of a
  1×3); it starts at the cell nearest the centre (ties: +X, then +Y, in part coordinates).
  Rotation keeps the anchor cell under the cursor. This is purely an editor aid: data still
  stores the origin, and rotation pivots on the origin. Overlap is refused and the ghost turns red.
- ✅ **Side-face placement is allowed**, even though such a part isn't held by anything
  (View > Highlight Unconnected Parts shows them).
- ✅ **No hard floor at layer 0.** A global floor makes no sense for parts in other frames, and
  building down from the top is legitimate. The Z=0 grid is only a reference plane for ground
  placement. Repositioning a whole build: select all and move it.

## Save format (v4) ✅
```json
{
  "version": 4,
  "profile": "nanoblock",
  "frames": [{ "id": 0 },
             { "id": 1, "parent": 0, "origin": [-1.84, 1.23, 0.0], "rotation": [0.981, 0.0, 0.0, 0.195] }],
  "groups": [{ "id": 1, "name": "Wing", "parent": null }],
  "parts": [
    { "id": 1, "part": "nanoblock:brick_2x4", "frame": 0,
      "pos": [0, 0.5, 3], "turns": 1, "color": "red", "group": 1 }
  ]
}
```
- `pos` is in **cells** (0.5 allowed). On load it's multiplied by `subdiv` and must come out as
  integers, so saves don't depend on `subdiv`.
- Frames and groups are listed parent-first. A frame's `origin` is in mm in its parent's space,
  `rotation` a unit quaternion `[w, x, y, z]`. A part's `group` (its innermost group) is omitted
  when it's ungrouped.
- ✅ `color` is a **palette id** from the profile; `part` a part id. Neither is translated if
  renamed: a save using an old id fails to load.
- History: v2 had only frame 0; v3 added frames; v4 added groups. v2 and v3 files still load.
  The v1 loader maps each v1 cube to `brick_1x1` in frame 0, with RGB matched to the palette
  (exact for files saved from the old palette, otherwise nearest). Saving always writes the latest
  version.

## Build order (as it happened)
1. ✅ Profile file + a single cell-to-world function used by the renderer, picking and camera.
2. ✅ Parts limited to `box` with derived studs; occupancy map; placed-part model; save v2.
3. ✅ Library panel (Parts tree by category).
4. ✅ Slopes, rounded bodies, explicit sockets, connections; frames (step A); groups; the Turn tool
   and turned placement (step B); moving the selection. Next: joints, modifiers, mesh bodies.

## Measurements (Nanoblock, mm)
Taken with calipers. ✅ = consistent, ❓ = needs a recheck.

| what | value | note |
|---|---|---|
| stud pitch | 4.00 ✅ | |
| 1×1 body width | 4.000 | measured across a row of 20, which really measures pitch; real gap not resolvable |
| stacking pitch | 3.125 ✅ | 10-brick stack, top stud excluded |
| single body height | 3.05 ✅ | ~0.075 seating gap per layer (first derived as 5.05 total incl. stud − a 2.00 stud; the stud re-measured smaller, see below) |
| stud | Ø2.45 × 1.60, solid ✅ | re-measured (first measured Ø2.65 × 2.00); side studs are the same |
| side stud (1×1 "2凸") | centred on the face, centre 0.875 above the bottom; base flush with the face ✅ | |
| wall, 1×N / 2×N | 0.85 / 0.95 | |
| 1×1 inner opening | 2.2 ❓ | consistent with walls (0.85+2.2+0.85 = 3.9 ≈ pitch − gap). Magnifier photos: a **round counterbore at the mouth**, then a deeper **square cavity whose corners are clipped by the circle**. Best guess: the stud grips in the round bore and 2.2 is the deeper square. To confirm: round bore diameter + depth (caliper depth rod). Parked: rendering only |
| 1×N underside | hollow | |
| 2×N underside | double ribs along long axis; 2×2 photo shows a centre bar with two round holes | wall→rib gap 2.15 ❓ (< stud Ø, measure at the bottom edge); ribs+gap 1.70; ribs recessed 0.75 from bottom edge |

Underside numbers affect rendering only; collision and placement use whole cells.
Decision: render the antistud as a plain round hole of stud diameter; don't model the exact
cavity unless a close-up view ever needs it.

