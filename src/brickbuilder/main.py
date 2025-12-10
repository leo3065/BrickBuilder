import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QSurfaceFormat
from brickbuilder.ui.main_window import MainWindow

def main():
    format = QSurfaceFormat()
    format.setProfile(QSurfaceFormat.CompatibilityProfile)
    format.setVersion(2, 1)
    QSurfaceFormat.setDefaultFormat(format)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
