import glm

class Brick:
    def __init__(self, position: glm.ivec3, color: glm.vec3):
        self.position = position
        self.color = color
