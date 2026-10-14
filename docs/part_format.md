# Profiles, part definitions and the part library — design

Status: **draft; implemented so far: profile + palette (step 1), box parts, placed-part model,
save v2 (step 2a), part picker, rotation, studs, overlap preview (step 2b).** Part files carry `name`, optional `ldraw`, and `[[body]]` (`shape = "box"`,
`size`, optional `at`, `studs = "top" | "none"`); id and category come from the file path. Decisions agreed so far are marked ✅; open points ❓.

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

`studs` takes `"top"` or `"none"` (flat parts such as NB102F) in step 2. Explicit stud sockets
cover irregular layouts later (single-stud parts such as NB102S/NB202S1).

**Slope profile ✅:** seen from the side, a slope is a box (base) plus a right triangle sitting on
it, extruded along the other horizontal axis. Studs aren't part of the outline. Parameters: base
size, the triangle's run (cells) and rise (layers; can be fractional, e.g. NB10202A peaks at 2
layers + stud height), and which way the vertical face points. A sketch, not final:
```toml
[[body]]
shape = "slope"
size = [1, 2, 1]        # base box
rise = 1.0              # layers above the base
run = [0, 1]            # the part of the base the triangle sits on (cell range along the slope axis)
high_side = "+y"        # direction of the triangle's vertical face
```

Occupancy is tracked per **sub-cell** of the profile's `subdiv` grid (so half-offset parts work),
but each part's shape fills whole cells. A slope fills every cell its outline touches. Finer
occupancy can come later if collisions between slopes matter.

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
- ✅ Fine rotation **requires a physical connection that permits it**: every engaged socket
  must lie on one shared axis (in practice, a part held by a single stud). The pivot is
  that axis, not the part origin.
- ✅ **Frames don't have to form a tree.** A part can bridge two frames. The Koraidon/Miraidon
  style of bracing (bricks reaching past a joint) makes a closed loop. So connections are
  stored as a **graph** (socket ↔ socket edges), and frame parent links are only one spanning
  tree of that graph. Loops are allowed in the data and checked for consistency (do the
  sockets still line up within tolerance?); the app does not solve for joint angles. v1 may
  only *create* tree-shaped frames, but nothing in the format should assume a tree.

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
- Placing: the cell under the cursor is the part's **origin cell**, so rotating (which pivots
  on the origin) keeps the ghost under the cursor. Overlap is refused and the ghost turns red.
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
   Starter set ✅: 1×1, 1×2, 1×3, 1×4, 1×6, 2×2, 2×3, 2×4, 2×6, 2×8.
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

