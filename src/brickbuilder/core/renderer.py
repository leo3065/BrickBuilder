import OpenGL.GL as gl
import glm
import numpy as np
import math

class Renderer:
    def __init__(self):
        pass

    def initialize(self):
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_LIGHTING)
        gl.glEnable(gl.GL_LIGHT0)
        gl.glEnable(gl.GL_COLOR_MATERIAL)
        gl.glEnable(gl.GL_NORMALIZE)
        
        # Light position (fixed relative to camera if not transformed, or world if transformed? 
        # Light position is transformed by current ModelView when specified.
        # We can set it in render loop to be fixed relative to world/camera.

    def render(self, camera, model, ghost_position, width, height, selected_brick_pos=None, show_grid=True, show_gizmo=True, section_z=None):
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix()

        w = camera.scale * camera.aspect_ratio
        h = camera.scale
        
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        gl.glOrtho(-w/2, w/2, -h/2, h/2, camera.near_plane, camera.far_plane)
        
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
            self.draw_grid()
        gl.glEnable(gl.GL_LIGHTING)
        
        # Render Bricks
        gl.glPushMatrix()
        gl.glTranslatef(0, 0, 0.5)
        
        self.render_bricks(model)
        
        if ghost_position:
            self.render_ghost(ghost_position)
            
        if selected_brick_pos:
            self.render_selection(selected_brick_pos)
            
        gl.glPopMatrix()
        
        if section_z is not None:
            gl.glDisable(gl.GL_CLIP_PLANE0)
        
        # Draw Gizmo
        if show_gizmo:
            self.draw_orientation_gizmo(camera, width, height)

    def render_selection(self, pos):
        # Draw a wireframe box around the selected brick
        gl.glDisable(gl.GL_LIGHTING)
        gl.glDisable(gl.GL_DEPTH_TEST) # See selection through walls
        
        gl.glLineWidth(3.0)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_LINE)
        
        gl.glBegin(gl.GL_QUADS)
        gl.glColor3f(1.0, 1.0, 0.0) # Yellow
        self.draw_cube(pos.x, pos.y, pos.z)
        gl.glEnd()
        
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
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

    def render_bricks(self, model):
        # Draw outlines first or last? 
        # Trick: Draw filled polys with offset (pushes them back), then lines (at normal depth).
        
        gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        gl.glPolygonOffset(1.0, 1.0)
        
        gl.glBegin(gl.GL_QUADS)
        for brick in model.get_all_bricks():
            pos = brick.position
            gl.glColor3f(brick.color.x, brick.color.y, brick.color.z)
            self.draw_cube(pos.x, pos.y, pos.z)
        gl.glEnd()
        
        gl.glDisable(gl.GL_POLYGON_OFFSET_FILL)
        
        # Draw outlines
        gl.glDisable(gl.GL_LIGHTING)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_LINE)
        gl.glLineWidth(2.0)
        gl.glBegin(gl.GL_QUADS)
        gl.glColor3f(0.0, 0.0, 0.0)
        for brick in model.get_all_bricks():
            pos = brick.position
            self.draw_cube(pos.x, pos.y, pos.z)
        gl.glEnd()
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
        gl.glLineWidth(1.0)
        gl.glEnable(gl.GL_LIGHTING)

    def render_ghost(self, pos):
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        
        # Ghost also needs to be visible over grid/other stuff, maybe disable depth test?
        # Or just draw as is.
        
        gl.glBegin(gl.GL_QUADS)
        gl.glColor4f(0.0, 1.0, 0.0, 0.5) # Semi-transparent green
        self.draw_cube(pos.x, pos.y, pos.z)
        gl.glEnd()
        
        gl.glDisable(gl.GL_BLEND)

    def draw_cube(self, x, y, z):
        # Center at x,y,z (which are integers usually), size 1.0
        # Vertices relative to center
        r = 0.5
        
        # Top Face (z+r)
        gl.glNormal3f(0.0, 0.0, 1.0)
        gl.glVertex3f(x-r, y-r, z+r)
        gl.glVertex3f(x+r, y-r, z+r)
        gl.glVertex3f(x+r, y+r, z+r)
        gl.glVertex3f(x-r, y+r, z+r)
        
        # Bottom Face (z-r)
        gl.glNormal3f(0.0, 0.0, -1.0)
        gl.glVertex3f(x-r, y-r, z-r)
        gl.glVertex3f(x+r, y-r, z-r)
        gl.glVertex3f(x+r, y+r, z-r)
        gl.glVertex3f(x-r, y+r, z-r)
        
        # Front Face (y-r)
        gl.glNormal3f(0.0, -1.0, 0.0)
        gl.glVertex3f(x-r, y-r, z-r)
        gl.glVertex3f(x+r, y-r, z-r)
        gl.glVertex3f(x+r, y-r, z+r)
        gl.glVertex3f(x-r, y-r, z+r)
        
        # Back Face (y+r)
        gl.glNormal3f(0.0, 1.0, 0.0)
        gl.glVertex3f(x-r, y+r, z-r)
        gl.glVertex3f(x+r, y+r, z-r)
        gl.glVertex3f(x+r, y+r, z+r)
        gl.glVertex3f(x-r, y+r, z+r)
        
        # Left Face (x-r)
        gl.glNormal3f(-1.0, 0.0, 0.0)
        gl.glVertex3f(x-r, y-r, z-r)
        gl.glVertex3f(x-r, y+r, z-r)
        gl.glVertex3f(x-r, y+r, z+r)
        gl.glVertex3f(x-r, y-r, z+r)
        
        # Right Face (x+r)
        gl.glNormal3f(1.0, 0.0, 0.0)
        gl.glVertex3f(x+r, y-r, z-r)
        gl.glVertex3f(x+r, y+r, z-r)
        gl.glVertex3f(x+r, y+r, z+r)
        gl.glVertex3f(x+r, y-r, z+r)

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


    def draw_grid(self):
        gl.glBegin(gl.GL_LINES)
        gl.glColor3f(0.5, 0.5, 0.5)
        
        size = 20
        step = 1
        
        # Grid on XY plane (Z=0)
        # Shift lines by 0.5 to align with block edges (since blocks are centered at integers)
        offset = 0.5
        
        for i in range(-size, size + 1, step):
            val = float(i) - offset
            
            # Lines along Y
            gl.glVertex3f(val, float(-size) - offset, 0.0)
            gl.glVertex3f(val, float(size) - offset, 0.0)
            
            # Lines along X
            gl.glVertex3f(float(-size) - offset, val, 0.0)
            gl.glVertex3f(float(size) - offset, val, 0.0)
            
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
