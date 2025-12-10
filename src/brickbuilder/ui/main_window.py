from PySide6.QtWidgets import QMainWindow, QMenuBar, QMenu, QFileDialog, QMessageBox
from PySide6.QtGui import QAction, QKeySequence
from brickbuilder.ui.viewport import Viewport

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BrickBuilder")
        self.resize(1280, 720)

        self.viewport = Viewport()
        self.setCentralWidget(self.viewport)
        
        self.create_menus()

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
            self.viewport.model.clear()
            self.viewport.model.modified = False
            self.viewport.update()

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
