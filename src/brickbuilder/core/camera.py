import glm
import math

# Preset views as (yaw, pitch) in degrees. Yaw is where the eye is around the target (0 = on +X),
# pitch how high (90 = straight above). Top and bottom keep +Y up on screen.
VIEWS = {
    "front": (-90.0, 0.0),    # from -Y, looking toward +Y
    "back": (90.0, 0.0),
    "right": (0.0, 0.0),      # from +X
    "left": (180.0, 0.0),
    "top": (-90.0, 90.0),
    "bottom": (-90.0, -90.0),
    "isometric": (-45.0, math.degrees(math.atan(1 / math.sqrt(2)))),  # equal angles to all three axes
}
PITCH_LIMIT = math.pi / 2 - 0.01  # straight up or down would leave "up" undefined


class Camera:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.target = glm.vec3(0.0, 0.0, 0.0)
        # World units are mm. Orthographic, so distance only needs to keep the model
        # in front of the near plane.
        self.distance = 1000.0
        self.yaw = -math.pi / 4  # 45 degrees
        self.pitch = math.pi / 6 # 30 degrees
        self.scale = 80.0 # visible height in mm
        
        # Up vector for the world (Z-up)
        self.world_up = glm.vec3(0.0, 0.0, 1.0) # Z is up
        
        self.aspect_ratio = 16/9
        self.near_plane = 0.1
        self.far_plane = 5000.0
        
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
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch))

    def set_view(self, name: str):
        """Look from one of the preset directions (VIEWS), keeping the target and zoom."""
        yaw, pitch = VIEWS[name]
        self.yaw = math.radians(yaw)
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, math.radians(pitch)))

    def is_view(self, name: str) -> bool:
        yaw, pitch = VIEWS[name]
        p = max(-PITCH_LIMIT, min(PITCH_LIMIT, math.radians(pitch)))
        dyaw = (self.yaw - math.radians(yaw) + math.pi) % (2 * math.pi) - math.pi
        return abs(dyaw) < 1e-6 and abs(self.pitch - p) < 1e-6

    def fit(self, lo: glm.vec3, hi: glm.vec3, margin: float = 1.2):
        """Centre on a box and zoom so it fills the view (with a margin)."""
        self.target = (lo + hi) * 0.5
        view = self.get_view_matrix()
        xs, ys = [], []
        for x in (lo.x, hi.x):
            for y in (lo.y, hi.y):
                for z in (lo.z, hi.z):
                    p = view * glm.vec4(x, y, z, 1.0)
                    xs.append(p.x)
                    ys.append(p.y)
        height = max(max(ys) - min(ys), (max(xs) - min(xs)) / self.aspect_ratio)
        self.scale = max(10.0, min(height * margin, 2000.0))

    def zoom(self, delta):
        # For ortho, zoom means changing the scale (view size).
        # Multiplicative, so each wheel notch feels the same at any zoom level.
        self.scale *= math.exp(-delta * 0.2)
        self.scale = max(1.0, min(self.scale, 2000.0))

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
