# Part format reference: profiles, part files, library, saves

What the data files look like today. Why it's this way: `design.md`. The measured numbers behind
the Nanoblock files: `measurements.md`. How the code uses it: `architecture.md`.

## Goals
- Nanoblock is the only system we author parts for, but nothing system-specific lives in code
  (see "Scope" in `CLAUDE.md`): a **profile** holds what differs between systems.
- Part files are **hand-written and readable**. Meaning (occupancy, connections) comes first;
  render geometry is derived from it.
- Fix what LDraw lacks for this use: no occupancy, no connection semantics (LDCad bolts them on via
  a separate "shadow library" of `SNAP_*` metas), raw 12-number matrices, triangle-level authoring,
  Lego-specific units. Keep from LDraw: reusable sub-parts (planned) and a category-folder library.
- Files are **TOML**, read with the stdlib `tomllib`; they're hand-authored, so there's no writer.

## Profile (one per brick system)
`src/brickbuilder/profiles/<id>.toml`. Parts and saves refer to a profile by `id`.

```toml
id = "nanoblock"
name = "Nanoblock"
cell = [4.0, 4.0, 3.125]      # mm: stud pitch X/Y, stacking pitch Z (studs excluded)
subdiv = [2, 2, 1]            # placement sub-grid per cell: half-cells in XY, whole cells in Z
grid_rotation = 90.0          # rotations that keep a part on its frame's grid (not used yet)
clearance = 0.05              # cosmetic seam between bodies (not used yet)
body_height = 3.05            # rendering only: stacking pitch minus seating gap (not used yet)

[stud]
diameter = 2.45
height = 1.60
hollow_diameter = 0.0         # solid

[[underside]]                 # where studs fit under a body (first match by its short side)
max_short_side = 2            # 1xN and 2xN: one slot per row, along the long side
slots = "rows"
[[underside]]
slots = "perimeter"           # wider (the base plates): slots on the sides, a hollow middle

[socket_types]
stud     = { mates = ["antistud"], dof = "fixed" }
antistud = { mates = ["stud"],     dof = "fixed" }
ball     = { mates = ["cup"],      dof = "spherical" }
cup      = { mates = ["ball"],     dof = "spherical", cone = 30, slot = 90 }  # degrees

[palette]
white = { name = "White", rgb = "#F4F4F2" }
clear = { name = "Clear", rgb = "#FFFFFF", clear = true, alpha = 0.5 }   # alpha: 0.75 by default for clear
```

- `subdiv` is how other systems stay data-only (Lego plates would be `[1, 1, 3]`). Positions are
  integers on this sub-grid, so there's no float drift. X and Y must be equal (parts turn in 90°
  steps, which swaps them).
