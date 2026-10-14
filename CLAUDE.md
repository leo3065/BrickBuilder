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
  core/parts.py      PartDef + built-in library loader (box bodies only so far)
  core/model.py      Model: PlacedPart dict + sub-cell occupancy, footprint/rotation, save v2 (+ v1 load)
  core/camera.py     Orbit camera, orthographic projection, Z-up
  core/picking.py    Mouse ray, ray/plane, ray/AABB (slab), brute-force model hit test
  core/renderer.py   Immediate-mode GL: grid, cubes + outlines, ghost, selection, axis gizmo,
                     optional Z clip plane (section_z)
  core/tools.py      Tool enum: PLACE / SELECT / PAINT / ERASE
  ui/main_window.py  Menus, tool toolbar (Q/W/E/R), color dock, file dialogs, unsaved prompt
  ui/viewport.py     QOpenGLWidget: input handling, tool dispatch, ghost preview
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
  `turns` rotates CCW about that corner (`model.rotate_cell`). Parts are only boxes so far,
  so `PlacedPart.box` (a world AABB) is what's rendered and picked.
- Colors are **palette ids** (`profile.palette`); parts are **part ids**; both are stable keys
  in save files, separate from their display `name`.
- Renderer loads `Camera.get_projection_matrix()`, the same matrix picking inverts.
- Ground placement only happens when the ray points downward; layer 0 sits on the grid.
- Save format v2 (see `docs/part_format.md`): `{version, profile, frames, parts: [{id, part,
  frame, pos (cells, 0.5 allowed), turns, color}]}`. v1 (`bricks` with float RGB) still loads
  as 1×1 bricks. Bad files raise `ModelError` and leave the model untouched. Bump `version`
  and keep older loader paths when the schema changes.
- Type hints are used throughout; `glm` (PyGLM) types for vectors.

## Known gaps / plan-vs-code drift (verify before relying on feature_plan.md)
- **6-view / isometric / 30° rotation buttons** were ticked in `feature_plan.md` but never
  existed in any commit (`git log -S isometric` only hits the plan). Now unticked.
- **Moving bricks** is listed in the done "building" item but isn't implemented.
- Bricks can go below the grid (`z < 0`). **Intentional**: no hard floor, since frames make
  a global floor meaningless and building from the top is legitimate. "Shift all" is planned.
- `resizeGL` divides by height (crash at 0).
- **Place tool always uses `brick_1x1`, turn 0** (build step 2b adds a part picker, rotate
  key, red ghost on overlap). Half-offset placement exists in the model but has no UI.
- Palette RGB values are eyeballed approximations; clear colors render opaque.
- README still describes a generic "brick building app" with "standard brick colors";
  should eventually state the Nanoblock-first / system-agnostic scope above.
- README/help say **Alt+Left orbit** and **Shift+Alt+Left pan**; the viewport only
  handles the middle button, and Alt+Left actually goes through the active tool.
- **Section view**: `Renderer.render(section_z=...)` supports a clip plane, but the
  viewport never passes it and there's no UI for it.
- **Ctrl+S is always "Save As"**: no current-file tracking.
- No `closeEvent`, so closing the window skips the unsaved-changes prompt.
- Selection in SELECT mode is display-only; `set_current_color` has a stub for
  repainting the selection.
- Picking iterates every part (fine at small scale); rendering is immediate mode
  every frame.
- Bodies render as full boxes: profile `clearance`, `body_height` and studs (`PartDef.studs`
  is computed) aren't drawn yet — studs come in step 2b. `grid_rotation` is unused.

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
