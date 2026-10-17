# Architecture

How the code is organised and how the editing features flow through it. Data formats:
`part_format.md`; decisions: `design.md`; turning and the clash test in depth: `turning.md`.

## Modules
```
src/brickbuilder/
  main.py              QApplication + QSurfaceFormat (Compatibility profile, GL 2.1)
  core/profile.py      Profile (TOML loader, palette, underside rules) + sub_to_world(): the one grid -> world mapping
  core/parts.py        PartDef, Joint + the built-in library loader (box, wedge and round bodies, sockets)
  core/geometry.py     Exact sub-grid geometry: Body (box, rounded box, wedge), RoundBody, wedge Cut planes,
                       per-sub-cell regions, the sharing rule (`compatible`), faces, ray vs convex solid,
                       seamless outlines
  core/model.py        Model: placed parts + sub-cell occupancy, frames, groups, grids for side studs and
                       joints, frame reuse, save v4 (+ v1-v3 load); turn / grid helpers (turn_about, ...)
  core/history.py      History: undo/redo; every UI edit goes through it; move_parts (turning, moving)
  core/connections.py  Contacts: studs in slots (with directions, half-inserted studs) and balls in cups;
                       the connection graph (Model.connections(), cached) + groups()
  core/motion.py       Turn planning: the moving set (the selection always moves; pin rule on the rest) and
                       full 3D free motions from the contacts (null space, numpy): turn / pose / slide /
                       locked / free; joint posing helpers (clamp_arm, min_rotation)
  core/collision.py    The clash test: SAT on convex solids (numpy, touching allowed) + studs only through
                       slots; a joined ball and cup may overlap
  core/camera.py       Orbit camera, orthographic projection, Z-up; preset views (VIEWS), fit
  core/picking.py      Mouse ray, ray/plane, ray/AABB (slab), brute-force model hit test
  core/renderer.py     Legacy GL: grid (or the working frame's), parts (cached fill + outline display lists
                       per part), moved/turned parts under a matrix, ghost (with slots and blocking studs),
                       selection / hover / highlight outlines, pivot marker, axis gizmo, optional Z clip
  core/tools.py        Tool enum: PLACE / SELECT / PAINT / ERASE / TURN
  ui/main_window.py    Menus and shortcuts, tool toolbar (Q/W/E/R/T), Parts tree (by category folder),
                       Colors and Groups docks, per-tool status bar, Save/Save As, close prompt
  ui/viewport.py       The 3D view widget shell: scene state, GL, painting, input dispatch, tools, undo,
                       New/Open; behaviour comes from the mixins below
  ui/placing.py        PlacingMixin: the Place tool preview (targets on faces, side studs, joints; turned
                       preview; working grid; nudging)
  ui/selecting.py      SelectionMixin: selection and groups, moving the selection (drag, nudge), Paint/Erase
  ui/turning.py        TurningMixin: the Turn tool (turning, sliding, posing, realign / reset)
  ui/view_controls.py  ViewControlsMixin: camera presets, orbit steps, fitting, gizmo clicks
  profiles/*.toml      Built-in system profiles (nanoblock.toml, incl. the 45-colour palette)
  parts/<profile>/<Category>/<name>.toml   Built-in parts; id = "<profile>:<file stem>"
tests/                 pytest suite (no GL)
```

## Runtime model
```python
PartDef      # id, name, category, bodies, cells, studs + stud_axes, antistuds (slots) + antistud_axes,
             # round_bodies, joints
Frame        # id, parent, origin (mm, parent space), rotation (quaternion); 0 = the root grid
Group        # id, name, parent: user-made subassemblies, separate from frames
PlacedPart   # id (stable int), part, frame, pos (SUB-GRID ints), turns (0..3), color, group, plus
             # derived world geometry: solids, edges, studs (+ axes), antistuds (+ axes), joint_solids,
             # joints, box
Model        # parts, frames, groups; occupancy: dict[(frame, sub-cell), [(part id, cut)]]
History      # every UI edit as undoable commands (lists of ops)
```

## Grid and geometry
- World axes **+X right, +Y forward, +Z up**; world units are **mm**. Cell size comes from the
  profile (`Viewport.profile`, always the built-in Nanoblock one); camera defaults are mm-scaled.
- Cell `(x, y, z)` occupies `[x-0.5, x+0.5]·cell.x`, `[y-0.5, y+0.5]·cell.y`, **`[z, z+1]·cell.z`**.
  Placement and occupancy use the finer sub-grid (`profile.subdiv`). `Profile.sub_to_world()` is
  the only grid -> world mapping (`cell_box()` builds on it); never re-derive it.
- A placed part's `pos` is the sub-grid position of its origin (min corner, bottom); `turns`
  rotates CCW about that corner (`model.rotate_cell`). `PlacedPart.solids` (world faces, convex) is
  what's rendered, picked and clash-tested; `box` is only the bounding AABB.
- Occupancy is `(frame, sub-cell) -> [(part id, Cut | None)]`, None = full; cuts are integer and
  canonical (`geometry.make_cut`) so complementary slopes compare exactly. Round bodies aren't in it.
- Studs and slots carry directions (`stud_axes`, `antistud_axes`); joints are `(kind, pivot, axis,
  slot)` in world space on placed parts.

## Frames
- A part's `pos` / `turns` / regions are in its frame's grid; its world geometry is that transformed
  by `Model.frame_matrix`. Placing against a part puts the new part in that part's frame
  (`Model.to_frame`).
