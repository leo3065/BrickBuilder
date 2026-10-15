# BrickBuilder
A Python-based GUI program for designing 3D models in Nanoblock-style micro bricks. Nanoblock is the only system with a part library and palette, but grid sizes, parts and colors come from data, so other similar systems can be added without code changes (see `docs/part_format.md`).

## Feature plan
### Basic

#### Editing
- [x] Building with parts that snap to the grid, including adding and removing them. When adding, the new part goes against the face under the cursor, or on the grid if nothing is under the cursor. Keep the outline of the model clean.
- [x] When in placing mode, showing a preview of the brick block to be placed.
- [x] Adding support for brick block rotation around its Z axis with 90 degrees increment.
- [x] Half-offset placement: a toggle (H) that snaps placement to half-cells, and arrow keys to nudge the preview by half a cell.
- [x] Undo/redo.
- [x] Multi-select: click, Ctrl+click, box drag, double-click for a connected subassembly, select all; delete and recolour the selection as one undo step. (Moving a selection is the next item.)
- [ ] Groups: named, nestable subassemblies (Ctrl+G / Ctrl+Shift+G), a Groups dock, hover outline; click selects the outermost group, double-click drills in, Alt+click picks one part. Saved in the file. See docs/part_format.md "Groups, pins and moving subassemblies".
- [ ] Moving and rotating already placed parts (pick a part up, keep its color, put it down elsewhere or turned).
- [ ] Shifting all bricks (or a selection) by whole cells in any direction at once, e.g. to make room below a model that was built from the top down.
- [x] Highlight parts that aren't connected to the main build (View > Highlight Unconnected Parts, U): parts outside the largest connected group get an orange outline.

#### Files and settings
- [x] A save/load function to save the current model and load a saved model.
- [x] Save (to the current file) as well as Save As, and the unsaved-changes prompt when closing the window.
- [ ] Preferences dialog, saved per user: undo history size (fixed at 500 for now), rotation snap angle (default 7.5°) and similar editor settings.
- [ ] Parts list (bill of materials): count of each part per color, e.g. for finding kits that contain them on nanoblock.info.

#### View
- [x] A 3D view with free rotate and zoom in/out, with a grid on XY plane. Coordinate system: +X is Right, +Y is Forward, +Z is Up.
- [ ] Buttons/Widgets for rotating to 6 main views (front, back, top, bottom, left, right), to the isometric view, as well as for rotating views in 30 degrees increment around X, Y, and Z axis.
- [ ] Allowing section view of the model, especially viewing blocks under a selected layer. Makes it easy to go though layers.
- [ ] Smooth shading for curved parts (round parts currently show faint bands, one per flat facet). Low priority.
- [ ] Draw bodies with the profile's measured `clearance` and `body_height`, so neighbouring bricks show a seam. Low priority: the outlines already show where bricks meet.

#### Parts
- [x] Grid dimensions come from a system profile; Nanoblock is 4 × 4 × 3.125 mm (measured stacking pitch). A UI for switching profiles is deliberately deferred until there's a second system.
- [x] Data-driven part shape and size definition (see `docs/part_format.md`): box bodies, including rounded corners, and explicit stud and antistud positions.
- [x] Slopes in part definitions (wedge bodies, with complementary slopes sharing cells). Starter set: 1×2 and 1×2×2, normal and inverted.
- [x] More slope parts: 1×3, 2×2, 2×3 and 2×4 slopes (nanoblock.info "Slope 1" shapes), confirmed against real parts.
- [x] Base plates: 10×10 and 20×20.
- [x] More box-based parts from `docs/nanoblock_parts.md`: flat 1×2 and 2×4, 2×2 L, 2×3 T, and the 1×3 with 2 studs and single-centre-stud 1×2 and 2×2 (explicit stud sockets off the cell centres).
- [x] Round parts: round 1×1, 1×2, 1×3, 1×4, 2×2 and the 2×2 fan (boxes with `corner_radius`).
- [ ] Joint parts: ball and socket on 1×2 and 2×2 (nanoblock.info JO-C / JO-D). Needs new body shapes (a sphere and a cup) or mesh bodies; the joint behaviour is under Intermediate.
- [ ] A menu for browsing the part library, with a tree view, thumbnail previews and mark-as-favorite. (The tree view grouped by category is done; thumbnails and favorites are not.)

#### Colors
- [x] Allowing selecing the color of the brick blocks, both before building and after building.
- [x] Adding a color palette menu for brick colors.
- [ ] Custom colors in a separate user palette file (with stable ids so saves keep working), which can be exported and imported to share them.
- [ ] Allowing semi-transparent brick blocks. (Data is ready: palette colors are flagged `clear` and carry an `alpha`.)

### Intermediate
- [x] Connections on one grid: antistud slots on every underside (from the real parts) and a graph of which studs sit in which slots. Worked out from the parts, not saved. Still to extend for frames (rotated parts, joints).
- [ ] Allowing fine rotation of brick blocks around its Z axis, snapped in the UI to a configurable increment (default 7.5 degrees). Only allowed where the connection permits it (in practice a part held by a single stud); the part turns about that stud and gets its own grid frame. New blocks built on the rotated block snap to the same grid as the rotated block. Optionally, also placing a part into another part's frame without touching it.
- [ ] Adding support for brick block to align to another brick block by rotating around the Z axis. This works by fixing a selected point of a brick block, and aligning another selected point of the same brick block to face a selected point on another brick block.
- [ ] Snapping solver: contacts as errors minimised by least squares over the dragged frames; free motions from the same setup (hinges, locks, slides); keeps loops closed. Used by turning, align, ball joints and circular arrays. See docs/part_format.md.
- [ ] Pins and joint chains: each connected component has one pin (explicit, else grounded, else the larger side); turning at a joint moves the unpinned side.
- [ ] Instances: define a subassembly once, place it several times, editing it updates every copy (like LDraw multi-part files).
- [ ] Circular array: copy a selection of parts (a subassembly, possibly spanning several frames) n times, each copy turned 360/n° about a centre, e.g. rings of rounded 1×N and the alternating round 1×4 / 1×3 body segments of the Rayquaza DX set. Copies turned by a multiple of 90° reuse existing frames (that ring needs only the root grid and one 45° frame). Checks the closing contacts and reports any gap. Needs multi-select.
- [ ] Allowing ball joint blocks (a socket and a ball), with free rotation of the ball joint bloc around the joint point. The ball joint block will snap to the socket block. (They might not be used in pairs.)
- [ ] Add a view option that highlights colliding parts in different frames (rotated parts, joints). Within one frame, overlaps are already refused when placing and loading.
- [ ] Bringing two frames (Z-rotated parts or ball joints) onto the same grid with minimal rotation.

### Advanced
- [ ] Exporting the model for the current view as an image, both raster and vector formats.
- [ ] Exporting the model as a 3D model file, such as .stl or .obj.
- [ ] Exporting the model as multiple images for guide, with layer-by-layer and part-by-part steps.
- [ ] Importing the model from a 3D model file, such as .stl or .obj and converting it to brick blocks builds.
- [ ] Allowing split the importing model to multiple parts before converting to brick blocks, each part using different grid rotation (for example, for a bird model, wings and the body can be built with different grid rotations, joined by one or more ball joint blocks).
- [ ] A plugin system for extening the functionality of the program.
