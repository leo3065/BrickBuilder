# BrickBuilder — context for Claude

## What this is and why it exists
A PySide6 + legacy OpenGL desktop app for designing **Nanoblock** models (not Lego).
Existing brick CAD tools only ship Lego part libraries and grids, and voxel editors
(e.g. MagicaVoxel) handle slopes, half-offset layers and ball joints poorly — that gap
is the reason this project exists. Keep that in mind when choosing defaults.

**Scope: Nanoblock-first, system-agnostic by data.** Only a Nanoblock part library and
palette will be authored, but the tool should stay usable for similar systems (Lego,
diamond blocks, other micro-bricks). Rule of thumb:
- Anything that differs between systems lives in **data**, not code: cell dimensions,
  stud pitch, offset step (half-unit), allowed rotation steps, part definitions, palette.
  Think of it as a "system profile" with Nanoblock as the only shipped profile.
- Don't hard-code Nanoblock numbers (4/4/3, 0.5 offset) in rendering/picking/model
  code; read them from the profile. The 7.5° rotation step is an arbitrary **editor snap
  setting**, not a system property — it doesn't belong in the profile.
- Real Nanoblock part list (nanoblock.info names and block numbers, LDraw files, our part ids):
  `docs/nanoblock_parts.md`. Check new parts against it.
- Design for profiles / part definitions / library / save v2: `docs/part_format.md`
  (TOML, cell units, derived studs, sockets with DOF, frames). Parametric part families
  are deliberately deferred — `params` key reserved only.
- Don't build features only another system needs (Lego plates at 1/3 height, SNOT,
  Technic, profile-switching UI) until there's an actual second system to support.

First real target: a custom **Skarmory** Nanoblock (no official set exists). Design
questions that drive features: small (standard Pokémon-set) vs DX scale; spread wings
with or without ball joints (joints give wings their own grid but are scarce and a weak
point); two-sided wing color vs resolution/strength. Wing support borrows from the
Koraidon/Miraidon sets (regular + sloped bricks bracing beyond the joints).

## Nanoblock domain facts
- 1×1 unit is nominally **4 mm × 4 mm × 3 mm** (W × D × H, studs excluded); the widely
  quoted "4×4×5" figure includes the 2 mm stud. Lego is 5×5×4 for comparison.
  Measured (see `docs/part_format.md`): stud pitch 4.00, **stacking pitch 3.125**
  (single body 3.05 + seating gap), stud Ø2.65 × 2.00 solid. Use the stacking pitch for
  proportions.
- So a unit cell is **not a cube**: height/width ≈ 0.78. Anything doing proportions,
  rendering or import/voxelization must respect this.
- Half-unit offset placement, slopes, multi-cell bricks, 90° Z rotation and ball joints
  are all real Nanoblock techniques the tool needs to support eventually
  (see `feature_plan.md`).

## Running
- Python 3.13, managed with `uv`.
- `uv sync` then `uv run run_app.py` (adds `src/` to `sys.path`).
- Also exposed as the `brickbuilder` script → `brickbuilder.main:main`.
- Root `main.py` is the leftover `uv init` stub; not the entry point.
- Tests: `uv run pytest` (pytest is a dev dependency; `tests/` covers profile, parts, model,
  save/load and picking — no GL). `test_model/*.json` are hand-made v1 sample saves
  (gitignored); a test loads them when present.

## Layout
```
src/brickbuilder/
  main.py            QApplication + QSurfaceFormat (Compatibility profile, GL 2.1)
  core/profile.py    Profile (TOML loader, palette) + sub_to_world(): the one grid -> world mapping
  core/parts.py      PartDef + built-in library loader (box and wedge bodies)
  core/geometry.py   Exact sub-grid geometry: Body, wedge Cut planes, per-sub-cell regions,
                     sharing rule (`compatible`), faces, ray vs convex solid, seamless outline
  core/model.py      Model: PlacedPart dict + sub-cell occupancy, footprint/rotation, save v2 (+ v1 load)
  core/history.py    History: undo/redo; every UI edit goes through it, never Model directly
  core/camera.py     Orbit camera, orthographic projection, Z-up
  core/picking.py    Mouse ray, ray/plane, ray/AABB (slab), brute-force model hit test
  core/renderer.py   Legacy GL: grid, parts (one cached display list per part: box, studs,
                     outlines), ghost, selection, axis gizmo, optional Z clip plane (section_z)
  core/tools.py      Tool enum: PLACE / SELECT / PAINT / ERASE
  ui/main_window.py  Menus (Edit > Undo/Redo, Rotate: Space / Shift+Space, anchor: A / Shift+A,
                     Half-Cell Snap: H, nudge: arrows), tool toolbar (Q/W/E/R), parts tree
                     (grouped by category folder) + color docks, status bar, Save/Save As (current file + title marker), close prompt
  ui/viewport.py     QOpenGLWidget: input handling, tool dispatch, ghost preview (red = overlap)
  profiles/*.toml    Built-in system profiles (nanoblock.toml, incl. 45-color palette)
  parts/<profile>/<Category>/<name>.toml   Built-in parts; id = "<profile>:<file stem>"
tests/               pytest suite
```

## Conventions & invariants
- World axes: **+X right, +Y forward, +Z up.**
- **World units are mm.** Cell size comes from the active profile (`Viewport.profile`,
  currently always the built-in Nanoblock one); camera defaults are mm-scaled.
