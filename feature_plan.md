# BrickBuilder
A Python-based GUI program for building and designing 3D brick models.

## Feature plan
### Basic
- [x] A 3D view with free rotate and zoom in/out, with a grid on XY plane. Cooridnate system: +X is Right, +Y is Forward, +Z is Up.
- [x] Building using 1x1x1 brick blocks (use cube shape for now) that snaps to grid, including adding, removing, and moving blocks. When adding, the new block will be placed on the face of the selected block, or on the grid if no block is selected. Keep the outline of the model clean.
- [x] A save/load function to save the current model and load a saved model.
- [x] Buttons/Widgets for rotating to 6 main views (front, back, top, bottom, left, right), to the isometric view, as well as for rotating views in 30 degrees increment around X, Y, and Z axis.
- [x] When in placing mode, showing a preview of the brick block to be placed.
- [x] Allowing selecing the color of the brick blocks, both before building and after building.
- [ ] Allowing section view of the model, especially viewing blocks under a selected layer. Makes it easy to go though layers.
- [ ] Multi-select function for various operations, such as moving, removing, and color changing. 
- [x] Adding a color palette manu for brick colors.
- [ ] Ability to add custom colors to the palette.
- [ ] Exporting and importing color palettes.
- [ ] Allowing semi-transparent brick blocks.
- [ ] Customizable grid dimentions (default to wxdxh: 4mm x 4mm x 3mm).
- [ ] Adding support for data-driven brick block shape and size definition.
- [ ] A manu for browing brick block library, with a treeview, a thumbnail preview for the brick blocks, and mark-as-favorite function. 
- [ ] Adding support for brick block rotation around its Z axis with 90 degrees increment.
- [ ] Adding support half-brick offset brick placement that can be toggled on and off.

### Intermediate
- [ ] Allowing fine rotation of brick blocks around its Z axis in 7.5 degrees increment.
- [ ] Adding support for brick block to align to another brick block by rotating around the Z axis. This works by fixing a selected point of a brick block, and aligning another selected point of the same brick block to face a selected point on another brick block. New blocks built on the rotated block will snap to the same grid as the rotated block.
- [ ] Allowing snapping a block to the same grid as another block.
- [ ] Allowing ball joint blocks (a socket and a ball), with free rotation of the ball joint bloc around the joint point. The ball joint block will snap to the socket block. (They might not be used in pairs.)
- [ ] Add a view option that highlights the colliding blocks.
- [ ] Allowing rotating 2 blocks around their Z axis to the same grid with minimal rotation.
- [ ] Allowing free rotating 2 ball joint blocks to the same grid with minimal rotation.

### Advanced
- [ ] Exporting the model for the current view as an image, both raster and vector formats.
- [ ] Exporting the model as a 3D model file, such as .stl or .obj.
- [ ] Exporting the model as multiple images for guide, with layer-by-layer and part-by-part steps.
- [ ] Importing the model from a 3D model file, such as .stl or .obj and converting it to brick blocks builds.
- [ ] Allowing split the importing model to multiple parts before converting to brick blocks, each part using different grid rotation (for example, for a bird model, wings and the body can be built with different grid rotations, joined by one or more ball joint blocks).
- [ ] A plugin system for extening the functionality of the program.
