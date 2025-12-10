import glm
import math
from typing import Optional, Tuple
from brickbuilder.core.camera import Camera
from brickbuilder.core.model import Model

class Ray:
    def __init__(self, origin: glm.vec3, direction: glm.vec3):
        self.origin = origin
        self.direction = glm.normalize(direction)

def get_mouse_ray(mouse_x: float, mouse_y: float, width: float, height: float, camera: Camera) -> Ray:
    # Normalized Device Coordinates (NDC)
    # x: -1 to 1, y: -1 to 1
    ndc_x = (2.0 * mouse_x) / width - 1.0
    ndc_y = 1.0 - (2.0 * mouse_y) / height # Flip Y
    
    # Clip coordinates
    clip_coords = glm.vec4(ndc_x, ndc_y, -1.0, 1.0)
    
    # Inverse Projection
    inv_proj = glm.inverse(camera.get_projection_matrix())
    eye_coords = inv_proj * clip_coords
    
    # Inverse View
    inv_view = glm.inverse(camera.get_view_matrix())
    
    # For Orthographic:
    # Ray direction is the Camera's Forward vector (negative Z axis of View Space).
    # Ray origin depends on the screen coordinate.
    
    # The world space position of the "mouse on near plane":
    # (ndc_x, ndc_y, -1, 1) transformed by inv(Proj * View)
    
    # Let's do it fully with matrices which handles both Ortho and Persp generic cases usually.
    # World position of near plane point
    inv_prod = glm.inverse(camera.get_projection_matrix() * camera.get_view_matrix())
    
    # Near point (z = -1 in NDC)
    near_point_ndc = glm.vec4(ndc_x, ndc_y, -1.0, 1.0)
    world_near = inv_prod * near_point_ndc
    world_near /= world_near.w
    
    # Far point (z = 1 in NDC)
    far_point_ndc = glm.vec4(ndc_x, ndc_y, 1.0, 1.0)
    world_far = inv_prod * far_point_ndc
    world_far /= world_far.w
    
    origin = glm.vec3(world_near)
    direction = glm.vec3(world_far) - origin
    
    return Ray(origin, direction)

def intersect_plane(ray: Ray, plane_normal: glm.vec3, plane_point: glm.vec3) -> Optional[float]:
    denom = glm.dot(ray.direction, plane_normal)
    if abs(denom) > 1e-6:
        t = glm.dot(plane_point - ray.origin, plane_normal) / denom
        if t >= 0:
            return t
    return None

def intersect_aabb(ray: Ray, box_min: glm.vec3, box_max: glm.vec3) -> Optional[Tuple[float, glm.vec3]]:
    # Slab method
    t_min = 0.0
    t_max = 100000.0
    
    pos = ray.origin
    d = ray.direction
    
    normal = glm.vec3(0)
    
    # X Axis
    if abs(d.x) < 1e-6:
        if pos.x < box_min.x or pos.x > box_max.x:
            return None
    else:
        odo = 1.0 / d.x
        t1 = (box_min.x - pos.x) * odo
        t2 = (box_max.x - pos.x) * odo
        
        if t1 > t2:
            t1, t2 = t2, t1
            
        if t1 > t_min:
            t_min = t1
            normal = glm.vec3(-1, 0, 0) if d.x > 0 else glm.vec3(1, 0, 0)
        
        t_max = min(t_max, t2)
        
        if t_min > t_max:
             return None

    # Y Axis
    if abs(d.y) < 1e-6:
        if pos.y < box_min.y or pos.y > box_max.y:
            return None
    else:
        odo = 1.0 / d.y
        t1 = (box_min.y - pos.y) * odo
        t2 = (box_max.y - pos.y) * odo
        
        if t1 > t2:
            t1, t2 = t2, t1
            
        if t1 > t_min:
            t_min = t1
            normal = glm.vec3(0, -1, 0) if d.y > 0 else glm.vec3(0, 1, 0)
            
        t_max = min(t_max, t2)
        
        if t_min > t_max:
             return None
             
    # Z Axis
    if abs(d.z) < 1e-6:
        if pos.z < box_min.z or pos.z > box_max.z:
            return None
    else:
        odo = 1.0 / d.z
        t1 = (box_min.z - pos.z) * odo
        t2 = (box_max.z - pos.z) * odo
        
        if t1 > t2:
            t1, t2 = t2, t1
            
        if t1 > t_min:
            t_min = t1
            normal = glm.vec3(0, 0, -1) if d.z > 0 else glm.vec3(0, 0, 1) # Normal is roughly right but we can refine logic if needed
            
        t_max = min(t_max, t2)
        
        if t_min > t_max:
             return None

    return t_min, normal

def intersect_model(ray: Ray, model: Model) -> Tuple[Optional[glm.ivec3], Optional[glm.vec3], Optional[glm.ivec3]]:
    # Returns (intersected_brick_pos, intersection_normal, neighbor_pos)
    closest_t = 100000.0
    hit_brick = None
    hit_normal = None
    
    # Optimization: Grid traversal is better, but iterating all bricks is okay for start < 1000 bricks
    for brick in model.get_all_bricks():
        # AABB: Brick is at brick.position (integer), size 1x1x1
        # Renderer shifts bricks by (0, 0, 0.5), so the visual center is at z+0.5.
        # This means the vertical range is [z, z+1].
        # X and Y are still centered at integer coordinates: [x-0.5, x+0.5].
        
        pos = glm.vec3(brick.position)
        box_min = pos + glm.vec3(-0.5, -0.5, 0.0)
        box_max = pos + glm.vec3(0.5, 0.5, 1.0)
        
        result = intersect_aabb(ray, box_min, box_max)
        if result:
            t, normal = result
            if t < closest_t:
                closest_t = t
                hit_brick = brick
                hit_normal = normal
                
    if hit_brick:
        # Determine neighbor pos
        # normal should be mostly axis aligned
        # e.g. (1, 0, 0) -> neighbor is pos + (1, 0, 0)
        
        # Snap normal to grid integer
        nx, ny, nz = 0, 0, 0
        if abs(hit_normal.x) > 0.9: nx = int(math.copysign(1, hit_normal.x))
        if abs(hit_normal.y) > 0.9: ny = int(math.copysign(1, hit_normal.y))
        if abs(hit_normal.z) > 0.9: nz = int(math.copysign(1, hit_normal.z))
        
        neighbor_pos = hit_brick.position + glm.ivec3(nx, ny, nz)
        
        return hit_brick.position, hit_normal, neighbor_pos
        
    return None, None, None
