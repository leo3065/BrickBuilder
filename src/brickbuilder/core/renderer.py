import OpenGL.GL as gl
import glm
import numpy as np
import math
from brickbuilder.core.geometry import face_normal

STUD_SEGMENTS = 16

class Renderer:
    def __init__(self):
        # Display lists for a stud (fill, rim outline), keyed by (diameter, height), and one
        # compiled list per placed part, keyed by everything that affects its look.
        # They belong to the GL context, so initialize() drops them.
        self._stud_lists = {}
        self._part_lists = {}

    def initialize(self):
        self._stud_lists = {}
        self._part_lists = {}
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_LIGHTING)
        gl.glEnable(gl.GL_LIGHT0)
        gl.glEnable(gl.GL_COLOR_MATERIAL)
        gl.glEnable(gl.GL_NORMALIZE)
        
        # Light position (fixed relative to camera if not transformed, or world if transformed? 
        # Light position is transformed by current ModelView when specified.
        # We can set it in render loop to be fixed relative to world/camera.

    def render(self, camera, model, profile, ghost, width, height, selected_solids=None, show_grid=True, show_gizmo=True, section_z=None):
        # ghost: (solids, stud positions, valid) or None; solids are lists of world-space faces
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix()

        # Same projection matrix that picking inverts
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadTransposeMatrixf(np.array(proj, dtype=np.float32).flatten())

        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadTransposeMatrixf(np.array(view, dtype=np.float32).flatten())
        
        # Section View (Clipping Plane)
        if section_z is not None:
             # Plane equation: Ax + By + Cz + D = 0
             # We want to clip everything ABOVE section_z.
             # So we want to KEEP everything where z <= section_z.
             # Or: 0x + 0y - 1z + section_z >= 0  => -z >= -section_z => z <= section_z
             # Equation: (0, 0, -1, section_z)
             
             # Note: glClipPlane transforms the plane equation by the inverse of the current modelview matrix 
             # when it is specified. So it becomes fixed in eye coordinates.
             # We want it fixed in World Coordinates (Z axis).
             # So we should set it while ModelView is just the View matrix (which it is now).
             
             plane = [0.0, 0.0, -1.0, float(section_z)]
             gl.glClipPlane(gl.GL_CLIP_PLANE0, plane)
             gl.glEnable(gl.GL_CLIP_PLANE0)
        
        gl.glDisable(gl.GL_LIGHTING)
        if show_grid:
            self.draw_grid(profile)
        gl.glEnable(gl.GL_LIGHTING)

        # Render Bricks (one box per placed part; boxes come from the model's sub-grid mapping)
        self.render_bricks(model, profile)

        if ghost:
            self.render_ghost(profile, *ghost)

        if selected_solids:
            self.render_selection(selected_solids)

        if section_z is not None:
            gl.glDisable(gl.GL_CLIP_PLANE0)
        
        # Draw Gizmo
        if show_gizmo:
            self.draw_orientation_gizmo(camera, width, height)

    def render_selection(self, solids):
        # Draw a wireframe around the selected part
        gl.glDisable(gl.GL_LIGHTING)
        gl.glDisable(gl.GL_DEPTH_TEST) # See selection through walls
        
        gl.glLineWidth(3.0)
        gl.glColor3f(1.0, 1.0, 0.0) # Yellow
        self.draw_edges(solids)
        gl.glLineWidth(1.0)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_LIGHTING)

    def draw_orientation_gizmo(self, camera, width, height):
        gizmo_size = 150
        padding = 10
        
        # Save state
        gl.glPushAttrib(gl.GL_VIEWPORT_BIT | gl.GL_ENABLE_BIT | gl.GL_DEPTH_BUFFER_BIT)
        gl.glDisable(gl.GL_LIGHTING)
        gl.glDisable(gl.GL_DEPTH_TEST) # Gizmo always on top
        
        # Set Viewport to top-right
        gl.glViewport(width - gizmo_size - padding, height - gizmo_size - padding, gizmo_size, gizmo_size)
        
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        # Ortho box for gizmo
        gl.glOrtho(-2, 2, -2, 2, -10, 10)
        
        gl.glMatrixMode(gl.GL_MODELVIEW)
        # Create a rotation-only view matrix
        # We can extract rotation from camera view matrix
        view = camera.get_view_matrix()
        
        # In GLM view matrix, the top-left 3x3 is the rotation (if no scaling)
        # We want to place the camera at some distance looking at 0,0,0
        # But easier: just load the view rotation.
        # However, lookAt(eye, target, up) creates translation too.
        # Let's recreate a matrix with only rotation logic.
        
        # Actually simplest: Use the same rotation angles but fixed distance.
        gizmo_cam_pos = glm.vec3(
            3.0 * math.cos(camera.pitch) * math.cos(camera.yaw),
            3.0 * math.cos(camera.pitch) * math.sin(camera.yaw),
            3.0 * math.sin(camera.pitch)
        )
        gizmo_view = glm.lookAt(gizmo_cam_pos, glm.vec3(0,0,0), camera.world_up)
        
        gl.glLoadTransposeMatrixf(np.array(gizmo_view, dtype=np.float32).flatten())
        
        # Draw Axis with Labels
        self.draw_gizmo_axis_with_labels()
        
        gl.glPopAttrib()
        # Restore viewport not needed explicitly if we use glPushAttrib(GL_VIEWPORT_BIT) ?
        # Actually GL_VIEWPORT_BIT is for glPushAttrib... wait, GL_VIEWPORT_BIT exists in Core/Compat?
        # Yes.
        
        # Just to be safe/explicit about main storage
        gl.glViewport(0, 0, width, height)

    def draw_gizmo_axis_with_labels(self):
        gl.glLineWidth(3.0)
        gl.glBegin(gl.GL_LINES)
        
        length = 1.5
        
        # X Axis - Red
        gl.glColor3f(1.0, 0.0, 0.0)
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glVertex3f(length, 0.0, 0.0)
        
        # Y Axis - Green
        gl.glColor3f(0.0, 1.0, 0.0)
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glVertex3f(0.0, length, 0.0)
        
        # Z Axis - Blue
        gl.glColor3f(0.0, 0.0, 1.0)
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glVertex3f(0.0, 0.0, length)
        
        gl.glEnd()
        gl.glLineWidth(1.0)
        
        # Draw Labels (Lines)
        gl.glLineWidth(2.0)
        gl.glBegin(gl.GL_LINES)
        
        # X Label at (length + 0.2, 0, 0)
        gl.glColor3f(1.0, 0.0, 0.0)
        # Billboard labels are hard without quads.
        # Let's draw 3D floating letters.
        # X: / \
        # Let's simple offset
        self.draw_char_x(glm.vec3(length + 0.3, 0, 0), 0.4)
        
        # Y Label
        gl.glColor3f(0.0, 1.0, 0.0)
        self.draw_char_y(glm.vec3(0, length + 0.3, 0), 0.4)
        
        # Z Label
        gl.glColor3f(0.0, 0.0, 1.0)
        self.draw_char_z(glm.vec3(0, 0, length + 0.3), 0.4)
        
        gl.glEnd()
        gl.glLineWidth(1.0)
        
    def draw_char_x(self, center, s):
        # Draw X in 3D... somewhat facing camera? Or just 3 perpendicular crosses?
        # Let's draw a generic X shape.
        hs = s/2
        # Diagonals
        gl.glVertex3f(center.x, center.y - hs, center.z - hs)
        gl.glVertex3f(center.x, center.y + hs, center.z + hs)
        
        gl.glVertex3f(center.x, center.y - hs, center.z + hs)
        gl.glVertex3f(center.x, center.y + hs, center.z - hs)

    def draw_char_y(self, center, s):
        # Draw Y
        hs = s/2
        gl.glVertex3f(center.x - hs, center.y, center.z + hs)
        gl.glVertex3f(center.x, center.y, center.z)
        
        gl.glVertex3f(center.x + hs, center.y, center.z + hs)
        gl.glVertex3f(center.x, center.y, center.z)
        
        gl.glVertex3f(center.x, center.y, center.z)
        gl.glVertex3f(center.x, center.y, center.z - hs)

    def draw_char_z(self, center, s):
        # Draw Z
        hs = s/2
        # Top
        gl.glVertex3f(center.x - hs, center.y + hs, center.z)
        gl.glVertex3f(center.x + hs, center.y + hs, center.z)
        # Bottom
        gl.glVertex3f(center.x - hs, center.y - hs, center.z)
        gl.glVertex3f(center.x + hs, center.y - hs, center.z)
        # Diagonal
        gl.glVertex3f(center.x + hs, center.y + hs, center.z)
        gl.glVertex3f(center.x - hs, center.y - hs, center.z)

    def render_bricks(self, model, profile):
        # Draw outlines first or last? 
        # Trick: Draw filled polys with offset (pushes them back), then lines (at normal depth).
        
        gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        gl.glPolygonOffset(1.0, 1.0)
        
        # Each part is compiled once into a display list (body, studs, outlines) and only
        # recompiled when something about it changes; per frame it's one call per part.
        # Offset fill only affects filled polygons, so the outlines in the lists stay in front.
        live = {}
        for placed in model.parts.values():
            key = (placed.id, placed.part.id, placed.pos, placed.turns, placed.color)
            display_list = self._part_lists.pop(key, None)
            if display_list is None:
                display_list = self.compile_part(placed, profile)
            live[key] = display_list
            gl.glCallList(display_list)
        # Whatever is left belongs to parts that were removed or changed
        for display_list in self._part_lists.values():
            gl.glDeleteLists(display_list, 1)
        self._part_lists = live

        gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)

    def compile_part(self, placed, profile):
        stud_fill, stud_rim = self.stud_lists(profile)
        display_list = gl.glGenLists(1)
        gl.glNewList(display_list, gl.GL_COMPILE)

        rgb = profile.palette[placed.color].rgb
        gl.glColor3f(rgb.x, rgb.y, rgb.z)
        self.draw_faces(placed.solids)
        self.call_at(stud_fill, placed.studs)

        # Outlines
        gl.glDisable(gl.GL_LIGHTING)
        gl.glLineWidth(2.0)
        gl.glColor3f(0.0, 0.0, 0.0)
        self.draw_edges(placed.solids)
        gl.glLineWidth(1.0)
        self.call_at(stud_rim, placed.studs)
        gl.glEnable(gl.GL_LIGHTING)

        gl.glEndList()
        return display_list

    def render_ghost(self, profile, solids, studs, valid):
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

        # A blocked placement is drawn on top of everything, so the overlap is visible
        if not valid:
            gl.glDisable(gl.GL_DEPTH_TEST)

        if valid:
            gl.glColor4f(0.0, 1.0, 0.0, 0.5) # Semi-transparent green
        else:
            gl.glColor4f(1.0, 0.15, 0.1, 0.5) # Semi-transparent red: would overlap
        self.draw_faces(solids)
        self.call_at(self.stud_lists(profile)[0], studs)

        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDisable(gl.GL_BLEND)

    def draw_faces(self, solids):
        # Filled convex faces with their normals (for lighting)
        for solid in solids:
            for face in solid:
                n = face_normal(face)
                gl.glBegin(gl.GL_POLYGON)
                gl.glNormal3f(n.x, n.y, n.z)
                for p in face:
                    gl.glVertex3f(p.x, p.y, p.z)
                gl.glEnd()

    def draw_edges(self, solids):
        for solid in solids:
            for face in solid:
                gl.glBegin(gl.GL_LINE_LOOP)
                for p in face:
                    gl.glVertex3f(p.x, p.y, p.z)
                gl.glEnd()

    def call_at(self, display_list, positions):
        for p in positions:
            gl.glPushMatrix()
            gl.glTranslatef(p.x, p.y, p.z)
            gl.glCallList(display_list)
            gl.glPopMatrix()

    def stud_lists(self, profile):
        # Unit stud at the origin: cylinder from z=0 up to the stud height, open at the bottom
        key = (profile.stud.diameter, profile.stud.height)
        if key not in self._stud_lists:
            r, h = profile.stud.diameter / 2, profile.stud.height
            ring = [(math.cos(2 * math.pi * i / STUD_SEGMENTS), math.sin(2 * math.pi * i / STUD_SEGMENTS))
                    for i in range(STUD_SEGMENTS)]

            fill = gl.glGenLists(2)
            rim = fill + 1

            gl.glNewList(fill, gl.GL_COMPILE)
            gl.glBegin(gl.GL_QUAD_STRIP)
            for c, s in ring + ring[:1]:
                gl.glNormal3f(c, s, 0.0)
                gl.glVertex3f(r * c, r * s, 0.0)
                gl.glVertex3f(r * c, r * s, h)
            gl.glEnd()
            gl.glBegin(gl.GL_TRIANGLE_FAN)
            gl.glNormal3f(0.0, 0.0, 1.0)
            gl.glVertex3f(0.0, 0.0, h)
            for c, s in ring + ring[:1]:
                gl.glVertex3f(r * c, r * s, h)
            gl.glEnd()
            gl.glEndList()

            gl.glNewList(rim, gl.GL_COMPILE)
            gl.glBegin(gl.GL_LINE_LOOP)
            for c, s in ring:
                gl.glVertex3f(r * c, r * s, h)
            gl.glEnd()
            gl.glEndList()

            self._stud_lists[key] = (fill, rim)
        return self._stud_lists[key]

    def draw_origin_marker(self):
        # Draw a small pyramid/triangle at origin
        gl.glBegin(gl.GL_TRIANGLES)
        
        # Front face
        gl.glColor3f(1.0, 1.0, 0.0) # Yellow
        gl.glVertex3f(0.0, 0.0, 1.0)
        gl.glVertex3f(-0.5, -0.5, 0.0)
        gl.glVertex3f(0.5, -0.5, 0.0)
        
        # Right face
        gl.glColor3f(0.0, 1.0, 1.0) # Cyan
        gl.glVertex3f(0.0, 0.0, 1.0)
        gl.glVertex3f(0.5, -0.5, 0.0)
        gl.glVertex3f(0.0, 0.5, 0.0)
        
        # Back/Left faces omitted for simple debug
        
        gl.glEnd()


    def draw_grid(self, profile):
        gl.glBegin(gl.GL_LINES)
        gl.glColor3f(0.5, 0.5, 0.5)

        size = 20 # cells

        # Grid on XY plane (Z=0), lines on cell edges (cells are centered on integer indices)
        cx, cy = profile.cell.x, profile.cell.y
        offset = 0.5

        for i in range(-size, size + 1):
            val = float(i) - offset

            # Lines along Y
            gl.glVertex3f(val * cx, (-size - offset) * cy, 0.0)
            gl.glVertex3f(val * cx, (size - offset) * cy, 0.0)

            # Lines along X
            gl.glVertex3f((-size - offset) * cx, val * cy, 0.0)
            gl.glVertex3f((size - offset) * cx, val * cy, 0.0)

        gl.glEnd()

    def draw_axis(self):
        gl.glLineWidth(2.0)
        gl.glBegin(gl.GL_LINES)
        
        # X Axis - Red
        gl.glColor3f(1.0, 0.0, 0.0)
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glVertex3f(5.0, 0.0, 0.0)
        
        # Y Axis - Green
        gl.glColor3f(0.0, 1.0, 0.0)
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glVertex3f(0.0, 5.0, 0.0)
        
        # Z Axis - Blue
        gl.glColor3f(0.0, 0.0, 1.0)
        gl.glVertex3f(0.0, 0.0, 0.0)
        gl.glVertex3f(0.0, 0.0, 5.0)
        
        gl.glEnd()
        gl.glLineWidth(1.0)
