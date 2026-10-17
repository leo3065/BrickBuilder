"""BrickBuilder: a desktop app for designing Nanoblock models."""
import os

import OpenGL

# PyOpenGL checks for a GL error after every single call, which was ~90% of the time spent drawing a
# frame (1000 parts: 27 ms -> 2.6 ms without). Off unless debugging GL: BRICKBUILDER_GL_DEBUG=1.
# Must be set before anything imports OpenGL.GL, hence here.
OpenGL.ERROR_CHECKING = os.environ.get("BRICKBUILDER_GL_DEBUG") == "1"
