from PySide6.QtWidgets import QMainWindow
from brickbuilder.ui.viewport import Viewport

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrickBuilder")
        self.resize(1280, 720)

        self.viewport = Viewport()
        self.setCentralWidget(self.viewport)