- Cell index `(x, y, z)` occupies `[x-0.5, x+0.5]·cell.x`, `[y-0.5, y+0.5]·cell.y`,
  **`[z, z+1]·cell.z`**. Placement and occupancy use a finer **sub-grid** (`profile.subdiv`,
  half-cells in XY for Nanoblock). `Profile.sub_to_world()` is the only place the grid ->
  world mapping is defined (`cell_box()` builds on it) — never re-derive it.
- A placed part's `pos` is the sub-grid position of its **origin** (min corner, bottom) and
  `turns` rotates CCW about that corner (`model.rotate_cell`). Parts are bodies (boxes and
  wedges); `PlacedPart.solids` (world faces) is what's rendered and picked, `box` is only the
  bounding AABB.
- Occupancy is `sub-cell -> [(part id, Cut | None)]`: None = full. Two parts share a sub-cell
  only if both are cut by the same plane on opposite sides (complementary slopes). Cuts are
  integer and canonical (`geometry.make_cut`) so they compare exactly; keep it that way.
- Colors are **palette ids** (`profile.palette`); parts are **part ids**; both are stable keys
  in save files, separate from their display `name`. Ids are ASCII `[a-z0-9_]` (checked on load).
  Renaming a part id: add the old one to `model.RENAMED_PARTS` so existing saves still load.
- Slope naming: `slope_{footprint}_wedge_{run}x{rise}[_inverted]`, shown as
  "Slope 1×2 wedge 1×1 [inverted]" (run = cells along the slope, rise = layers).
- **Edits from the UI go through `Viewport.history`** (add_part / remove_part / set_color), never
  `Model` directly, or undo gets out of sync. One user action = one command (list of ops).
  History also owns the modified flag (`mark_clean()` on save, `reset()` on new/open).
- Renderer loads `Camera.get_projection_matrix()`, the same matrix picking inverts.
- Ground placement only happens when the ray points downward; layer 0 sits on the grid.
- Save format v2 (see `docs/part_format.md`): `{version, profile, frames, parts: [{id, part,
  frame, pos (cells, 0.5 allowed), turns, color}]}`. v1 (`bricks` with float RGB) still loads
  as 1×1 bricks. Bad files raise `ModelError` and leave the model untouched. Saving writes a `.tmp` file
  and swaps it in, so a failed save never truncates the existing file. Bump `version`
  and keep older loader paths when the schema changes.
- Type hints are used throughout; `glm` (PyGLM) types for vectors.

## Known gaps / plan-vs-code drift (verify before relying on feature_plan.md)
- **6-view / isometric / 30° rotation buttons** were ticked in `feature_plan.md` but never
  existed in any commit (`git log -S isometric` only hits the plan). Now unticked.
- **Moving bricks** is listed in the done "building" item but isn't implemented.
- Bricks can go below the grid (`z < 0`). **Intentional**: no hard floor, since frames make
  a global floor meaningless and building from the top is legitimate. "Shift all" is planned.
- `resizeGL` divides by height (crash at 0).
- Placement: the cell under the cursor is where the part's **anchor cell** goes (A / Shift+A
  cycles bottom-layer cells, default nearest the centre; `model.origin_for_anchor`). The target
  cell comes from `model.placement_target` (hit point + face normal; H toggles half-cell snap in
  XY); arrow keys nudge it half a cell along the world axis nearest the screen direction, and
  the nudge resets when the target changes.
- Palette RGB values are eyeballed approximations; clear colors render opaque.
- Camera controls are middle mouse only (README and Help match); Alt+Left goes to the active tool.
- **Section view**: `Renderer.render(section_z=...)` supports a clip plane, but the
  viewport never passes it and there's no UI for it.
- Selection in SELECT mode is display-only; `set_current_color` has a stub for
  repainting the selection.
- Picking iterates every part (fine at small scale); the renderer calls one cached display
  list per part each frame (VBOs/shaders are still the longer-term plan).
- Profile `clearance`, `body_height` aren't used yet. Outlines come from the merged shape
  (`geometry.part_outline`, once per part type), so multi-body parts have no seams. Each part
  has two display lists: all fills are drawn first, then all outlines (drawing them together
  let later parts paint over earlier outlines). First draw of 1000 bricks ≈ 550 ms.
- `grid_rotation` is unused. Measured: 1000 parts / 8000 studs ≈ 25 ms per frame. Display lists
  are keyed by (id, part, pos, turns, color) — anything else that changes a part's look must join the key.

## Architectural pressure from upcoming features
Done in step 2a: placed parts with part id, origin, quarter turns and a sub-cell occupancy
map (multi-cell parts, half-offset-ready). Still ahead:
- fine Z rotation (UI-snapped, default 7.5°), ball joints and per-part grids → bricks belong to a
  "grid frame" (transform); the global grid becomes just the root frame.
- ~~non-cube cells~~ done: `Profile.cell_box()` (build step 1).
- Prefer migrating to VBOs/shaders before mesh-heavy features (slopes, imported parts).
Raise these trade-offs with the user before restructuring; don't silently rewrite.

## Working with the user
- Solo personal project, picked up after a long break; momentum matters more than
  perfection. Small, reviewable steps.
- Uses Blender as a proportion/cross-section reference (possible future: a
  "brickify" geometry-nodes pass, or OBJ/STL import here).
- Keep `feature_plan.md` checkboxes honest when finishing or discovering features.
