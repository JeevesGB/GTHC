from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

COLORS = {
    "bg": "#f0f2f5",
    "surface": "#ffffff",
    "surface_muted": "#f5f6f8",
    "border": "#dde1e6",
    "border_strong": "#cdd2d9",
    "text": "#1a1d23",
    "text_muted": "#6b7280",
    "text_disabled": "#9ca3af",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_soft": "#eff4ff",
    "accent_disabled": "#93b4f5",
    "accent_text_on": "#ffffff",
    "accent_text_disabled": "#eef3ff",
    "rule": "#e8ebef",
    "grid": "#eef0f3",
    "danger": "#dc2626",
    "success": "#16a34a",
    "delta_up": "#16a34a",
    "delta_down": "#dc2626",
    "focus": "#93c5fd",
}

APP_STYLE = f"""
QMainWindow, QDialog {{
    background: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 12px;
}}
QWidget {{ color: {COLORS["text"]}; }}

QLabel#title {{
    font-size: 16px;
    font-weight: 700;
    color: {COLORS["text"]};
}}
QLabel#muted {{
    color: {COLORS["text_muted"]};
    font-size: 11.5px;
}}
QLabel#path {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 11.5px;
    color: {COLORS["accent"]};
}}
QLabel#tag {{
    font-size: 11px;
    color: {COLORS["text_muted"]};
    font-weight: 500;
}}
QLabel#badge {{
    font-size: 10.5px;
    font-weight: 600;
    color: {COLORS["accent"]};
    background: {COLORS["accent_soft"]};
    border-radius: 8px;
    padding: 1px 7px;
}}
QLabel#cardTitle {{
    font-size: 12.5px;
    font-weight: 700;
    color: {COLORS["text"]};
}}
QLabel#fieldLabel {{
    font-size: 10.5px;
    font-weight: 600;
    color: {COLORS["text_muted"]};
    letter-spacing: 0.3px;
}}
QLabel#gameTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {COLORS["text"]};
    background: transparent;
}}
QLabel#gameDesc {{
    qproperty-alignment: AlignCenter;
    font-size: 11.5px;
    color: {COLORS["text_muted"]};
    background: transparent;
}}
QLabel#subtitle {{
    font-size: 13px;
    color: {COLORS["text_muted"]};
}}
QLabel#deltaUp {{
    color: {COLORS["delta_up"]};
    font-weight: 600;
}}
QLabel#deltaDown {{
    color: {COLORS["delta_down"]};
    font-weight: 600;
}}
QLabel#successBanner {{
    background: #ecfdf5;
    color: {COLORS["success"]};
    border: 1px solid #a7f3d0;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 500;
}}

QFrame#card {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
}}
QFrame#rule {{
    background: {COLORS["rule"]};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QPushButton {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 3px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
    color: {COLORS["text"]};
    min-height: 18px;
}}
QPushButton:hover {{
    border-color: {COLORS["accent"]};
    background: {COLORS["accent_soft"]};
}}
QPushButton:pressed {{ background: #dbe6ff; }}
QPushButton:disabled {{
    color: {COLORS["text_disabled"]};
    background: {COLORS["surface_muted"]};
    border-color: #e5e7eb;
}}
QPushButton:focus {{
    border-color: {COLORS["accent"]};
    outline: none;
}}
QPushButton#primary {{
    background: {COLORS["accent"]};
    color: {COLORS["accent_text_on"]};
    border-color: {COLORS["accent"]};
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
}}
QPushButton#primary:disabled {{
    background: {COLORS["accent_disabled"]};
    border-color: {COLORS["accent_disabled"]};
    color: {COLORS["accent_text_disabled"]};
}}
QPushButton#link {{
    background: transparent;
    border: none;
    color: {COLORS["accent"]};
    padding: 2px 4px;
    font-size: 11.5px;
    font-weight: 500;
}}
QPushButton#link:hover {{ color: {COLORS["accent_hover"]}; }}
QPushButton#danger {{
    color: {COLORS["danger"]};
    border-color: #fecaca;
}}
QPushButton#danger:hover {{
    background: #fef2f2;
    border-color: {COLORS["danger"]};
}}
QPushButton#donor {{
    text-align: left;
    padding: 6px 10px;
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 4px;
    font-size: 12px;
    min-height: 28px;
}}
QPushButton#donor:hover {{ border-color: {COLORS["accent"]}; }}
QPushButton#donor:focus {{
    border-color: {COLORS["accent"]};
    background: {COLORS["accent_soft"]};
}}
QPushButton#game {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 8px;
    padding: 6px 10px;
    text-align: center;
    font-size: 13px;
    font-weight: 600;
    color: {COLORS["text"]};
    min-height: 60px;
}}
QPushButton#game:hover {{
    border-color: {COLORS["accent"]};
    background: {COLORS["accent_soft"]};
}}
QPushButton#game:pressed {{ background: #dbe6ff; }}
QPushButton#game:focus {{
    border-color: {COLORS["accent"]};
}}

QLineEdit {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {COLORS["accent"]};
}}
QLineEdit:focus {{ border-color: {COLORS["accent"]}; }}

QListWidget {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 4px;
    outline: none;
    padding: 2px;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 3px;
    min-height: 18px;
}}
QListWidget::item:selected {{
    background: {COLORS["accent_soft"]};
    color: {COLORS["text"]};
}}
QListWidget::item:hover {{ background: {COLORS["surface_muted"]}; }}

QTabWidget::pane {{
    border: none;
    background: transparent;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 12px;
    margin-right: 2px;
    color: {COLORS["text_muted"]};
    font-weight: 600;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {COLORS["accent"]};
    color: {COLORS["accent_text_on"]};
}}
QTabBar::tab:hover:!selected {{
    background: {COLORS["rule"]};
    color: {COLORS["text"]};
}}

QTableWidget {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    gridline-color: {COLORS["grid"]};
    outline: none;
    font-size: 12px;
}}
QTableWidget::item {{ padding: 3px 8px; }}
QHeaderView::section {{
    background: {COLORS["surface_muted"]};
    color: {COLORS["text_muted"]};
    font-size: 10.5px;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    padding: 5px 8px;
}}

QRadioButton {{
    spacing: 6px;
    padding: 2px 0;
    font-size: 12px;
}}
QRadioButton::indicator {{ width: 14px; height: 14px; }}

QScrollArea {{ border: none; background: transparent; }}
QSplitter::handle {{ background: transparent; width: 8px; }}

QStatusBar {{
    background: {COLORS["surface"]};
    border-top: 1px solid {COLORS["border"]};
    color: {COLORS["text_muted"]};
    font-size: 11.5px;
}}
QToolBar {{
    background: {COLORS["surface"]};
    border-bottom: 1px solid {COLORS["border"]};
    spacing: 6px;
    padding: 3px 8px;
    min-height: 28px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 3px 8px;
    color: {COLORS["text"]};
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    background: {COLORS["accent_soft"]};
    border-color: {COLORS["border_strong"]};
}}
QProgressBar {{
    border: 1px solid {COLORS["border"]};
    border-radius: 3px;
    background: {COLORS["surface_muted"]};
    text-align: center;
    max-height: 12px;
}}
QProgressBar::chunk {{
    background: {COLORS["accent"]};
    border-radius: 2px;
}}
QComboBox {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 18px;
}}
QComboBox:focus {{ border-color: {COLORS["accent"]}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
"""


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    mapping = [
        (QPalette.ColorRole.Window, COLORS["bg"]),
        (QPalette.ColorRole.WindowText, COLORS["text"]),
        (QPalette.ColorRole.Base, COLORS["surface"]),
        (QPalette.ColorRole.AlternateBase, COLORS["surface_muted"]),
        (QPalette.ColorRole.Text, COLORS["text"]),
        (QPalette.ColorRole.Button, COLORS["surface"]),
        (QPalette.ColorRole.ButtonText, COLORS["text"]),
        (QPalette.ColorRole.Highlight, COLORS["accent"]),
        (QPalette.ColorRole.HighlightedText, COLORS["accent_text_on"]),
    ]
    for role, hex_color in mapping:
        pal.setColor(role, QColor(hex_color))
    app.setPalette(pal)
    app.setStyleSheet(APP_STYLE)


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def rule() -> QFrame:
    f = QFrame()
    f.setObjectName("rule")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f


def title_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("title")
    return lab


def muted_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    return lab


def field_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("fieldLabel")
    return lab


def card_title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("cardTitle")
    return lab


def donor_button(main: str, sub: str = "", active: bool = False) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("donor")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(32)
    btn.setText(main if not sub else f"{main}\n{sub}")
    _style_donor(btn, active)
    return btn


def _style_donor(btn: QPushButton, active: bool) -> None:
    if active:
        btn.setStyleSheet(
            f"QPushButton#donor {{ text-align: left; padding: 6px 10px; "
            f"border-color: {COLORS['accent']}; background: {COLORS['accent_soft']}; }}"
        )
    else:
        btn.setStyleSheet(
            "QPushButton#donor { text-align: left; padding: 6px 10px; }"
        )


def set_donor_button(btn: QPushButton, main: str, sub: str = "", active: bool = False) -> None:
    btn.setText(main if not sub else f"{main}\n{sub}")
    _style_donor(btn, active)
