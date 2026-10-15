# Profiles, part definitions and the part library — design

Status: **draft; implemented so far: profile + palette, box and wedge (slope) bodies, placed-part
model with exact slope occupancy, save v2, part picker, rotation, studs, anchors, half-offset
placement.** Part files carry `name`, optional `ldraw`, and `[[body]]` (`shape = "box"` with
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
diameter = 2.65
height = 2.00
hollow_diameter = 0.0         # solid

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

`studs` takes `"top"` or `"none"` (flat parts such as NB102F) in step 2. Explicit stud sockets
cover irregular layouts later (single-stud parts such as NB102S/NB202S1).

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
(nominal 4×4×3) and a Ø2.4 stud; our measured numbers win. Part files may cross-reference it,
e.g. `ldraw = "NB102A.dat"`.

### Sockets
```toml
[[socket]]
type = "stud"          # key into profile.socket_types
at = [0.5, 0.5, 1]     # cells
normal = "+z"
```
Ordinary bricks need no explicit sockets: `studs = "top"` / `antistuds = "bottom"` derive
them. Explicit sockets are for irregular layouts and joints.

✅ Implemented so far: `type = "stud"` with `at` (cells: x, y, and the height of the top the stud
sits on), e.g. the single centre stud of a 1×2 at `[0.5, 1.0, 1]`; and `type = "antistud"`
(the height of the bottom it's in), e.g. the extra centre antistud of the 2×2 round at
`[1.0, 1.0, 0]`. With `to`, an antistud is a **slot** (see below). `normal` and the joint socket types come later.

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
- ✅ **No physics solver.** A pose is either picked by the user within what the contacts leave
  free, or worked out by the tool (align, land on a grid). Saves store each frame's transform;
  on load every contact is checked against it within tolerance.
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

## Undersides: where studs fit ✅ (from the real parts)
An antistud is a **slot**: a stud fits anywhere along it (a point is a slot of length 0). Derived
from each body whose bottom isn't sitting on another body of the part:
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

## Ball joints (planned)
Parts: nanoblock.info JO-C (cup / socket) and JO-D (ball), each on a 1×2 or a 2×2, with the cup or
ball on a side face. The Kawada manual calls them NAJO-C / NAJO-D.

**Range of movement ✅ (from the real parts and the manual).** Hold the cup fixed and look at the
ball side's arm direction `d`, relative to the cup's axis `a` (straight out of the cup) and its
slot direction `s` (perpendicular to `a`, the side the cup's U-shaped slot opens toward):
1. **Roll** about the arm itself: always free.
2. **Cone:** any `d` within about **30°** of `a`, in any direction (limited by the cup's rim).
3. **Slot:** `d` may also lie in the plane of `a` and `s`, tilted by up to about **90° either way**
   (the slot is two-sided ✅), with no sideways freedom there.

The slot is fixed to the cup part, so mounting the cup part on its side turns the 90° range from
up/down into left/right (the manual's "横向き" 30° vs "縦向き" 90° pictures).

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

## Runtime model (step 2) ✅
```python
PartDef      # from a part TOML: id, name, category, occupied cells, derived stud positions
PlacedPart   # id (stable int), part, frame (0 = root), pos (SUB-GRID ints), turns (0..3), color (palette id)
Model        # parts: dict[id, PlacedPart]; occupancy: dict[sub-cell, part id]
             # add_part(...) -> id | None (refused on overlap), remove_part, part_at, can_place
```
- Connections aren't stored while everything is on one frame: they can be re-derived from
  geometry. Stored edges arrive with joints.
- Placing: the cell under the cursor is where the part's **anchor cell** goes. The anchor is
  one of the part's bottom-layer cells, cycled with A / Shift+A (e.g. end / middle / end of a
  1×3); it starts at the cell nearest the centre (ties: +X, then +Y, in part coordinates). Rotation keeps the anchor cell under the cursor. This is
  purely an editor aid: data still stores the origin, and rotation pivots on the origin.
  Overlap is refused and the ghost turns red.
- ✅ **Side-face placement is allowed**, even though such a part isn't held by anything.
  Checking for unconnected parts comes later.
- ✅ **No hard floor at layer 0.** A global floor makes no sense for parts in other frames, and
  building down from the top is legitimate. The Z=0 grid is only a reference plane for ground
  placement. Repositioning a whole build is a "shift all parts" operation instead.

## Save format v2 ✅
```json
{
  "version": 2,
  "profile": "nanoblock",
  "frames": [{ "id": 0 }],
  "parts": [
    { "id": 1, "part": "nanoblock:brick_2x4", "frame": 0,
      "pos": [0, 0.5, 3], "turns": 1, "color": "red" }
  ]
}
```
- `pos` is in **cells** (0.5 allowed). On load it's multiplied by `subdiv` and must come out as
  integers, so saves don't depend on `subdiv`.
- Non-root frames will look like
  `{ "id": 1, "parent": 0, "origin": [..], "rotation": [w, x, y, z] }`; step 2 only writes frame 0.
- ✅ `color` is a **palette id**; the palette moves into the profile. The current placeholder
  colors become the initial palette, so renaming them to official Nanoblock colors later needs
  an id-mapping for older saves.
- The v1 loader maps each v1 cube to `brick_1x1` in frame 0, with RGB matched to the palette
  (exact for files saved from the current palette, otherwise nearest). Saving always writes v2.

## Build order
1. Profile file + a single cell-to-world function used by the renderer, picking and camera →
   4×4×3 rendering.
2. Parts limited to `box` with derived studs; occupancy map; placed-part model; save v2.
   Starter set ✅: 1×1, 1×2, 1×3, 1×4, 1×6, 2×2, 2×3, 2×4, 2×8 (no plain 2×6 exists).
3. Library panel.
4. Modifiers, slopes, mesh bodies, explicit sockets → frames, fine rotation, ball joints.

## Measurements (Nanoblock, mm)
Taken with calipers. ✅ = consistent, ❓ = needs a recheck.

| what | value | note |
|---|---|---|
| stud pitch | 4.00 ✅ | |
| 1×1 body width | 4.000 | measured across a row of 20, which really measures pitch; real gap not resolvable |
| stacking pitch | 3.125 ✅ | 10-brick stack, top stud excluded |
| single body height | 3.05 ✅ | 5.05 total incl. stud − 2.00 stud; ~0.075 seating gap per layer |
| stud | Ø2.65 × 2.00, solid ✅ | |
| wall, 1×N / 2×N | 0.85 / 0.95 | |
| 1×1 inner opening | 2.2 ❓ | consistent with walls (0.85+2.2+0.85 = 3.9 ≈ pitch − gap). Magnifier photos: a **round counterbore at the mouth**, then a deeper **square cavity whose corners are clipped by the circle**. Best guess: the stud grips in the round bore and 2.2 is the deeper square. To confirm: round bore diameter + depth (caliper depth rod). Parked: rendering only |
| 1×N underside | hollow | |
| 2×N underside | double ribs along long axis; 2×2 photo shows a centre bar with two round holes | wall→rib gap 2.15 ❓ (< stud Ø, measure at the bottom edge); ribs+gap 1.70; ribs recessed 0.75 from bottom edge |

Underside numbers affect rendering only; collision and placement use whole cells.
Decision: render the antistud as a plain round hole of stud diameter; don't model the exact
cavity unless a close-up view ever needs it.

