# BrickBuilder
A Python-based GUI program for designing 3D models in Nanoblock-style micro bricks. Nanoblock is the only system with a part library and palette, but grid sizes, parts and colors come from data, so other similar systems can be added without code changes (see `docs/part_format.md`).

## Feature plan
### Basic
- [x] A 3D view with free rotate and zoom in/out, with a grid on XY plane. Coordinate system: +X is Right, +Y is Forward, +Z is Up.
- [x] Building with parts that snap to the grid, including adding and removing them. When adding, the new part goes against the face under the cursor, or on the grid if nothing is under the cursor. Keep the outline of the model clean.
- [x] A save/load function to save the current model and load a saved model.
- [x] Save (to the current file) as well as Save As, and the unsaved-changes prompt when closing the window.
- [x] Undo/redo.
- [ ] Preferences dialog, saved per user: undo history size (fixed at 500 for now), rotation snap angle (default 7.5°) and similar editor settings.
- [ ] Buttons/Widgets for rotating to 6 main views (front, back, top, bottom, left, right), to the isometric view, as well as for rotating views in 30 degrees increment around X, Y, and Z axis.
- [x] When in placing mode, showing a preview of the brick block to be placed.
- [x] Allowing selecing the color of the brick blocks, both before building and after building.
- [ ] Allowing section view of the model, especially viewing blocks under a selected layer. Makes it easy to go though layers.
- [ ] Multi-select function for various operations, such as moving, removing, and color changing. 
- [ ] Moving and rotating already placed parts (pick a part up, keep its color, put it down elsewhere or turned).
- [ ] Shifting all bricks (or a selection) by whole cells in any direction at once, e.g. to make room below a model that was built from the top down.
- [x] Adding a color palette menu for brick colors.
- [ ] Custom colors in a separate user palette file (with stable ids so saves keep working), which can be exported and imported to share them.
- [ ] Allowing semi-transparent brick blocks. (Data is ready: palette colors are flagged `clear` and carry an `alpha`.)
- [x] Grid dimensions come from a system profile; Nanoblock is 4 × 4 × 3.125 mm (measured stacking pitch). A UI for switching profiles is deliberately deferred until there's a second system.
- [x] Adding support for data-driven part shape and size definition: box-shaped parts (see `docs/part_format.md`).
- [x] Slopes in part definitions (wedge bodies, with complementary slopes sharing cells). Starter set: 1×2 and 1×2×2, normal and inverted.
- [x] More slope parts: 1×3, 2×2, 2×3 and 2×4 slopes (nanoblock.info "Slope 1" shapes), confirmed against real parts.
- [x] Base plates: 10×10 and 20×20.
- [x] More box-based parts from `docs/nanoblock_parts.md`: flat 1×2 and 2×4, 2×2 L, 2×3 T, and the 1×3 with 2 studs and single-centre-stud 1×2 and 2×2 (explicit stud sockets off the cell centres).
- [ ] Round parts and mesh bodies (e.g. joints) in part definitions. Round 1×1, 1×2, 1×3, 1×4, 2×2 and the 2×2 fan (boxes with `corner_radius`) are done; next: joints.
- [ ] A menu for browsing the part library, with a tree view, thumbnail previews and mark-as-favorite. (The tree view grouped by category is done; thumbnails and favorites are not.)
- [x] Adding support for brick block rotation around its Z axis with 90 degrees increment.
- [x] Half-offset placement: a toggle (H) that snaps placement to half-cells, and arrow keys to nudge the preview by half a cell.
- [ ] Parts list (bill of materials): count of each part per color, e.g. for finding kits that contain them on nanoblock.info.
- [ ] Highlight parts that aren't connected to anything (e.g. placed against a side face, which is allowed while designing).

### Intermediate
- [ ] Allowing fine rotation of brick blocks around its Z axis, snapped in the UI to a configurable increment (default 7.5 degrees). Only allowed where the connection permits it (in practice a part held by a single stud); the part turns about that stud and gets its own grid frame. New blocks built on the rotated block snap to the same grid as the rotated block. Optionally, also placing a part into another part's frame without touching it.
- [ ] Adding support for brick block to align to another brick block by rotating around the Z axis. This works by fixing a selected point of a brick block, and aligning another selected point of the same brick block to face a selected point on another brick block.
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
