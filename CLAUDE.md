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
- Don't hard-code Nanoblock numbers (4/4/3, 0.5 offset, 7.5°) in rendering/picking/model
  code; read them from the profile.
- Don't build features only another system needs (Lego plates at 1/3 height, SNOT,
  Technic, profile-switching UI) until there's an actual second system to support.

First real target: a custom **Skarmory** Nanoblock (no official set exists). Design
questions that drive features: small (standard Pokémon-set) vs DX scale; spread wings
with or without ball joints (joints give wings their own grid but are scarce and a weak
point); two-sided wing color vs resolution/strength. Wing support borrows from the
Koraidon/Miraidon sets (regular + sloped bricks bracing beyond the joints).

## Nanoblock domain facts
- 1×1 unit = **4 mm × 4 mm × 3 mm** (W × D × H, studs excluded). The widely quoted
  "4×4×5" figure wrongly includes stud height. Lego is 5×5×4 for comparison.
- So a unit cell is **not a cube**: height/width = 0.75. Anything doing proportions,
  rendering or import/voxelization must respect this.
- Half-unit offset placement, slopes, multi-cell bricks, 90° Z rotation and ball joints
  are all real Nanoblock techniques the tool needs to support eventually
  (see `feature_plan.md`).

## Running
- Python 3.13, managed with `uv`.
- `uv sync` then `uv run run_app.py` (adds `src/` to `sys.path`).
- Also exposed as the `brickbuilder` script → `brickbuilder.main:main`.
- Root `main.py` is the leftover `uv init` stub; not the entry point.
- No tests yet. `test_model/*.json` are hand-made sample saves (gitignored).

## Layout
```
src/brickbuilder/
  main.py            QApplication + QSurfaceFormat (Compatibility profile, GL 2.1)
  core/brick.py      Brick(position: ivec3, color: vec3)
  core/model.py      Model: dict[(x,y,z)] -> Brick, modified flag, JSON save/load (version 1)
  core/camera.py     Orbit camera, orthographic projection, Z-up
  core/picking.py    Mouse ray, ray/plane, ray/AABB (slab), brute-force model hit test
  core/renderer.py   Immediate-mode GL: grid, cubes + outlines, ghost, selection, axis gizmo,
                     optional Z clip plane (section_z)
  core/colors.py     Named palette (placeholder "LEGO-ish" colors)
  core/tools.py      Tool enum: PLACE / SELECT / PAINT / ERASE
  ui/main_window.py  Menus, tool toolbar (Q/W/E/R), color dock, file dialogs, unsaved prompt
  ui/viewport.py     QOpenGLWidget: input handling, tool dispatch, ghost preview
```

## Conventions & invariants
- World axes: **+X right, +Y forward, +Z up.**
- Grid units are currently abstract 1.0 cubes (not yet scaled to 4×4×3).
- Brick index `(x, y, z)` occupies X∈[x-0.5, x+0.5], Y∈[y-0.5, y+0.5], **Z∈[z, z+1]**.
  The renderer applies `glTranslatef(0,0,0.5)` around brick drawing and `picking.py`
  hard-codes the matching AABB — change both together, or better, centralize it.
- Ground placement only happens when the ray points downward; layer 0 sits on the grid.
- Save format: `{"version": 1, "bricks": [{x,y,z,r,g,b}, ...]}` with float RGB.
  Bump `version` and keep a loader path for v1 when the schema changes.
- Type hints are used throughout; `glm` (PyGLM) types for vectors.

## Known gaps / plan-vs-code drift (verify before relying on feature_plan.md)
- **6-view / isometric / 30° rotation buttons** were ticked in `feature_plan.md` but never
  existed in any commit (`git log -S isometric` only hits the plan). Now unticked.
- **Moving bricks** is listed in the done "building" item but isn't implemented.
- `Camera.get_projection_matrix()` (used by picking) and the renderer's own `glOrtho`
  call (`renderer.py:33`) duplicate the projection — keep them in sync or unify.
- Nothing stops bricks below the grid: looking up at a layer-0 bottom face snaps the
  ghost to `z = -1`. Undecided whether layer 0 should be a hard floor.
- `resizeGL` divides by height (crash at 0); after a Ctrl+click erase in Place mode the
  ghost is stale until the mouse moves; load ignores `version`.
- `__pycache__/*.pyc` files are tracked in git (committed before `.gitignore`); untrack
  with `git rm -r --cached` when convenient.
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
- Picking iterates every brick (fine at small scale); rendering is immediate mode
  every frame.

## Architectural pressure from upcoming features
The `dict[(x,y,z)] -> Brick` model assumes one brick = one cell on one global grid.
Planned features break that:
- multi-cell / data-driven shapes → bricks need a part id, origin, rotation and a
  footprint; keep a separate occupancy map (cell → brick) for collisions and picking.
- half-brick offsets → consider an internal half-unit grid (double resolution) rather
  than float positions.
- fine Z rotation (7.5°), ball joints and per-part grids → bricks belong to a
  "grid frame" (transform); the global grid becomes just the root frame.
- non-cube cells (4×4×3) → a single place for cell-to-world scale used by renderer,
  picking and camera, sourced from the system profile.
- Prefer migrating to VBOs/shaders before mesh-heavy features (slopes, imported parts).
Raise these trade-offs with the user before restructuring; don't silently rewrite.

## Working with the user
- Solo personal project, picked up after a long break; momentum matters more than
  perfection. Small, reviewable steps.
- Uses Blender as a proportion/cross-section reference (possible future: a
  "brickify" geometry-nodes pass, or OBJ/STL import here).
- Keep `feature_plan.md` checkboxes honest when finishing or discovering features.
