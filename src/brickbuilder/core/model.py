from typing import Dict, Optional, Tuple
import glm
from brickbuilder.core.brick import Brick

class Model:
    def __init__(self):
        # Store bricks in a dict keyed by position tuple for O(1) lookup
        # key: (x, y, z), value: Brick
        self.bricks: Dict[Tuple[int, int, int], Brick] = {}

    def add_brick(self, position: glm.ivec3, color: glm.vec3) -> None:
        key = (position.x, position.y, position.z)
        if key not in self.bricks:
            self.bricks[key] = Brick(position, color)

    def remove_brick(self, position: glm.ivec3) -> None:
        key = (position.x, position.y, position.z)
        if key in self.bricks:
            del self.bricks[key]

    def get_brick(self, position: glm.ivec3) -> Optional[Brick]:
        key = (position.x, position.y, position.z)
        return self.bricks.get(key)
    
    def get_all_bricks(self):
        return self.bricks.values()
