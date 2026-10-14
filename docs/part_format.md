# Profiles, part definitions and the part library — design

Status: **draft / not implemented.** Decisions agreed so far are marked ✅; open points ❓.

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
| `slope`    | wedge; direction + rise/run               | derived (whole cells)|
| `cylinder` | round parts                               | derived (bounding cells) |
| `mesh`     | escape hatch: `file = "ball.obj"`         | **must be declared** |

Occupancy is whole cells for now (a slope occupies its full cells). Finer occupancy can come
later if collisions between slopes matter.

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

## Save format v2 (sketch)
```toml
# JSON in practice, kept consistent with v1
{ "version": 2, "profile": "nanoblock",
  "frames": [{ "id": 0 }, { "id": 1, "parent": 0, "origin": [..], "rotation": [w, x, y, z] }],
  "parts":  [{ "part": "nanoblock:brick_2x4", "frame": 0, "pos": [x, y, z],
               "turns": 0, "color": "red" }] }
```
The v1 loader maps each v1 cube to a 1×1 brick in frame 0, with its RGB matched to the
nearest palette color or added as a custom color.

## Build order
1. Profile file + a single cell-to-world function used by the renderer, picking and camera →
   4×4×3 rendering.
2. Parts limited to `box` with derived studs; occupancy map; placed-part model; save v2.
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
| 1×1 inner opening | 2.2 ❓ | consistent with walls (0.85+2.2+0.85 = 3.9 ≈ pitch − gap), but smaller than stud Ø2.65. Probably not a plain square (grip ribs/bumps?). Resolve with a close-up photo when underside rendering is built |
| 1×N underside | hollow | |
| 2×N underside | double ribs along long axis | wall→rib gap 2.15 ❓ (< stud Ø, measure at the bottom edge); ribs+gap 1.70; ribs recessed 0.75 from bottom edge |

Underside numbers affect rendering only; collision and placement use whole cells.