- `[[underside]]` rules: tried in order; the first whose `max_short_side` the body's footprint fits
  (omitted = any) names a pattern. Patterns are code (`profile.UNDERSIDE_PATTERNS`): `rows` (one
  slot per row of cells along the long side, Y on a tie; a 1×N gets its middle line, a 1×1 a point),
  `perimeter` (four slots along the sides through the corner cells' centres, and a **hollow** one cell
  inside them: studs fit anywhere there without gripping) and `none`. A system with another underside (Lego's tubes) adds a pattern when it's needed. No
  rules: no derived antistuds.
- `cup` carries the joint limits: `cone` (any direction) and `slot` (in the slot's plane, either way).
- Palette ids are stable keys in save files, ASCII `[a-z0-9_]`; `name` is for display. RGB values
  are approximate; clear colours render opaque for now.

## Part files
`src/brickbuilder/parts/<profile>/<Category folders>/<name>.toml`. The id is `<profile>:<file stem>`
(ASCII `[a-z0-9_]`), the category is the folder path. Top-level keys: `name`, `[[body]]` (at least
one box or wedge), `[[socket]]`, `antistuds` (`"derived"` default, or `"none"`). `params` is reserved
(parametric families, see "Planned"); the loader rejects it and any unknown key.

Positions are in **cells** of the profile (x, y in cells, z in layers): readable, and a corrected
measurement in the profile needs no part edits. The origin is the minimum corner of the part's cells,
at the bottom; 90° turns pivot on it. Round bodies and joint offsets are sized in **mm** (a sphere
can't be sized in cells that aren't cubes).

### Box bodies
```toml
[[body]]
shape = "box"
size = [2, 4, 1]       # cells
at = [0, 0, 0]         # min corner, optional
studs = "top"          # or "none" (flat parts, e.g. NB102F)
corner_radius = 0.5    # optional: round the vertical edges (cells)
```
- Derived studs sit at the centre of every top cell not covered by another body of the part.
- `corner_radius`: one number for all four vertical edges (at most half the shorter side; `0.5` on a
  1×N gives semicircular ends) or a table per corner, e.g. `{ "+x+y" = 2 }` for the 2×2 fan's quarter
  circle (two corners on one side can't round more than its length). A derived stud is dropped when
  its cell's centre is cut away. A rounded box must be the part's only body.

### Wedge bodies (slopes)
A slope is a box base plus a **wedge**: a box cut along its diagonal, keeping the lower or upper half.
Seen from the side the triangle is half of an m (cells) × n (layers) rectangle, so its corners are on
the sub-grid.
```toml
# NB102A, 1x2 slope: 1x2x1 base; on one cell a lower triangle 1 cell x 1 layer
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
- NB10202A / NB10202V (1×2×2) are the same with wedge size `[1, 1, 2]`.
- A lower wedge's sloped top has no studs (and can't be given any); an upper wedge's flat top does.
- Complementary wedges (same rectangle, both `keep` and `tall` flipped) share cells: see Occupancy.
- An inverted slope's underside is open (walls only on the sides), so studs fit under its slope.

### Round bodies (joints)
```toml
[[body]]
shape = "cylinder"     # or "sphere"
at = [1.0, 1.0, 0.5]   # cells: a point on the face it starts from
axis = "+x"            # which way it points from there
offset_mm = 0          # along the axis to where it starts (a sphere: its centre)
length_mm = 2.75       # cylinder only
diameter_mm = 2.9
end_diameter_mm = 5.2  # optional: a tapered cylinder (the cup's neck)
joint = true           # part of a joint's ball, arm or cup
```
Round bodies aren't in the occupancy grid (they stick out past the brick's cells); the clash test
covers them. A joined ball and cup may overlap each other (the cup is modelled solid).

### Sockets
```toml
[[socket]]
type = "stud"          # stud | antistud | ball | cup
at = [0.5, 1.0, 1]     # cells: x, y, height of the face it's on
axis = "+z"            # +x ... -z, default +z
```
- **stud**: anywhere, e.g. the single centre stud of a 1×2 at `[0.5, 1.0, 1]`, or the 1×1 side stud
  at `[1.0, 0.5, 0.28]` with `axis = "+x"`. `axis` is the way the stud points.
- **antistud**: a point, or with `to` a **slot** (a segment a stud fits anywhere along), e.g. the 2×2
  round's centre point `[1.0, 1.0, 0]`. `axis` is the way a stud sitting in it points (`+z` for an
  underside). A slot must lie across its axis.
- **ball** / **cup**: `offset_mm` along `axis` from `at` to the pivot (a ball's centre / a cup's
  pivot). A ball's axis points from its part toward the ball, a cup's out of the cup. A cup's `slot`
  (default `+z`, the part's up) is the direction its slot opens toward.

### Undersides (derived antistuds)
Unless `antistuds = "none"`, every box or upper-wedge body whose bottom isn't sitting on another body
of the part gets slots by the profile's `[[underside]]` rules (a lower wedge sits on its base). For
Nanoblock (from the real parts):
- **1×1**: a point at the cell centre. **1×N**: one slot along the middle line, first cell centre to
  last (it's hollow: a 1×N sits half-offset, or at an angle across two 1×1s). **2×N**: one slot per
  row along the long side (ribs block the middle); along Y when the sides are equal.
- Wider (base plates): four slots on the sides, through the corner cells' centres, and a hollow one
  cell in from them where studs fit without gripping. A 10×10: four 9-cell slots and a 7×7 hollow;
  studs between a side slot and the hollow are blocked (the ribs).
- Same footprint, same underside: flats, single-stud bricks, the 1×3 with 2 studs, round 1×N.
  L = a 1×2 slot + a 1×1 point, T = a 1×3 slot + a 1×1 point (their bodies are split that way).
- Explicit instead: the 2×2 fan has three points at its cell centres; the 2×2 round a centre point
  plus four **diagonal** slots from each cell centre out to the rim (a 1×3 lying diagonally fits).

### Occupancy
Per **sub-cell** of the profile's `subdiv` grid. A box fills whole sub-cells. A wedge's sub-cells are
*full*, *empty* or *partial* (cut by the diagonal plane, stored exactly with integer sub-grid
coefficients and the kept side), from the sub-cell's 8 corners. Two parts may share a sub-cell only if
**neither is full and both are cut by the same plane on opposite sides** (two-colour slope pairs). A
sub-cell entirely outside a rounded corner is free; one the curve crosses counts as full. Studs and
round bodies are handled by the clash test, not occupancy. A stud may be inside another part's body
only through one of its slots or hollows, its base on or below their plane.

### Naming
- Slopes: `slope_{footprint}_wedge_{run}x{rise}[_inverted]`, shown as "Slope 1×2 wedge 1×1
  [inverted]" (run = cells along the slope, rise = layers).
- Part and palette ids are never translated: a save using a renamed id fails to load ("unknown part").

### Planned (not implemented)
- **Modifiers** for bodies and sockets: `array = { grid = { count = [2, 4], step = [1, 1] } }`,
  `array = { radial = { count = 8, axis = "z", center = [1, 1, 0] } }`, `mirror = "x"`.
- **Sub-parts**: `[[include]] part = "nanoblock:ball_head"` with an offset/rotation.
- **Mesh bodies**: `shape = "mesh"`, `file = "x.obj"`, occupancy declared by hand.
- **Parametric families** (`brick(w, d)` from one file): `params` stays reserved, no expressions in
  values; revisit only once the hand-written library shows real duplication pain.

## Library
- A folder tree of part files; the folders are the categories (the Parts tree mirrors them).
- Thumbnails (planned) are rendered and cached outside the library; favorites live in user settings.

## Save format (v4)
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
- `pos` is the part origin in **cells** (0.5 allowed), on its frame's grid. On load it's multiplied
  by `subdiv` and must come out as integers, so saves don't depend on `subdiv`. `turns`: quarter turns
  CCW about the origin.
- Frames and groups are listed parent-first. A frame's `origin` is mm in its parent's space,
  `rotation` a unit quaternion `[w, x, y, z]` (ball joint poses are stored this way too). A part's
  `group` (its innermost group) is omitted when ungrouped.
- `color` is a palette id, `part` a part id.
- History: v2 had only frame 0; v3 added frames; v4 added groups. v2 and v3 still load; v1 (`bricks`
  with float RGB) loads as 1×1 bricks with the nearest palette colour. Saving writes the latest
  version. Bump `version` and keep the old loader paths when the schema changes.

## LDraw reference
`D:\Nanoblocks\LDrawData` (unofficial LDraw Nanoblock library, CCAL 2.0): use it for **shapes and the
part list**, not dimensions (it assumes 10 LDU per pitch and 7.5 per layer, nominal 4×4×3, and a Ø2.4
stud; our measured numbers win). Part files don't reference it; each part's LDraw file is listed in
`nanoblock_parts.md`.
