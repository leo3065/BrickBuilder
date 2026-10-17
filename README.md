# BrickBuilder

A desktop app for designing models in **Nanoblock** micro bricks, built with PySide6 and OpenGL.

Brick CAD tools ship Lego part libraries and grids, and voxel editors handle slopes, half-offset
layers and ball joints poorly. BrickBuilder works on Nanoblock's own grid (4 × 4 mm cells,
3.125 mm per layer, measured) with Nanoblock parts and colours. Grid sizes, parts and colours are
data, not code, so other micro-brick systems could be added without changing the program.

## Features
- **Parts**, in a categorised list:
  - **Bricks:** 1×1, 1×2, 1×3, 1×4, 1×6, 2×2, 2×3, 2×4, 2×8; flat (studless) 1×2 and 2×4; 2×2 L and
    2×3 T; the 1×2 and 2×2 with a single centre stud, the 1×3 with 2 studs, and the 1×1 with a
    side stud.
  - **Slopes:** 1×2 (with a 1- or 2-layer wedge), 1×3, 2×2, 2×3 and 2×4, plus inverted versions of
    the two 1×2 slopes. A slope and its inverted partner can share a cell, as in two-colour
    patterns from real sets.
  - **Round:** 1×1 and 2×2 cylinders, 1×2, 1×3 and 1×4 with rounded ends, and the 2×2 quarter-circle fan.
  - **Plates:** 10×10 and 20×20 base plates.
- **Building that follows the real parts.** Parts snap to the grid, in 90° steps and at half-cell
  offsets. Undersides take studs where the real ones do (a 1×N's hollow slot anywhere along it, a
  2×N one slot per row, and so on), and a placement that would put a stud where it can't go is
  refused. The preview shows its underside slots in blue and rings any stud in the way in red.
- **Turned parts.** Turn a placed part to any angle about the stud it's held by, slide it along
  the slot it's in, or place a part already turned. Whatever is built on a turned part follows its
  grid, and parts turned alike share one, so they can be bridged.
- **Side studs.** Build sideways off the 1×1 side-stud brick. Side studs in one plane share a
  grid, so a part can bridge them, and a part on a side stud turns about it.
- **Moving and grouping.** Select parts or whole named, nestable groups; move them by dragging
  onto any face or grid, or nudge them with the arrow keys; delete, recolour, group and ungroup.
- **Checks:** View > Highlight Unconnected Parts (U) marks parts the main build doesn't hold;
  View > Highlight Colliding Parts (O) marks parts on different grids that overlap.
- **The 45 official Nanoblock colours.** Names come from nanoblock.info; the RGB values are
  approximate.
- **Undo/redo** for every edit, Save / Save As, and a prompt before closing with unsaved changes.

See [`feature_plan.md`](feature_plan.md) for what's planned next (joints, copy/paste, circular
arrays and more).

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

### Place (Q)
Click to place the part chosen in the Parts list; Ctrl + click removes a part.
- **Space / Shift+Space:** rotate the part 90°.
- **A / Shift+A:** choose which of its cells sits under the cursor (starts nearest the centre).
- **H:** toggle half-cell snapping. **Arrow keys:** nudge the preview half a cell.
- **[ / ]:** turn the preview off the grid in 7.5° steps (it then needs a stud to sit on);
  **Shift+R** puts it back.
- **Side studs:** hover the face a side stud sticks out of to build on the stud.
- **F:** use the grid of the part under the cursor for empty space and the ground too; F over
  empty space goes back to the main grid.

### Select (W)
- **Click** a part, or its whole outermost group (outlined in blue on hover). **Double-click**
  drills into a group; **Alt+click** picks a single part; **Ctrl+click** adds or removes; **drag**
  from empty space for a box. **Ctrl+A** selects all, **Esc** clears; Edit > Select Connected grows
  the selection to whole connected subassemblies.
- **Drag a selected part** to move the selection onto any face, grid or side stud (Space turns it
  90°, [ / ] a fine turn, Esc cancels). **Arrow keys** move it half a cell (H) or a cell along its
  own grid, **PgUp / PgDown** a layer.
- **Delete** removes the selection; picking a colour recolours it.
- **Ctrl+G / Ctrl+Shift+G:** group / ungroup. The Groups dock lists the groups with part counts
  (click to select, double-click to rename).

### Turn (T)
- **Drag** a part (or the selection) to turn it about the stud it's held by, in 7.5° steps;
  **Shift** turns freely. **Ctrl+drag** slides it along the slot it's held in.
- **[ / ]** turn the selection a step; **Shift+R** turns it back onto its grid.
- If the contacts lock it (studs on different axes, two studs in one slot), the status bar says
  why; a red preview means it would overlap something.

### Paint (E) and Erase (R)
Click to recolour a part with the current colour, or to remove it.

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
  axis, and when a turn is refused, plus the clash test and its tolerances.
- [`docs/nanoblock_parts.md`](docs/nanoblock_parts.md): the real Nanoblock part list from
  nanoblock.info, matched to LDraw files and BrickBuilder part ids, with kit usage notes.
