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
- How turning is checked (moving set, contacts, null space, clash test, tolerances): `docs/turning.md`.
- Design for profiles / part definitions / library / save format: `docs/part_format.md`
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
  (single body 3.05 + seating gap), stud Ø2.45 × 1.60 solid (re-measured). Use the stacking pitch for
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
  save/load, picking, history, groups, frames, connections, collisions, turning and moving — no
  GL). `test_model/*.json` are hand-made sample saves (gitignored); a test loads them when present.
  UI changes are checked with an offscreen `QT_QPA_PLATFORM=offscreen` script that drives
  `MainWindow` with synthetic mouse/key events (not part of the suite).

## Layout
```
src/brickbuilder/
  main.py            QApplication + QSurfaceFormat (Compatibility profile, GL 2.1)
  core/profile.py    Profile (TOML loader, palette) + sub_to_world(): the one grid -> world mapping
  core/parts.py      PartDef + built-in library loader (box and wedge bodies)
  core/geometry.py   Exact sub-grid geometry: Body (box, rounded box, wedge), wedge Cut planes, per-sub-cell regions,
                     sharing rule (`compatible`), faces, ray vs convex solid, seamless outline
  core/model.py      Model: PlacedPart dict + sub-cell occupancy, frames, groups, save v4 (+ v1-v3 load)
  core/history.py    History: undo/redo; every UI edit goes through it, never Model directly
  core/connections.py  Stud-in-antistud-slot graph (Model.connections(), cached) + groups()
  core/motion.py     Turn planning: moving set (selection always moves; pin rule on the rest) and
                     free motion from stud-in-slot contacts (null space, numpy): turn / locked / free
  core/collision.py  The clash test: SAT on convex solids (numpy, touching allowed) + studs only on slots
  core/camera.py     Orbit camera, orthographic projection, Z-up
  core/picking.py    Mouse ray, ray/plane, ray/AABB (slab), brute-force model hit test
  core/renderer.py   Legacy GL: grid (or the working frame's), parts (cached fill + outline display
                     lists per part), moved/turned parts under a matrix, ghost, selection/hover/
                     highlight outlines, pivot marker, axis gizmo, optional Z clip plane (section_z)
  core/tools.py      Tool enum: PLACE / SELECT / PAINT / ERASE / TURN
  ui/main_window.py  Menus and shortcuts, tool toolbar (Q/W/E/R/T), Parts tree (by category
                     folder), Colors and Groups docks, per-tool status bar, Save/Save As, close prompt
  ui/viewport.py     QOpenGLWidget: input, tool dispatch, ghost preview, selection levels, Turn
                     tool, dragging/nudging the selection, working frame (red preview = clash)
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
- `PartDef.studs` are stud positions in cells `(x, y, top height)`: derived ones sit at cell
  centres, explicit `[[socket]] type = "stud"` ones anywhere (e.g. on cell boundaries).
- `PartDef.antistuds` are **slots** (segments; a point = zero length) where a stud fits anywhere
  along: derived per body by the profile's `[[underside]]` rules (system specific; Nanoblock: 1×N
  one slot, 2×N one per row along the long side, Y on a tie, wider none), or `antistuds = "none"`
  + explicit sockets. Part files have no `ldraw` key (dropped; the LDraw names are in
  `docs/nanoblock_parts.md`). Rules from the real parts: docs/part_format.md
  "Undersides". Connections are derived from world positions (so they work across Z-turned
  frames), never saved.
- Colors are **palette ids** (`profile.palette`); parts are **part ids**; both are stable keys
  in save files, separate from their display `name`. Ids are ASCII `[a-z0-9_]` (checked on load).
  There's no translation for renamed ids: a save using an old id fails with "unknown part".
- Slope naming: `slope_{footprint}_wedge_{run}x{rise}[_inverted]`, shown as
  "Slope 1×2 wedge 1×1 [inverted]" (run = cells along the slope, rise = layers).
- **Edits from the UI go through `Viewport.history`** (parts, colours, groups, frames, moves),
  never `Model` directly, or undo gets out of sync. One user action = one command (list of ops).
  Commands that can fail (`move_parts`, `add_part_in_new_frame`) go through `_try_run`, which rolls
  back and returns the reason. History also owns the modified flag (`mark_clean()` on save,
  `reset()` on new/open).
- Renderer loads `Camera.get_projection_matrix()`, the same matrix picking inverts.
- Ground placement only happens when the ray points downward; layer 0 sits on the grid.
- **Frames** (`model.Frame`): a grid of its own = parent + origin (mm, parent space) + rotation
  (quaternion). Frame 0 is the root grid. A part's `pos`/`turns`/regions are in its frame's grid;
  its world geometry is that transformed by `Model.frame_matrix`. Occupancy is keyed by
  (frame, sub-cell); parts in different frames are compared with the clash test (`collision.py`):
  `can_place` checks both, `Model.collisions()` (cached) lists cross-frame clashes; `add_part` itself
  only refuses same-frame overlaps. Placing against a part
  puts the new part in that part's frame (`Model.to_frame`). A turned part's frame should be its
  original grid turned about the pivot, so it keeps its grid position (and builds stay on whole cells).
  `History.move_parts(ids, world transform)` does this: moves frames the set owns outright, gives
  other moving parts a new child frame, merges anything lined up with its parent grid back into it
  (`model.to_parent_grid`), and refuses (unchanged, returns the reason) on a clash. With
  `target_frame` (a drag) that frame becomes the home grid. Deleting parts removes emptied frames.
  Turns are about the shared axis of the holding studs (`model.turn_about(pivot, axis, deg)`;
  vertical for top studs, horizontal for a side stud). Studs and slots carry axes (`stud_axes`,
  `antistud_axes`, from socket `axis`); contacts need matching axes. A face with a side stud
  targets `Model.side_stud_grid` (reusing a lined-up frame via `Model.find_grid`); the Place tool
  previews it as `Viewport._ghost_grid` until placing creates the frame.
- Save format v4 (see `docs/part_format.md`): `{version, profile, frames: [{id: 0}, {id, parent,
  origin, rotation}...], groups: [{id, name, parent}...], parts: [{id, part, frame, pos (cells,
  0.5 allowed), turns, color, group?}]}`; frames and groups listed parent-first. v3 (no groups),
  v2 (root frame only) and v1 (`bricks` with float RGB) still load,
  v1 as 1×1 bricks. Bad files raise `ModelError` and leave the model untouched. Saving writes a `.tmp` file
  and swaps it in, so a failed save never truncates the existing file. Bump `version`
  and keep older loader paths when the schema changes.
- Type hints are used throughout; `glm` (PyGLM) types for vectors.

## How the editing features work (pointers)
- **Placement**: the cell under the cursor is where the part's **anchor cell** goes (A / Shift+A
  cycles bottom-layer cells, default nearest the centre; `model.origin_for_anchor`). The target
  cell comes from `Viewport._target_under` → `model.placement_target` (hit point + face normal,
  on the hit part's frame; else the working frame's ground; H = half-cell snap in XY). Arrow keys
  nudge it half a cell along its grid's axis nearest the screen direction (`_grid_axes`); the nudge
  resets when the target changes. `[ / ]` turn the preview off the grid (`ghost_angle`, about the
  anchor cell centre; placed with `History.add_part_in_new_frame`, needs a stud contact). F sets
  `working_frame`, whose grid is used (and drawn) for the ground.
- **Selection** (`Viewport.selection`, part ids) and **groups** (`model.Group`, `Model.groups`;
  `PlacedPart.group` = innermost group, separate from frames): a click selects
  `Model.selection_unit(part, Viewport.select_context)` (outermost group at the top level;
  double-click drills one level in); Alt = one part. Delete / recolour / group / ungroup / rename
  are one command each; `remove_parts` also drops emptied groups and frames.
- **Turn tool (T)**: `motion.plan_turn` (moving set + free motion), dragged in
  `Viewport._start_turn/_drag_turn/_finish_turn`, previewed with `Renderer.render(turning=(ids,
  transform, valid), pivot=...)` (the parts' own display lists under the matrix; red from
  `Model.moved_overlaps`), committed with `History.move_parts`. `[ / ]`, Shift+R: `turn_step`,
  `realign_selection`. Details and tolerances: `docs/turning.md`.
- **Moving the selection**: drag a selected part in the Select tool
  (`_start_drag/_update_drag/_finish_drag`, `move_parts(..., target_frame)`), or arrows / PgUp /
  PgDown (`nudge_selection`, along its own grid, never changing frames).
- **Clash test** (`collision.clash` via `Model.part_shape`, cached): bodies by SAT, studs as
  prisms that may enter another body only through one of its slots, base on or below the slot's
  plane (hollow undersides: a lower stud goes in less deep; it still connects with half its
  height in). Used by previews and by every
  `move_parts` / turned-placement commit against all staying parts; the Place tool on one grid
  still uses only the occupancy map.
- `Viewport.notice` is a one-line status-bar message (why something was refused, what's moving).
  A turn or drag in progress is cancelled by Esc, undo/redo, delete, tool change and New/Open.

## Known gaps / plan-vs-code drift (verify before relying on feature_plan.md)
- **6-view / isometric / 30° rotation buttons** were ticked in `feature_plan.md` once but never
  existed (`git log -S isometric` only hits the plan). Now unticked.
- Bricks can go below the grid (`z < 0`). **Intentional**: no hard floor, since frames make
  a global floor meaningless and building from the top is legitimate.
- Palette RGB values are eyeballed approximations; clear colors render opaque.
- Camera controls are middle mouse only (README and Help match); Alt+Left goes to the active tool.
- **Section view**: `Renderer.render(section_z=...)` supports a clip plane, but the
  viewport never passes it and there's no UI for it.
- Profile `clearance`, `body_height` and `grid_rotation` aren't used yet.
- Picking iterates every part (fine at small scale). Outlines come from the merged shape
  (`geometry.part_outline`, once per part type), so multi-body parts have no seams. Each part
  has two display lists: all fills are drawn first, then all outlines (drawing them together
  let later parts paint over earlier outlines). Display lists are keyed by (id, part, pos, turns,
  color, frame, box): anything else that changes a part's look must join the key. Measured:
  first draw of 1000 bricks ≈ 550 ms, then 1000 parts / 8000 studs ≈ 25 ms per frame.

## Architectural pressure from upcoming features
Done: parts, occupancy, frames (step A), groups, the Turn tool and turned placement (step B),
moving the selection, the clash test. Still ahead: ball joints (tilted frames, joint contacts and
limits in the turn finder), the full snapping solver (several moving frames, loops), copy/paste,
circular arrays, instances.
- Prefer migrating to VBOs/shaders before mesh-heavy features (joint parts, imported meshes).
Raise these trade-offs with the user before restructuring; don't silently rewrite.

## Working with the user
- Solo personal project, picked up after a long break; momentum matters more than
  perfection. Small, reviewable steps.
- Uses Blender as a proportion/cross-section reference (possible future: a
  "brickify" geometry-nodes pass, or OBJ/STL import here).
- Keep `feature_plan.md` checkboxes honest when finishing or discovering features.
