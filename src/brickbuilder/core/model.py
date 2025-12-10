from typing import Dict, Optional, Tuple, List, Any
import glm
import json
from brickbuilder.core.brick import Brick

class Model:
    def __init__(self) -> None:
        # Store bricks in a dict keyed by position tuple for O(1) lookup
        # key: (x, y, z), value: Brick
        self.bricks: Dict[Tuple[int, int, int], Brick] = {}
        self.modified = False

    def add_brick(self, position: glm.ivec3, color: glm.vec3) -> None:
        key = (position.x, position.y, position.z)
        if key not in self.bricks:
            self.bricks[key] = Brick(position, color)
            self.modified = True

    def remove_brick(self, position: glm.ivec3) -> None:
        key = (position.x, position.y, position.z)
        if key in self.bricks:
            del self.bricks[key]
            self.modified = True

    def get_brick(self, position: glm.ivec3) -> Optional[Brick]:
        key = (position.x, position.y, position.z)
        return self.bricks.get(key)
    
    def get_all_bricks(self) -> Any:
        # Returns dict_values, typehint as Any or Collection[Brick]
        return self.bricks.values()

    def clear(self) -> None:
        self.bricks.clear()
        self.modified = True # Clearing makes it modified relative to previous state? 
        # Usually New -> Clears -> Modified=False (fresh state). 
        # But if we call clear() blindly it modifies. 
        # Application logic should reset modified after "New" action.

    def to_dict(self) -> Dict[str, Any]:
        brick_list: List[Dict[str, Any]] = []
        for brick in self.bricks.values():
            brick_data = {
                "x": brick.position.x,
                "y": brick.position.y,
                "z": brick.position.z,
                "r": brick.color.x,
                "g": brick.color.y,
                "b": brick.color.z
            }
            brick_list.append(brick_data)
        
        return {
            "version": 1,
            "bricks": brick_list
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        self.clear()
        if "bricks" in data:
            for b_data in data["bricks"]:
                pos = glm.ivec3(b_data["x"], b_data["y"], b_data["z"])
                col = glm.vec3(b_data["r"], b_data["g"], b_data["b"])
                # Bypass add_brick to avoid setting modified=True for every brick?
                # Or just reset at end.
                key = (pos.x, pos.y, pos.z)
                self.bricks[key] = Brick(pos, col)
        self.modified = False # Loaded state is clean

    def save_to_file(self, filename: str) -> None:
        data = self.to_dict()
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        self.modified = False

    def load_from_file(self, filename: str) -> None:
        with open(filename, 'r') as f:
            data = json.load(f)
        self.from_dict(data)
