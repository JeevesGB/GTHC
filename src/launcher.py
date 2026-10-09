from __future__ import annotations
import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,QFrame,
    QHBoxLayout,QLabel,
    QMainWindow,QMessageBox,
    QPushButton,QVBoxLayout,
    QWidget,
)
from ui.design import APP_STYLE, apply_app_theme
from ui.folder_paths import get_folder, get_last_game, set_last_game
from version import __version__
ROOT = Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", ROOT))
ICON_PNG = RES_DIR / "ico.png"
GT3_LOGO = RES_DIR / "gt3" / "gt3.png"
GT4_LOGO = RES_DIR / "gt4" / "gt4.png"
BACKUP_GT3 = ROOT.parent / "gt3_hybrid_gui"

SHOW_CAR_CREATOR = True #False # Set True to activate button


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GT Hybrid Creator")
        # WIDTH, HEIGHT (shorter when the Car Creator button is hidden)
        self.setFixedSize(350, 430 if SHOW_CAR_CREATOR else 358)
        self.setStyleSheet(APP_STYLE)

        self._gt3_win = None
        self._gt4_win = None
        self._creator_win = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 8)
        root.setSpacing(8)

        icon_lab = QLabel()
        icon_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if ICON_PNG.is_file():
            pix = QPixmap(str(ICON_PNG))
            if not pix.isNull():
                icon_lab.setPixmap(
                    pix.scaled(
                        72,
                        72,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        root.addWidget(icon_lab)

        sub = self._label(
            "Choose a game. Each tool uses its own data format and window.",
            "subtitle",
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)

        card = QFrame()
        card.setObjectName("card")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(8, 8, 8, 8)
        card_l.setSpacing(8)

        gt3_folder = get_folder("gt3")
        gt4_folder = get_folder("gt4")
        card_l.addWidget(
            self._game_button(
                GT3_LOGO,
                "Gran Turismo 3",
                self._folder_hint(gt3_folder, "paramdb folder"),
                self._open_gt3,
            )
        )
        card_l.addWidget(
            self._game_button(
                GT4_LOGO,
                "Gran Turismo 4",
                self._folder_hint(gt4_folder, "SpecDB folder"),
                self._open_gt4,
            )
        )
        if SHOW_CAR_CREATOR:
            card_l.addWidget(
                self._game_button(
                    ICON_PNG,
                    "Car Creator",
                    "Clone cars · dyno · gearbox",
                    self._open_creator,
                )
            )
        root.addWidget(card)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        ver = QLabel(f"V{__version__}")
        ver.setStyleSheet("color: #9ca3af; font-size: 11px;")
        foot.addWidget(ver)
        foot.addStretch()
        root.addLayout(foot)

        last = get_last_game()
        if last == "gt3":
            self.statusBar().showMessage("Last opened: Gran Turismo 3", 3000)
        elif last == "gt4":
            self.statusBar().showMessage("Last opened: Gran Turismo 4", 3000)

    @staticmethod
    def _folder_hint(path, fallback: str) -> str:
        if path is None:
            return fallback
        name = path.name
        return name if len(name) <= 28 else name[:25] + "…"

    @staticmethod
    def _label(text: str, obj: str = "") -> QLabel:
        lab = QLabel(text)
        if obj:
            lab.setObjectName(obj)
        lab.setWordWrap(True)
        return lab

    def _game_button(
        self,
        logo_path: Path,
        title: str,
        desc: str,
        slot,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("game")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(64)
        btn.setToolTip(f"{title}\n{desc}")
        btn.setAccessibleName(title)

        layout = QVBoxLayout(btn)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background: transparent;")
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if logo_path.is_file():
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                logo.setPixmap(
                    pix.scaled(
                        200,
                        48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        elif ICON_PNG.is_file():
            pix = QPixmap(str(ICON_PNG))
            if not pix.isNull():
                logo.setPixmap(
                    pix.scaled(
                        40,
                        40,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        layout.addWidget(logo)

        btn.clicked.connect(slot)
        return btn

    def _open_gt3(self) -> None:
        set_last_game("gt3")
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
            from gt3.hybrid_gui import HybridGarage
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
        set_last_game("gt4")
        from gt4.window import GT4HybridWindow

        if self._gt4_win is not None and self._gt4_win.isVisible():
            self._gt4_win.raise_()
            self._gt4_win.activateWindow()
            return
        self._gt4_win = GT4HybridWindow()
        self._gt4_win.show()



    def _open_creator(self) -> None:
        try:
            from car_creator.window import CarCreatorWindow
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self,
                "Could not load Car Creator",
                f"{e}\n\n{traceback.format_exc()}\n\nInstall: pip install -r {ROOT / 'requirements.txt'}",
            )
            return
        if self._creator_win is not None and self._creator_win.isVisible():
            self._creator_win.raise_()
            self._creator_win.activateWindow()
            return
        try:
            self._creator_win = CarCreatorWindow()
            self._creator_win.show()
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self,
                "Car Creator failed to open",
                f"{e}\n\n{traceback.format_exc()}",
            )


def main() -> int:
    import os
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "GTHybridCreator.GTHC"
            )
        except Exception:
            pass
    try:
        from PyQt6.QtCore import Qt as _Qt
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            _Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("GT Hybrid Creator")
    app.setOrganizationName("JeevesGB")
    if ICON_PNG.is_file():
        app.setWindowIcon(QIcon(str(ICON_PNG)))
    apply_app_theme(app)
    win = LauncherWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())