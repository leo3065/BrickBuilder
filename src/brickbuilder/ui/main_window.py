from PySide6.QtWidgets import QMainWindow, QMenuBar, QMenu, QFileDialog, QMessageBox, QToolBar, QDockWidget, QWidget, QVBoxLayout, QPushButton, QGridLayout, QLabel, QDialog, QButtonGroup, QListWidget, QListWidgetItem
from PySide6.QtGui import QAction, QKeySequence, QIcon, QColor
from PySide6.QtCore import Qt, QSize
from brickbuilder.ui.viewport import Viewport
from brickbuilder.core.tools import Tool

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BrickBuilder")
        self.resize(1280, 720)

        self.viewport = Viewport()
        self.setCentralWidget(self.viewport)
        
        self.create_menus()
        self.create_toolbar()
        self.create_parts_dock()
        self.create_color_dock()
        self.update_status()

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

        # Edit Menu
        edit_menu = menu_bar.addMenu("Edit")

        rotate_action = QAction("Rotate Part", self)
        rotate_action.setShortcut("Space")
        rotate_action.triggered.connect(lambda: self.rotate_part(1))
        edit_menu.addAction(rotate_action)

        rotate_back_action = QAction("Rotate Part Back", self)
        rotate_back_action.setShortcut("Shift+Space")
        rotate_back_action.triggered.connect(lambda: self.rotate_part(-1))
        edit_menu.addAction(rotate_back_action)

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

    def create_parts_dock(self):
        dock = QDockWidget("Parts", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)

        self.parts_list = QListWidget()
        # No keyboard focus, so Space always reaches the Rotate shortcut
        self.parts_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for part in self.viewport.library.values():
            item = QListWidgetItem(part.name)
            item.setData(Qt.ItemDataRole.UserRole, part.id)
            tip = part.id if not part.ldraw else f"{part.id}  (LDraw {part.ldraw})"
            item.setToolTip(tip)
            self.parts_list.addItem(item)
            if part is self.viewport.current_part:
                self.parts_list.setCurrentItem(item)
        self.parts_list.currentItemChanged.connect(self.on_part_selected)

        dock.setWidget(self.parts_list)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def on_part_selected(self, item, _previous=None):
        if item is None:
            return
        self.viewport.set_current_part(self.viewport.library[item.data(Qt.ItemDataRole.UserRole)])
        # Picking a part means you want to place it
        self.set_tool(Tool.PLACE, self.place_action)
        self.update_status()

    def rotate_part(self, quarter_turns: int):
        self.viewport.rotate_current_part(quarter_turns)
        self.update_status()

    def update_status(self):
        part = self.viewport.current_part
        self.statusBar().showMessage(f"{part.name}  ·  rotated {self.viewport.current_turns * 90}°   (Space / Shift+Space to rotate)")

    def create_color_dock(self):
        dock = QDockWidget("Colors", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        
        widget = QWidget()
        # Set dark background for the container to act as the "inner border" color when using padding+clip
        widget.setStyleSheet("background-color: #222222;") 
        layout = QGridLayout(widget)
        
        row = 0
        col = 0
        cols_per_row = 5 # the Nanoblock palette has 45 colors

        self.color_buttons = {}
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)

        for color in self.viewport.profile.palette.values():
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCheckable(True)
            # No keyboard focus, so Space rotates instead of clicking the focused swatch
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            # Convert glm to CSS color
            r = int(color.rgb.x * 255)
            g = int(color.rgb.y * 255)
            b = int(color.rgb.z * 255)
            fill = f"rgb({r}, {g}, {b})"
            if color.clear:
                # Clear (translucent) colors: diagonal split, solid top-left and see-through
                # bottom-right (the dark dock background shows through)
                fill = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                        f"stop:0 rgb({r}, {g}, {b}), stop:0.5 rgb({r}, {g}, {b}), "
                        f"stop:0.501 rgba({r}, {g}, {b}, 70), stop:1 rgba({r}, {g}, {b}, 70))")

            # Unchecked: Simple 1px black border
            # Checked: Cyan outer border, transparent padding (revealing dark bg -> inner border effect), content
            style = f"""
                QPushButton {{
                    background: {fill};
                    border: 1px solid black;
                    border-radius: 0px;
                }}
                QPushButton:checked {{
                    background: {fill};
                    border: 2px solid #00FFFF; /* Cyan Outer */
                    padding: 3px;              /* Thickness of "Inner" (gap) */
                    background-clip: content-box;
                }}
            """
            btn.setStyleSheet(style)
            btn.setToolTip(color.name)

            # Connect click to set active color
            btn.clicked.connect(lambda _, c=color.id: self.set_active_color(c))

            self.color_group.addButton(btn)
            self.color_buttons[color.id] = btn
            
            layout.addWidget(btn, row, col)
            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1
                
        layout.setRowStretch(row + 1, 1) # Push to top
        dock.setWidget(widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        
        # Select default
        self.set_active_color(self.viewport.current_color)

    def set_active_color(self, color_id: str):
        self.viewport.set_current_color(color_id)

        # QButtonGroup handles the exclusivity and checking state visually via stylesheet
        # We just need to ensure the correct button is checked if set programmatically
        if color_id in self.color_buttons:
            self.color_buttons[color_id].setChecked(True)

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
        - Place (Q): Left Click to place the part chosen in the Parts list.<br>
          Space / Shift+Space rotates it. Red preview = it would overlap.<br>
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
                self.viewport.model_replaced()
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