- `History.move_parts(ids, world transform, target_frame=None)` moves frames the set owns outright,
  gives other moving parts a new child frame (their old grid moved), merges anything lined up with
  its home grid back into it (`model.to_parent_grid`), else onto another frame that lines up
  (`Model.lined_up_frames`), and refuses (unchanged, returns the reason) on a clash. A drag passes
  `target_frame`, which becomes everyone's home. Deleting parts removes emptied frames and groups.
- Grids for things not on a grid yet: `Model.side_stud_grid` (a side stud), `Model.joint_grid` (a part
  straight on a joint), `Model.find_grid` (an existing frame that lines up). The Place tool previews
  them as `Viewport._ghost_grid` until placing creates the frame (`History.add_part_in_new_frame`,
  which also reuses a lined-up frame).

## History
- **Edits from the UI go through `Viewport.history`**, never `Model` directly, or undo gets out of
  sync. One user action = one command (a list of ops: parts, colours, groups, frames).
- Commands that can fail (`move_parts`, `add_part_in_new_frame`) go through `_try_run`: applied op by
  op, the full clash test against everything that stayed, rolled back with the reason on failure.
- History owns the modified flag (`mark_clean()` on save, `reset()` on New/Open).

## Features
- **Placement**: `Viewport.update_ghost` → `_joint_target` (on a matching joint: `Model.joint_grid`)
  else `_target_under` (a side stud: `_side_stud_target`; a face: `model.placement_target` on the hit
  part's frame; else the working frame's ground; H = half-cell snap). The anchor cell goes on the
  target (`model.origin_for_anchor`); arrow keys nudge (`_grid_axes`, by screen projection); `[ / ]`
  turn the preview (`ghost_angle`); F sets `working_frame` (its grid is used and drawn for the ground).
  Valid: `Model.can_place` (occupancy + clash test), or `turned_placement_problem` on a grid of its
  own (needs a stud or joint contact). The ghost draws its slots (`Renderer.draw_slots`) and, when
  blocked, rings the studs in the way (`Model.blocking_studs`, `Renderer.draw_blocking`).
- **Selection and groups**: `Viewport.selection` (part ids); groups are `model.Group` in
  `Model.groups`, `PlacedPart.group` the innermost one. A click selects
  `Model.selection_unit(part, Viewport.select_context)` (outermost group; double-click drills in);
  Alt = one part. Delete / recolour / group / ungroup / rename are one command each.
- **Turn tool**: `motion.plan_turn` → `Viewport._start_turn` / `_drag_turn` (turn about an axis),
  `_drag_slide` (Ctrl; clamped by `_slide_range` so a stud stays in its slot), `_drag_pose` / `_drag_roll` (a ball joint); preview via `Renderer.render(turning=
  (ids, transform, valid), pivot=(point, axis))`, red from `Model.moved_overlaps` and
  `Model.joints_within_limits`; commit with `History.move_parts`. Keys: `turn_step`, `realign_selection`,
  `reset_joint`.
- **Moving**: Select-tool drag (`_start_drag` / `_update_drag` / `_finish_drag`, `move_parts(...,
  target_frame)`), arrows / PgUp / PgDown (`nudge_selection`, never changing frames).
- **Clash test**: `collision.clash` via `Model.part_shape` (cached). Used by previews, by every
  `_try_run` commit, by `can_place` and by `Model.collisions()` (View > Highlight Colliding Parts).
- **Connections**: `Model.connections()` (cached until the next change) from
  `connections.iter_contacts` and `joint_contacts`.
- **Camera**: `Camera.set_view` / `fit` (`camera.VIEWS`), View > Camera keys, gizmo clicks
  (`Viewport._gizmo_axis_at`). Middle mouse orbits / pans, wheel zooms.
- `Viewport.notice` is a one-line status-bar message (why something was refused, what's moving). A
  turn or drag in progress is cancelled by Esc, undo/redo, delete, tool change and New/Open.

## Rendering
- Renderer loads `Camera.get_projection_matrix()`, the same matrix picking inverts.
- Each part has two display lists, fill and outline: all fills are drawn first, then all outlines
  (drawing them together let later parts paint over earlier outlines). Outlines come from the merged
  shape (`geometry.part_outline`, once per part type), so multi-body parts have no seams.
- Display lists are keyed by (id, part, pos, turns, color, frame, box): anything else that changes a
  part's look must join the key. Parts being turned or dragged are drawn from their own lists under
  the move's matrix.
- Measured: first draw of 1000 bricks ≈ 550 ms, then 1000 parts / 8000 studs ≈ 25 ms per frame.
  Picking iterates every part (fine at this scale). VBOs/shaders are the longer-term plan.

## Saving
- `Model.to_dict` / `from_dict` (format: `part_format.md` "Save format"). Bad files raise
  `ModelError` and leave the model untouched. Saving writes a `.tmp` file and swaps it in, so a failed
  save never truncates the existing file.

## Testing
- `uv run pytest`: profile, parts, model, save/load, picking, history, groups, frames, connections,
  collisions, turning, moving, side studs, joints, camera; no GL. `test_model/*.json` are hand-made
  sample saves (gitignored); a test loads them when present.
- UI changes are checked with a script that drives `MainWindow` with synthetic mouse / key events,
  offscreen (`QT_QPA_PLATFORM=offscreen`) or in a real window for screenshots
  (`viewport.grabFramebuffer()`); not part of the suite.
