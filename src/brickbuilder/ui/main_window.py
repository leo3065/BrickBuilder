from PySide6.QtWidgets import QMainWindow, QMenuBar, QMenu, QFileDialog, QMessageBox, QToolBar, QDockWidget, QWidget, QVBoxLayout, QPushButton, QGridLayout, QLabel, QDialog, QButtonGroup
from PySide6.QtGui import QAction, QKeySequence, QIcon, QColor
from PySide6.QtCore import Qt, QSize
from brickbuilder.ui.viewport import Viewport
from brickbuilder.core.tools import Tool
from brickbuilder.core.colors import COLORS, DEFAULT_COLOR

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BrickBuilder")
        self.resize(1280, 720)

        self.viewport = Viewport()
        self.setCentralWidget(self.viewport)
        
        self.create_menus()
        self.create_toolbar()
        self.create_color_dock()

    def create_menus(self) -> None:
        menu_bar = self.menuBar()
        
        # File Menu
        file_menu = menu_bar.addMenu("File")
        
        # New
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)
        
        # Open
        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        # Save
        save_action = QAction("Save As...", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)
        
        # Help Menu
        help_menu = menu_bar.addMenu("Help")
        help_action = QAction("Controls", self)
        help_action.setShortcut(QKeySequence.HelpContents)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

    def create_toolbar(self):
        toolbar = QToolBar("Tools")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        
        # Place Tool
        place_action = QAction("Place", self)
        place_action.setCheckable(True)
        place_action.setChecked(True)
        place_action.setShortcut("Q")
        place_action.triggered.connect(lambda: self.set_tool(Tool.PLACE, place_action))
        toolbar.addAction(place_action)
        self.place_action = place_action
        
        # Select Tool
        select_action = QAction("Select", self)
        select_action.setCheckable(True)
        select_action.setShortcut("W")
        select_action.triggered.connect(lambda: self.set_tool(Tool.SELECT, select_action))
        toolbar.addAction(select_action)
        self.select_action = select_action
        
        # Paint Tool
        paint_action = QAction("Paint", self)
        paint_action.setCheckable(True)
        paint_action.setShortcut("E")
        paint_action.triggered.connect(lambda: self.set_tool(Tool.PAINT, paint_action))
        toolbar.addAction(paint_action)
        self.paint_action = paint_action
        
        # Erase Tool
        erase_action = QAction("Erase", self)
        erase_action.setCheckable(True)
        erase_action.setShortcut("R")
        erase_action.triggered.connect(lambda: self.set_tool(Tool.ERASE, erase_action))
        toolbar.addAction(erase_action)
        self.erase_action = erase_action

    def set_tool(self, tool: Tool, action: QAction):
        # Uncheck others
        for a in [self.place_action, self.select_action, self.paint_action, self.erase_action]:
            if a != action:
                a.setChecked(False)
        action.setChecked(True) # Ensure clicked is checked
        self.viewport.set_tool(tool)

    def create_color_dock(self):
        dock = QDockWidget("Colors", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        
        widget = QWidget()
        # Set dark background for the container to act as the "inner border" color when using padding+clip
        widget.setStyleSheet("background-color: #222222;") 
        layout = QGridLayout(widget)
        
        row = 0
        col = 0
        cols_per_row = 2
        
        self.color_buttons = {}
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        
        for name, color in COLORS.items():
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setCheckable(True)
            
            # Convert glm to CSS color
            r = int(color.x * 255)
            g = int(color.y * 255)
            b = int(color.z * 255)
            
            # Unchecked: Simple 1px black border
            # Checked: Cyan outer border, transparent padding (revealing dark bg -> inner border effect), content
            style = f"""
                QPushButton {{
                    background-color: rgb({r}, {g}, {b});
                    border: 1px solid black;
                    border-radius: 0px;
                }}
                QPushButton:checked {{
                    background-color: rgb({r}, {g}, {b});
                    border: 2px solid #00FFFF; /* Cyan Outer */
                    padding: 4px;              /* Thickness of "Inner" (gap) */
                    background-clip: content-box; 
                }}
            """
            btn.setStyleSheet(style)
            btn.setToolTip(name)
            
            # Connect click to set active color
            btn.clicked.connect(lambda _, c=color: self.set_active_color(c))
            
            self.color_group.addButton(btn)
            self.color_buttons[tuple(color)] = btn
            
            layout.addWidget(btn, row, col)
            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1
                
        layout.setRowStretch(row + 1, 1) # Push to top
        dock.setWidget(widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        
        # Select default
        self.set_active_color(DEFAULT_COLOR)

    def set_active_color(self, color):
        self.viewport.set_current_color(color)
        
        # QButtonGroup handles the exclusivity and checking state visually via stylesheet
        # We just need to ensure the correct button is checked if set programmatically
        c_tuple = tuple(color)
        if c_tuple in self.color_buttons:
            self.color_buttons[c_tuple].setChecked(True)

    def show_help(self):
        d = QDialog(self)
        d.setWindowTitle("BrickBuilder Controls")
        layout = QVBoxLayout(d)
        
        controls = """
        <b>Camera:</b><br>
        - Orbit: Middle Mouse (or Alt + Left)<br>
        - Pan: Shift + Middle Mouse (or Shift + Alt + Left)<br>
        - Zoom: Scroll Wheel<br>
        <br>
        <b>Tools:</b><br>
        - Place (Q): Left Click to place brick.<br>
          (Ctrl + Left Click removes in Place mode)<br>
        - Select (W): Click to select brick.<br>
        - Paint (E): Click to color brick.<br>
        - Erase (R): Click to remove brick.<br>
        """
        
        lbl = QLabel(controls)
        layout.addWidget(lbl)
        
        btn = QPushButton("OK")
        btn.clicked.connect(d.accept)
        layout.addWidget(btn)
        
        d.exec()

    def check_unsaved_changes(self) -> bool:
        if self.viewport.model.modified:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("The document has been modified.")
            msg.setInformativeText("Do you want to save your changes?")
            msg.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Save)
            ret = msg.exec()
            
            if ret == QMessageBox.Save:
                return self.save_file()
            elif ret == QMessageBox.Cancel:
                return False
        return True

    def new_file(self) -> None:
        if self.check_unsaved_changes():
            self.viewport.reset_scene()
            self.viewport.model.modified = False

    def open_file(self) -> None:
        if not self.check_unsaved_changes():
            return
            
        filename, _ = QFileDialog.getOpenFileName(self, "Open Model", "", "JSON Files (*.json)")
        if filename:
            try:
                self.viewport.model.load_from_file(filename)
                self.viewport.update()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load file:\n{e}")

    def save_file(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(self, "Save Model", "", "JSON Files (*.json)")
        if filename:
            try:
                self.viewport.model.save_to_file(filename)
                return True
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
                return False
        return False
