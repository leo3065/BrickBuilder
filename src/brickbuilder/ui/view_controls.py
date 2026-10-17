"""Camera controls beyond the mouse: preset views, orbit steps, fitting, clicking the axis gizmo.
"""
import glm
import math
from typing import Optional


class ViewControlsMixin:
    """Mixed into ui.viewport.Viewport: uses its state (model, history, camera, ...)."""

    GIZMO_SIZE, GIZMO_PADDING = 150, 10  # device pixels, as the renderer draws the axis gizmo

    def set_view(self, name: str):
        self.camera.set_view(name)
        self.refresh_ghost()

    def orbit_view(self, yaw_degrees: float, pitch_degrees: float):
        self.camera.orbit(math.radians(yaw_degrees), math.radians(pitch_degrees))
        self.refresh_ghost()

    def fit_view(self, selection_only: bool = False):
        """Home: everything in view; with `selection_only`, the selection (or everything if none)."""
        ids = self.selection if selection_only and self.selection else set(self.model.parts)
        if not ids:
            return
        boxes = [self.model.parts[pid].box for pid in ids if pid in self.model.parts]
        lo = glm.vec3(min(b[0].x for b in boxes), min(b[0].y for b in boxes), min(b[0].z for b in boxes))
        hi = glm.vec3(max(b[1].x for b in boxes), max(b[1].y for b in boxes), max(b[1].z for b in boxes))
        self.camera.fit(lo, hi)
        self.refresh_ghost()

    def _gizmo_axis_at(self, pos) -> Optional[str]:
        """Which axis label of the corner gizmo is under the cursor: "x", "y", "z" or None."""
        ratio = self.devicePixelRatio()
        size, pad = self.GIZMO_SIZE / ratio, self.GIZMO_PADDING / ratio
        left, top = self.width() - size - pad, pad
        if not (left <= pos.x() <= left + size and top <= pos.y() <= top + size):
            return None
        cam = self.camera
        eye = glm.vec3(math.cos(cam.pitch) * math.cos(cam.yaw), math.cos(cam.pitch) * math.sin(cam.yaw),
                       math.sin(cam.pitch)) * 3.0
        view = glm.lookAt(eye, glm.vec3(0), cam.world_up)
        best = None
        for name, axis in (("x", glm.vec3(1, 0, 0)), ("y", glm.vec3(0, 1, 0)), ("z", glm.vec3(0, 0, 1))):
            p = view * glm.vec4(axis * 1.8, 1.0)  # the label sits just past the axis line's end
            sx = left + (p.x / 2 + 1) / 2 * size
            sy = top + (1 - (p.y / 2 + 1) / 2) * size
            d = math.hypot(pos.x() - sx, pos.y() - sy)
            if d < 14 and (best is None or d < best[0]):
                best = (d, name)
        return best[1] if best else None
