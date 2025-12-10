import glm
import math

class Camera:
    def __init__(self):
        self.target = glm.vec3(0.0, 0.0, 0.0)
        self.distance = 50.0 # Keep camera far enough back
        self.yaw = -math.pi / 4  # 45 degrees
        self.pitch = math.pi / 6 # 30 degrees
        
        # Orthographic scale (vertical size of the view in world units)
        self.scale = 20.0 
        self.aspect_ratio = 16/9
        self.near_plane = -100.0 # Ortho can see behind locally if needed, but usually 0 or negative relative to eye is fine if eye is far. 
        # But lookAt places eye at +distance. So we want near/far relative to that.
        # Let's use standard near/far.
        self.near_plane = 0.1
        self.far_plane = 500.0
        
        # Up vector for the world (Z-up)
        self.world_up = glm.vec3(0.0, 0.0, 1.0) # Z is up
        
    def get_view_matrix(self):
        x = self.distance * math.cos(self.pitch) * math.cos(self.yaw)
        y = self.distance * math.cos(self.pitch) * math.sin(self.yaw)
        z = self.distance * math.sin(self.pitch)
        
        eye = self.target + glm.vec3(x, y, z)
        return glm.lookAt(eye, self.target, self.world_up)

    def get_projection_matrix(self):
        # logical_width = self.scale * self.aspect_ratio
        # logical_height = self.scale
        
        w = self.scale * self.aspect_ratio
        h = self.scale
        
        return glm.ortho(-w/2, w/2, -h/2, h/2, self.near_plane, self.far_plane)

    def set_aspect_ratio(self, aspect):
        self.aspect_ratio = aspect

    def orbit(self, delta_yaw, delta_pitch):
        # Rotate around World Z (Yaw)
        self.yaw += delta_yaw
        
        # Rotate around Local X (Pitch)
        self.pitch += delta_pitch
        
        # Clamp pitch to avoid gimbal lock/flipping
        limit = math.pi / 2 - 0.01
        self.pitch = max(-limit, min(limit, self.pitch))

    def zoom(self, delta):
        # For ortho, zoom means changing the scale (view size)
        sensitivity = 2.0
        self.scale -= delta * sensitivity
        self.scale = max(0.1, min(self.scale, 500.0))

    def pan(self, dx, dy):
        # Calculate right and up vectors relative to camera
        view = self.get_view_matrix()
        # View matrix (row-major in memory if we just look at indices from glm if not transposed? 
        # Wait, glm objects in python are accessible [col][row].
        # view[0] is col 0 (Right vector).
        # view[1] is col 1 (Up vector).
        # view[2] is col 2 (Forward vector).
        # Since view matrix transforms World -> Eye.
        # The rows of the rotation part are the basis vectors of World expressed in Eye space?
        # Inverse of view matrix (Eye -> World) has the basis vectors of Eye expressed in World space as Columns.
        
        # Let's extract Right and Up from the inverse view matrix to move in world space relative to screen.
        inv_view = glm.inverse(view)
        
        # In GLM/OpenGL:
        # Col 0 = Right
        # Col 1 = Up
        # Col 2 = Back
        right = glm.vec3(inv_view[0])
        up = glm.vec3(inv_view[1])
        
        # Using scale for ortho panning
        self.target -= right * dx * self.scale
        self.target -= up * dy * self.scale
