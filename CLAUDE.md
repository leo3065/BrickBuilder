# BrickBuilder — context for Claude

## What this is and why it exists
A PySide6 + legacy OpenGL desktop app for designing **Nanoblock** models (not Lego). Brick CAD tools
only ship Lego part libraries and grids, and voxel editors (e.g. MagicaVoxel) handle slopes,
half-offset layers and ball joints poorly: that gap is why this project exists. Keep it in mind when
choosing defaults.

**Scope: Nanoblock-first, system-agnostic by data.** Only a Nanoblock part library and palette will
be authored, but the tool should stay usable for similar systems (Lego, diamond blocks, other
micro-bricks).
- Anything that differs between systems lives in **data** (the profile, part files), not code: cell
  size, sub-grid, underside rules, socket types and limits, parts, palette. Don't hard-code
  Nanoblock numbers (4/4/3.125, 0.5 offsets) in rendering / picking / model code.
- Editor settings aren't system properties: the 7.5° rotation snap doesn't belong in the profile.
- Don't build features only another system needs (Lego plates at 1/3 height, Technic, a
  profile-switching UI) until there's an actual second system.

First real target: a custom **Skarmory** Nanoblock (no official set exists). Questions that drive
features: small vs DX scale; spread wings with or without ball joints (joints give wings their own
grid but are scarce and a weak point); two-sided wing colour vs resolution and strength. Wing support
borrows from the Koraidon/Miraidon sets (regular + sloped bricks bracing beyond the joints).

## Domain facts
- A cell is 4 × 4 mm with a **3.125 mm stacking pitch** (measured): **not a cube** (height / width ≈
  0.78). Anything doing proportions, rendering or import must respect this.
- Half-offset placement, slopes, multi-cell bricks, turned parts, side studs and ball joints are all
  real Nanoblock techniques.
- All measured numbers: `docs/measurements.md`. The real part list: `docs/nanoblock_parts.md` (check
  new parts against it).

## Running
- Python 3.13 with `uv`: `uv sync`, then `uv run run_app.py` (also the `brickbuilder` script). Root
  `main.py` is the leftover `uv init` stub.
- Tests: `uv run pytest` (no GL). UI changes: drive `MainWindow` with synthetic events (offscreen, or
  a real window for screenshots); see `docs/architecture.md` "Testing".

## Docs
- `docs/architecture.md`: modules, runtime model, frames, history, how each feature flows, rendering.
- `docs/part_format.md`: profile, part files, library and save format (the data reference).
- `docs/design.md`: decisions and why, worked examples from real sets, build history.
- `docs/turning.md`: how turning, posing and the clash test are checked, with tolerances.
- `docs/measurements.md`, `docs/nanoblock_parts.md`: the real parts.
- `feature_plan.md`: the todo list (keep its checkboxes honest); `README.md`: features and controls.

## Invariants that bite
- **Edits from the UI go through `Viewport.history`**, never `Model` directly. One user action = one
  command.
- `Profile.sub_to_world()` is the only grid -> world mapping; never re-derive it. World units are mm,
  +X right, +Y forward, +Z up.
- A part's `pos` / `turns` are on its **frame's** grid; world geometry goes through
  `Model.frame_matrix`. Frame 0 is the root grid.
- Part and palette ids are stable save keys, ASCII `[a-z0-9_]`, never translated.
- Save format changes: bump `version`, keep the older loader paths.
- Occupancy cuts are integer and canonical (`geometry.make_cut`); keep them exact.
- Display lists are keyed by (id, part, pos, turns, color, frame, box): anything else that changes a
  part's look must join the key.
- Type hints throughout; `glm` (PyGLM) types for vectors.

## Known gaps
- Section view: `Renderer.render(section_z=...)` supports a clip plane, but there's no UI for it.
- Profile `clearance`, `body_height` and `grid_rotation` aren't used yet.
- Palette RGB values are approximate; clear colours render opaque.
- Bricks can go below the grid (`z < 0`) on purpose: no hard floor (`docs/design.md`).
- Chains and closed loops of joints need the full snapping solver (`docs/design.md`).
- Prefer migrating to VBOs/shaders before mesh-heavy features (imported meshes). Raise such
  trade-offs with the user before restructuring; don't silently rewrite.

## Working with the user
- Solo personal project, picked up after a long break; momentum matters more than perfection.
  Small, reviewable steps; commit when asked, push when asked.
- Uses Blender as a proportion / cross-section reference (possible future: a "brickify"
  geometry-nodes pass, or OBJ/STL import here).
- Keep `feature_plan.md` checkboxes honest when finishing or discovering features.
