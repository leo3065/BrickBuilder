import glm
from typing import Dict

# Standard LEGO-ish colors
COLORS: Dict[str, glm.vec3] = {
    "Red": glm.vec3(0.8, 0.1, 0.1),
    "Green": glm.vec3(0.1, 0.6, 0.1),
    "Blue": glm.vec3(0.1, 0.3, 0.8),
    "Yellow": glm.vec3(0.95, 0.9, 0.1),
    "White": glm.vec3(0.95, 0.95, 0.95),
    "Black": glm.vec3(0.1, 0.1, 0.1),
    "Grey": glm.vec3(0.6, 0.6, 0.6),
    "Dark Grey": glm.vec3(0.3, 0.3, 0.3),
    "Orange": glm.vec3(0.9, 0.5, 0.1),
    "Brown": glm.vec3(0.4, 0.2, 0.1),
    "Purple": glm.vec3(0.5, 0.1, 0.6),
    "Pink": glm.vec3(0.9, 0.6, 0.7),
    "Cyan": glm.vec3(0.2, 0.8, 0.8),
    "Lime": glm.vec3(0.6, 0.8, 0.2),
}

DEFAULT_COLOR_NAME = "Red"
DEFAULT_COLOR = COLORS[DEFAULT_COLOR_NAME]
