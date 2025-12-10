import OpenGL.GL as gl
import glm
import numpy as np

class Renderer:
    def __init__(self):
        pass

    def initialize(self):
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glEnable(gl.GL_DEPTH_TEST)

    def render(self, camera):
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix()
        
        # Debug: Print camera info occasionally
        if not hasattr(self, 'frame_count'):
            self.frame_count = 0
        self.frame_count += 1
        
        if self.frame_count % 100 == 0:
            print(f"Camera distance: {camera.distance}")
            print(f"Camera pitch: {camera.pitch}, yaw: {camera.yaw}")
            # Print diagonal of projection matrix to deduce FOV state
            # proj[0][0] = f / aspect
            # proj[1][1] = f  (where f = cot(fov/2))
            p = np.array(proj).flatten()
            print(f"Proj[0][0]: {p[0]}, Proj[1][1]: {p[5]}")
        
        # GLM is column-major. np.array(glm_mat) yields [[col0], [col1]...].
        # However, it seems when converting to numpy 4x4, we get rows consistent with C-order.
        # OpenGL expects Column-Major flat list.
        # If we have rows, we need to transpose to get columns.
        # This fixes the "perspective distortion in ortho" (translation ending up in W).
        
        w = camera.scale * camera.aspect_ratio
        h = camera.scale
        
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        # Left, Right, Bottom, Top, Near, Far
        # Camera near/far are positive distances from eye. glOrtho uses Z values. 
        # In Camera space, looking down -Z. 
        # But glOrtho standard maps zNear/zFar to -1, 1 depth.
        # Let's simple use glOrtho directly.
        gl.glOrtho(-w/2, w/2, -h/2, h/2, camera.near_plane, camera.far_plane)
        
        gl.glMatrixMode(gl.GL_MODELVIEW)
        # Use Transpose load which expects Row-Major data (what numpy gives us naturally)
        gl.glLoadTransposeMatrixf(np.array(view, dtype=np.float32).flatten())
        
        self.draw_grid()
        self.draw_origin_marker()
        self.draw_axis()

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
        for i in range(-size, size + 1, step):
            gl.glVertex3f(float(i), float(-size), 0.0)
            gl.glVertex3f(float(i), float(size), 0.0)
            
            gl.glVertex3f(float(-size), float(i), 0.0)
            gl.glVertex3f(float(size), float(i), 0.0)
            
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
