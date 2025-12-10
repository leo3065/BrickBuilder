from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QMouseEvent, QWheelEvent
import OpenGL.GL as gl
import glm
from typing import Optional
from brickbuilder.core.renderer import Renderer
from brickbuilder.core.camera import Camera
from brickbuilder.core.model import Model
from brickbuilder.core import picking
from brickbuilder.core.tools import Tool
from brickbuilder.core.colors import COLORS, DEFAULT_COLOR

class Viewport(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = Renderer()
        self.camera = Camera()
        self.model = Model()
        
        self.current_tool = Tool.PLACE
        self.current_color = DEFAULT_COLOR
        
        self.ghost_position: Optional[glm.ivec3] = None
        self.ghost_color = glm.vec3(0.0, 1.0, 0.0) # Green ghost
        
        self.selected_brick_pos: Optional[glm.ivec3] = None
        
        # Enable mouse tracking for hover effects if needed later
        self.setMouseTracking(True)
        
        # Timer for continuous update if needed (or just update on events)
        # For smooth camera, might need timer or requestUpdate
        
        self.last_mouse_pos = None

    def initializeGL(self):
        self.renderer.initialize()

    def resizeGL(self, w, h):
        self.camera.set_aspect_ratio(w / h)
        gl.glViewport(0, 0, w, h)

    def paintGL(self):
        pixel_ratio = self.devicePixelRatio()
        self.renderer.render(self.camera, self.model, self.ghost_position, int(self.width() * pixel_ratio), int(self.height() * pixel_ratio), self.selected_brick_pos)

    def set_tool(self, tool: Tool):
        self.current_tool = tool
        self.ghost_position = None
        self.selected_brick_pos = None
        self.update()

    def reset_scene(self):
        self.model.clear()
        self.camera.reset()
        self.ghost_position = None
        self.selected_brick_pos = None
        self.update()

    def set_current_color(self, color: glm.vec3):
        self.current_color = color
        # If in Paint mode and something selected, paint it?
        if self.current_tool == Tool.SELECT and self.selected_brick_pos:
             pass

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()
        
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle_left_click(event)
            self.update()

    def _handle_left_click(self, event: QMouseEvent):
        ray = picking.get_mouse_ray(event.position().x(), event.position().y(), self.width(), self.height(), self.camera)

        if self.current_tool == Tool.PLACE:
            self._handle_place_tool(event, ray)
        elif self.current_tool == Tool.SELECT:
            self._handle_select_tool(ray)
        elif self.current_tool == Tool.PAINT:
            self._handle_paint_tool(ray)
        elif self.current_tool == Tool.ERASE:
            self._handle_erase_tool(ray)

    def _handle_place_tool(self, event: QMouseEvent, ray):
        if self.ghost_position:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                 # Quick erase override in Place mode
                hit_pos, _, _ = picking.intersect_model(ray, self.model)
                if hit_pos:
                   self.model.remove_brick(hit_pos)
            else:
                self.model.add_brick(self.ghost_position, self.current_color)
                # Refresh ghost immediately
                self.update_ghost(event.position().x(), event.position().y())

    def _handle_select_tool(self, ray):
        hit_pos, _, _ = picking.intersect_model(ray, self.model)
        self.selected_brick_pos = hit_pos

    def _handle_paint_tool(self, ray):
        hit_pos, _, _ = picking.intersect_model(ray, self.model)
        if hit_pos:
            brick = self.model.get_brick(hit_pos)
            if brick:
                brick.color = self.current_color
                self.model.modified = True

    def _handle_erase_tool(self, ray):
        hit_pos, _, _ = picking.intersect_model(ray, self.model)
        if hit_pos:
            self.model.remove_brick(hit_pos)

    def mouseMoveEvent(self, event: QMouseEvent):
        current_pos = event.position()
        
        # Tool-specific hover logic
        if self.current_tool == Tool.PLACE:
             self.update_ghost(current_pos.x(), current_pos.y())
        else:
            self.ghost_position = None

        if self.last_mouse_pos is not None:
             # Navigation stays same
            delta = current_pos - self.last_mouse_pos
            self.last_mouse_pos = current_pos

            if event.buttons() & Qt.MouseButton.MiddleButton:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Pan
                    sensitivity = 0.005
                    self.camera.pan(delta.x() * sensitivity, -delta.y() * sensitivity)
                else:
                    # Rotate
                    sensitivity = 0.01
                    self.camera.orbit(-delta.x() * sensitivity, -delta.y() * sensitivity)
        
        self.update()

    def update_ghost(self, mouse_x, mouse_y):
        ray = picking.get_mouse_ray(mouse_x, mouse_y, self.width(), self.height(), self.camera)
        
        # Check model intersection first
        hit_pos, normal, neighbor = picking.intersect_model(ray, self.model)
        
        if neighbor:
            # Snap to neighbor
            self.ghost_position = neighbor
        elif ray.direction.z < -1e-6:
            # Check ground plane (Z=0) intersection ONLY if looking down
            # Normal (0,0,1), Point (0,0,0)
            t = picking.intersect_plane(ray, glm.vec3(0, 0, 1), glm.vec3(0, 0, 0))
            if t:
                hit_point = ray.origin + ray.direction * t
                # Round to nearest int
                x = round(hit_point.x)
                y = round(hit_point.y)
                # Z should be 0, but for brick center Z=0 means it goes from -0.5 to 0.5. 
                # If we want it ON the grid, center Z=0.5.
                # Let's assume Grid is at Z=0, and Bricks sit ON TOP.
                # So first layer center Z=0.5 (index 0?)
                # If grid is visual guide at Z=0. 
                # Let's say brick index (x,y,z) is center (x, y, z+0.5).
                # Wait, earlier I said center at integer coordinates.
                # If grid is Z=0, and we want bricks on top, then index Z=0 should mean center Z=0.5 visually?
                # Or we just use Z=0 as center, so it sinks half way.
                # User requirement: "placed on the face of the selected block, or on the grid".
                # Usually on grid means sitting on it.
                # So Z index 0 center = (x, y, 0.5).
                
                # Let's adjust rendering later. For now logic: index 0.
                self.ghost_position = glm.ivec3(x, y, 0)
            else:
                self.ghost_position = None
        else:
            self.ghost_position = None


    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self.camera.zoom(delta * 0.005)
        self.update()
