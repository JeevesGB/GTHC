from __future__ import annotations
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ui.design import APP_STYLE, apply_app_theme
from version import __version__


ROOT = Path(__file__).resolve().parent
# Bundled files live in sys._MEIPASS when frozen (PyInstaller), else next to this file.
RES_DIR = Path(getattr(sys, "_MEIPASS", ROOT))
ICON_PNG = RES_DIR / "ico.png"
BACKUP_GT3 = ROOT.parent / "gt3_hybrid_gui"


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GT Hybrid Creator")
        self.resize(380, 300)
        self.setFixedSize(300, 300)
        self.setStyleSheet(APP_STYLE)

        self._gt3_win = None
        self._gt4_win = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(16)

        title = self._label("GT Hybrid Creator", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        sub = self._label(
            "Choose a game. Each tool uses its own data format and window.",
            "subtitle",
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)

        card = QFrame()
        card.setObjectName("card")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(6, 6, 6, 6)
        card_l.setSpacing(10)
        card_l.addWidget(
            self._game_button(
                "Gran Turismo 3",
                "paramdb folder",
                self._open_gt3,
            )
        )
        card_l.addWidget(
            self._game_button(
                "Gran Turismo 4",
                "SpecDB folder",
                self._open_gt4,
            )
        )
        root.addWidget(card)
        root.addStretch()

        foot = QLabel(f"V{__version__}")
        foot.setStyleSheet("color: #9ca3af; font-size: 11px;")
        foot.setAlignment(Qt.AlignmentFlag.AlignLeft)
        foot.setWordWrap(True)
        root.addWidget(foot)

    @staticmethod
    def _label(text: str, obj: str = "") -> QLabel:
        lab = QLabel(text)
        if obj:
            lab.setObjectName(obj)
        lab.setWordWrap(True)
        return lab

    def _game_button(self, title: str, desc: str, slot) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("game")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        inner = QVBoxLayout(btn)
        inner.setContentsMargins(4, 2, 4, 2)
        inner.setSpacing(2)
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        t = QLabel(title)
        t.setObjectName("gameTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)

        d = QLabel(desc)
        d.setObjectName("gameDesc")
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner.addWidget(t)
        inner.addWidget(d)
        btn.clicked.connect(slot)
        return btn

    def _open_gt3(self) -> None:
        if not getattr(sys, "frozen", False):
            gt3_pkg = ROOT / "gt3"
            if (gt3_pkg / "hybrid_gui.py").is_file():
                sys.path.insert(0, str(gt3_pkg))
            elif (BACKUP_GT3 / "hybrid_gui.py").is_file():
                sys.path.insert(0, str(BACKUP_GT3))
            else:
                QMessageBox.critical(
                    self,
                    "GT3 tool missing",
                    f"Expected {gt3_pkg / 'hybrid_gui.py'}",
                )
                return

        try:
            from hybrid_gui import HybridGarage
        except Exception as e:
            QMessageBox.critical(
                self,
                "Could not load GT3 tool",
                f"{e}\n\nInstall: pip install -r {ROOT / 'requirements.txt'}",
            )
            return

        if self._gt3_win is not None and self._gt3_win.isVisible():
            self._gt3_win.raise_()
            self._gt3_win.activateWindow()
            return
        self._gt3_win = HybridGarage()
        self._gt3_win.show()

    def _open_gt4(self) -> None:
        from gt4.window import GT4HybridWindow

        if self._gt4_win is not None and self._gt4_win.isVisible():
            self._gt4_win.raise_()
            self._gt4_win.activateWindow()
            return
        self._gt4_win = GT4HybridWindow()
        self._gt4_win.show()


def main() -> int:
    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows our icon instead of python.exe's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "GTHybridCreator.GTHC"
            )
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("GT Hybrid Creator")
    app.setOrganizationName("GTHybridCreator")
    if ICON_PNG.is_file():
        app.setWindowIcon(QIcon(str(ICON_PNG)))  # every window, incl. GT3/GT4
    apply_app_theme(app)
    win = LauncherWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())