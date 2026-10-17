# BrickBuilder

A desktop app for designing models in **Nanoblock** micro bricks, built with PySide6 and OpenGL.

Brick CAD tools ship Lego part libraries and grids, and voxel editors handle slopes, half-offset
layers and ball joints poorly. BrickBuilder works on Nanoblock's own grid (4 × 4 mm cells,
3.125 mm per layer, measured) with Nanoblock parts and colours. Grid sizes, parts and colours are
data, not code, so other micro-brick systems could be added without changing the program.

## Features
- **3D view** with orbit, pan and zoom, orthographic, Z up, and a grid on the ground plane.
- **Parts** in groups:
  - **Bricks:** 1×1, 1×1 with a side stud, 1×2, 1×3, 1×4, 1×6, 2×2, 2×3, 2×4, 2×8, flat (studless) 1×2 and 2×4,
    2×2 L, 2×3 T, and the 1×2 and 2×2 with a single centre stud and the 1×3 with 2 studs.
  - **Slopes:** 1×2 (with a 1- or 2-layer wedge), 1×3, 2×2, 2×3 and 2×4, plus inverted versions of
    the two 1×2 slopes. A slope and its inverted partner can share a cell, as in two-colour
    patterns from real sets.
  - **Round:** 1×1 and 2×2 cylinders, 1×2, 1×3 and 1×4 with rounded ends, and the 2×2 quarter-circle fan.
  - **Plates:** 10×10 and 20×20 base plates.
- **Placement preview** that turns red when a part would overlap something. It shows its underside
  slots as blue lines (crosses for single points), so you can see which way a 2×2's rows run, and
  rings any stud in the way in red.
- **Turning placed parts** to any angle about the stud they're held by (Turn tool), with
  their own grid for what's built on them.
- **Rotation** in 90° steps, a choice of which cell of the part sits under the cursor, and
  **half-offset placement**.
- **The 45 official Nanoblock colours.** Colour names come from nanoblock.info; the RGB values
  are approximate.
- **Connection check:** View > Highlight Unconnected Parts (U) marks parts that aren't held
  by the main build. Undersides follow the real parts: a 1×N's hollow slot takes studs anywhere
  along it, a 2×N has one slot per row, and so on.
- **Groups:** named, nestable subassemblies that clicks select as a whole.
- **Collision check:** View > Highlight Colliding Parts (O) marks parts on different grids (turned
  parts) that overlap.
- **Undo/redo**, Save / Save As, and a prompt before closing with unsaved changes.

See [`feature_plan.md`](feature_plan.md) for what's planned next.

## Getting started
Requires Python 3.13+ and [`uv`](https://github.com/astral-sh/uv).

```bash
uv sync
```

```bash
uv run run_app.py
```

Run the tests with:

```bash
uv run pytest
```

## Controls

### Camera
- **Orbit:** middle mouse drag
- **Pan:** Shift + middle mouse drag
- **Zoom:** scroll wheel

### Tools
- **Place (Q):** click to place the part chosen in the Parts list. Ctrl + click removes a part.
  - **Space / Shift+Space:** rotate the part 90°.
  - **A / Shift+A:** choose which of its cells sits under the cursor (starts nearest the centre).
  - **H:** toggle half-cell snapping. **Arrow keys:** nudge the preview half a cell.
  - **[ / ]:** turn the preview off the grid in 7.5° steps (it gets a grid of its own and has to sit
    on a stud); **Shift+R** puts it back.
  - **F:** use the grid of the part under the cursor for empty space and the ground too; F over
    empty space goes back to the main grid.
  - **Side studs:** hover the face a side stud sticks out of to build on the stud (side studs in
    one plane share a grid, so a part can bridge them).
- **Select (W):** click a part, or its whole outermost group (outlined in blue on hover);
  double-click drills into a group; Alt+click picks a single part. Ctrl+click adds or removes;
  drag a box to select several. **Drag a selected part** to move the selection onto any face or
  grid (Space turns it, [ / ] fine turn, Esc cancels); **arrow keys** move it half a cell (H) or a
  cell along its own grid, **PgUp / PgDown** a layer. **Delete** removes the selection and picking a colour recolours
  it (one undo step each). **Ctrl+A** selects all, **Esc** clears. Edit > Select Connected grows
  the selection to whole connected subassemblies.
  - **Ctrl+G / Ctrl+Shift+G:** group / ungroup the selection. Groups nest; the Groups dock lists
    them with part counts (click to select, double-click to rename).
- **Turn (T):** drag a part (or the selection) to turn it about the stud it's held by, in 7.5°
  steps; **Shift** turns freely; **Ctrl+drag** slides it along the slot it's held in. **[ / ]** turn the selection a step, **Shift+R** turns it back onto
  its grid. Parts built on a turned part follow its grid. If the contacts lock it (studs on different
  axes, two studs in one slot), the status bar says why; a red preview means it would overlap.
- **Paint (E):** click to recolour a part with the current colour.
- **Erase (R):** click to remove a part.

### View
- **U:** highlight parts that aren't connected to the main build (orange).
- **O:** highlight parts that overlap parts on another grid (red).

### Edit and file
- **Undo:** Ctrl+Z. **Redo:** Ctrl+Y or Ctrl+Shift+Z.
- **New:** Ctrl+N. **Open:** Ctrl+O. **Save:** Ctrl+S. **Save As:** Ctrl+Shift+S.
- **Help:** F1.

## Documentation
- [`docs/part_format.md`](docs/part_format.md): design and file formats for system profiles,
  part definitions, the part library and save files, plus the measured Nanoblock dimensions.
- [`docs/turning.md`](docs/turning.md): how the Turn tool decides what turns, about which
  axis, and when a turn is refused.
- [`docs/nanoblock_parts.md`](docs/nanoblock_parts.md): the real Nanoblock part list from
  nanoblock.info, matched to LDraw files and BrickBuilder part ids.
