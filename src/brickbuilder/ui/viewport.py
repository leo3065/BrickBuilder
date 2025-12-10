from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QMouseEvent, QWheelEvent
import OpenGL.GL as gl
from brickbuilder.core.renderer import Renderer
from brickbuilder.core.camera import Camera

class Viewport(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = Renderer()
        self.camera = Camera()
        
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
        self.renderer.render(self.camera)

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()
        
    def mouseMoveEvent(self, event: QMouseEvent):
        if self.last_mouse_pos is None:
            return

        current_pos = event.position()
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

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self.camera.zoom(delta * 0.005)
        self.update()
