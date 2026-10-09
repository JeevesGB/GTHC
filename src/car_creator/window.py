"""Car Creator — standalone window launched from the GTHC launcher.

Clone a template car into a new database entry while previewing:
  - Spec stats (power, weight, drivetrain, …)
  - Dyno graph (torque / power vs RPM)
  - Gearbox graph (ratio “length” per gear)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QColor, QBrush
from PyQt6.QtWidgets import (
    QDialog,
    QSplitter,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QTabWidget,
    QSlider,
    QAbstractItemView,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    HAS_MPL = True
except Exception:
    HAS_MPL = False
    FigureCanvasQTAgg = None  # type: ignore
    Figure = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "gt3") not in sys.path:
    sys.path.insert(0, str(ROOT / "gt3"))
if str(ROOT / "gt4") not in sys.path:
    sys.path.insert(0, str(ROOT / "gt4"))

from ui.design import APP_STYLE
from ui.folder_paths import get_folder, set_folder, get_last_game, get_recent
from ui.car_picker import CarPickerDialog, PickerCar
from ui.makers import guess_brand_from_text


DRIVE_NAMES = ["FR", "FF", "4WD", "MR", "RR"]
GEAR_COLORS = [
    "#2563eb", "#dc2626", "#ea580c", "#16a34a",
    "#7c3aed", "#0891b2", "#ca8a04", "#e11d48",
]
GEAR_LABELS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]
ASPIRATION_OPTIONS = ["Naturally aspirated", "Turbo", "Supercharger", "Twin-turbo", "Hybrid"]


def _label(text: str, obj: str = "") -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(True)
    return lab


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


@dataclass
class PreviewCar:
    """Normalised preview model for both GT3 and GT4 templates."""

    game: str  # "gt3" | "gt4"
    key: Any  # hex str (GT3) or row_id (GT4)
    name: str
    label: str = ""
    year: int = 0
    price: int = 0
    ps: Optional[float] = None
    torque: Optional[float] = None
    rev_limit: Optional[int] = None
    mass: Optional[int] = None
    wheelbase: Optional[int] = None
    drive: Optional[int] = None
    gears: Optional[int] = None
    ratios: List[float] = field(default_factory=list)  # forward gear ratios
    rpm: List[int] = field(default_factory=list)
    torque_curve: List[float] = field(default_factory=list)
    power_curve: List[float] = field(default_factory=list)
    idle_rpm: Optional[int] = None
    curve_loaded: bool = False
    raw: Any = None  # engine-specific handle


class CarCreatorWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GT Car Creator")
        self.resize(1180, 760)
        self.setMinimumSize(880, 560)
        self.setStyleSheet(APP_STYLE)

        self.game: Optional[str] = None  # gt3 | gt4
        self.folder: Optional[Path] = None
        self.db: Any = None
        self.previews: List[PreviewCar] = []
        self.current: Optional[PreviewCar] = None
        self._seeding = False
        self._syncing = False
        self._dirty = False
        self._baseline_rpm: list = []
        self._baseline_tq: list = []
        self._baseline_pw: list = []
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(40)
        self._redraw_timer.timeout.connect(self._flush_redraw)
        self._pending_dyno = False
        self._pending_gear = False

        # GT3 multi-region support (primary region only for creator v1)
        self._gt3_regions: list = []

        self._install_crash_log()
        self._build_ui()
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Loading saved database path…")
        QTimer.singleShot(80, self._safe_try_load_saved)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        self.addToolBar(tb)

        act = QAction("Open folder…", self)
        act.triggered.connect(self._open_folder)
        tb.addAction(act)
        act = QAction("Reload folder", self)
        act.triggered.connect(self._reload_folder)
        tb.addAction(act)
        act = QAction("Save database…", self)
        act.triggered.connect(self._save)
        tb.addAction(act)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        root.addWidget(self._splitter)

        # ---- LEFT: setup + form (scrollable) ----
        left_host = QWidget()
        left = QVBoxLayout(left_host)
        left.setContentsMargins(4, 4, 8, 4)
        left.setSpacing(8)

        # Step 1 — source
        src_card = _card()
        src_l = QVBoxLayout(src_card)
        src_l.setContentsMargins(10, 8, 10, 8)
        src_l.setSpacing(6)
        src_l.addWidget(_label("1 · Source", "cardTitle"))

        row = QHBoxLayout()
        row.setSpacing(8)
        self.game_combo = QComboBox()
        self.game_combo.addItem("Gran Turismo 3", "gt3")
        self.game_combo.addItem("Gran Turismo 4", "gt4")
        self.game_combo.setMinimumWidth(140)
        row.addWidget(self.game_combo)
        self.open_btn = QPushButton("Open folder…")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self._open_folder)
        row.addWidget(self.open_btn)
        src_l.addLayout(row)
        self.folder_lab = _label("No database loaded", "muted")
        src_l.addWidget(self.folder_lab)

        src_l.addWidget(_label("Clone from", "fieldLabel"))
        self.template_btn = QPushButton("Choose template car…")
        self.template_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.template_btn.setEnabled(False)
        self.template_btn.setMinimumHeight(32)
        self.template_btn.clicked.connect(self._pick_template)
        src_l.addWidget(self.template_btn)
        self.template_lab = _label("No template selected", "muted")
        src_l.addWidget(self.template_lab)
        # Keep an invisible index for current template (into self.previews)
        self._template_index: int = -1
        left.addWidget(src_card)

        # Step 2 — edit tabs
        edit_card = _card()
        edit_l = QVBoxLayout(edit_card)
        edit_l.setContentsMargins(8, 8, 8, 8)
        edit_l.setSpacing(4)
        edit_l.addWidget(_label("2 · Edit new car", "cardTitle"))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # --- Identity tab ---
        id_w = QWidget()
        id_l = QVBoxLayout(id_w)
        id_l.setContentsMargins(8, 10, 8, 8)
        id_l.setSpacing(8)
        id_l.addWidget(_label("Shown in the database / dealership lists.", "muted"))

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. my_skyline_01")
        id_l.addLayout(self._field("Display name / label", self.label_edit, tip="GT4: internal label + display name. GT3: written into unicode name strings on Save."))

        self.price_spin = QSpinBox()
        self.price_spin.setRange(0, 50_000_000)
        self.price_spin.setSingleStep(1000)
        self.price_spin.setGroupSeparatorShown(True)
        id_l.addLayout(self._field("Price", self.price_spin, tip="Credits"))

        self.year_spin = QSpinBox()
        self.year_spin.setRange(1900, 2100)
        id_l.addLayout(self._field("Year", self.year_spin))

        self.type_spin = QComboBox()
        self.type_spin.addItem("Road", 0)
        self.type_spin.addItem("Race", 1)
        self.type_spin.addItem("Rally", 2)
        id_l.addLayout(self._field("Class", self.type_spin, tip="GT3 car class"))

        self.flags_spin = QSpinBox()
        self.flags_spin.setRange(0, 255)
        id_l.addLayout(self._field("Flags", self.flags_spin, tip="Buy/sell flags (advanced)"))
        id_l.addStretch(1)
        tabs.addTab(id_w, "Identity")

        # --- Performance tab ---
        perf_w = QWidget()
        perf_l = QVBoxLayout(perf_w)
        perf_l.setContentsMargins(8, 10, 8, 8)
        perf_l.setSpacing(8)
        perf_l.addWidget(_label(
            "Peaks, chassis and aspiration. Torque shape is edited on the Curve tab.",
            "muted",
        ))

        self.aspiration_combo = QComboBox()
        for a in ASPIRATION_OPTIONS:
            self.aspiration_combo.addItem(a)
        perf_l.addLayout(self._field("Aspiration", self.aspiration_combo))

        self.ps_spin = QDoubleSpinBox()
        self.ps_spin.setRange(0, 2000)
        self.ps_spin.setDecimals(0)
        self.ps_spin.setSingleStep(5)
        self.ps_spin.setSuffix(" PS")
        self.ps_slider = self._slider(0, 1000)
        perf_l.addLayout(self._field_slider("Peak power", self.ps_spin, self.ps_slider))

        self.tq_spin = QDoubleSpinBox()
        self.tq_spin.setRange(0, 300)
        self.tq_spin.setDecimals(1)
        self.tq_spin.setSingleStep(0.5)
        self.tq_spin.setSuffix(" kgf·m")
        self.tq_slider = self._slider(0, 1500)
        perf_l.addLayout(self._field_slider("Peak torque", self.tq_spin, self.tq_slider))

        self.rev_spin = QSpinBox()
        self.rev_spin.setRange(1000, 20000)
        self.rev_spin.setSingleStep(100)
        self.rev_spin.setSuffix(" rpm")
        self.rev_slider = self._slider(1000, 12000)
        perf_l.addLayout(self._field_slider("Rev limit", self.rev_spin, self.rev_slider))

        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(0, 5000)
        self.idle_spin.setSingleStep(50)
        self.idle_spin.setSuffix(" rpm")
        perf_l.addLayout(self._field("Idle RPM", self.idle_spin))

        self.mass_spin = QSpinBox()
        self.mass_spin.setRange(400, 10000)
        self.mass_spin.setSingleStep(10)
        self.mass_spin.setSuffix(" kg")
        self.mass_slider = self._slider(400, 2500)
        perf_l.addLayout(self._field_slider("Mass", self.mass_spin, self.mass_slider))

        self.wb_spin = QSpinBox()
        self.wb_spin.setRange(1500, 10000)
        self.wb_spin.setSingleStep(10)
        self.wb_spin.setSuffix(" mm")
        perf_l.addLayout(self._field("Wheelbase", self.wb_spin))

        self.drive_spin = QComboBox()
        for i, name in enumerate(DRIVE_NAMES):
            self.drive_spin.addItem(name, i)
        perf_l.addLayout(self._field("Drivetrain", self.drive_spin))

        scale_row = QHBoxLayout()
        scale_row.addWidget(_label("Scale curve:", "fieldLabel"))
        for pct, label in ((0.9, "−10%"), (1.0, "100%"), (1.1, "+10%"), (1.25, "+25%")):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedWidth(52)
            b.clicked.connect(lambda checked=False, p=pct: self._scale_power(p))
            scale_row.addWidget(b)
        scale_row.addStretch(1)
        perf_l.addLayout(scale_row)
        perf_l.addStretch(1)
        tabs.addTab(perf_w, "Performance")

        # --- Torque curve tab ---
        curve_w = QWidget()
        curve_l = QVBoxLayout(curve_w)
        curve_l.setContentsMargins(8, 10, 8, 8)
        curve_l.setSpacing(6)
        curve_l.addWidget(_label(
            "Spin the values or use the buttons. Power is calculated live "
            "(PS ≈ tq × rpm ÷ 716.2). Peak row is highlighted.",
            "muted",
        ))
        self.curve_stats_lab = _label("—", "muted")
        curve_l.addWidget(self.curve_stats_lab)

        self.curve_table = QTableWidget(0, 3)
        self.curve_table.setHorizontalHeaderLabels(["RPM", "Torque", "Power (PS)"])
        self.curve_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.curve_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.curve_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.curve_table.verticalHeader().setDefaultSectionSize(30)
        self.curve_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.curve_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.curve_table.setMinimumHeight(220)
        curve_l.addWidget(self.curve_table, 1)

        curve_btns = QHBoxLayout()
        for label, slot in (
            ("+ Point", self._curve_add_point),
            ("Insert", self._curve_insert_point),
            ("− Point", self._curve_remove_point),
            ("Smooth", self._curve_smooth),
            ("Reset", self._curve_reset),
        ):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            curve_btns.addWidget(b)
        curve_btns.addStretch(1)
        curve_l.addLayout(curve_btns)

        scale_c = QHBoxLayout()
        scale_c.addWidget(_label("Torque ×", "fieldLabel"))
        for factor, lab in ((0.95, "0.95"), (1.05, "1.05"), (1.10, "1.10")):
            b = QPushButton(lab)
            b.setFixedWidth(48)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, f=factor: self._curve_scale_torque(f))
            scale_c.addWidget(b)
        scale_c.addStretch(1)
        curve_l.addLayout(scale_c)
        tabs.addTab(curve_w, "Curve")

        # --- Gearbox tab ---
        gear_w = QWidget()
        gear_l = QVBoxLayout(gear_w)
        gear_l.setContentsMargins(8, 10, 8, 8)
        gear_l.setSpacing(6)
        gear_l.addWidget(_label(
            "Colours match the geared power graph. Drag a slider or type a ratio. 0 = off.",
            "muted",
        ))

        self.ratio_spins: list = []
        self.ratio_sliders: list = []
        self.ratio_color_labs: list = []
        for i in range(8):
            row = QHBoxLayout()
            row.setSpacing(6)
            swatch = QLabel(f" {GEAR_LABELS[i]} ")
            swatch.setStyleSheet(
                f"background:{GEAR_COLORS[i]}; color:white; border-radius:3px; "
                f"padding:2px 6px; font-weight:600; font-size:11px;"
            )
            swatch.setFixedWidth(44)
            self.ratio_color_labs.append(swatch)
            row.addWidget(swatch)
            sl = self._slider(0, 600)  # ratio ×100, 0.00–6.00 default range
            sl.setMaximum(2000)  # up to 20.00
            self.ratio_sliders.append(sl)
            row.addWidget(sl, 1)
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 20.0)
            sp.setDecimals(3)
            sp.setSingleStep(0.05)
            sp.setSpecialValueText("off")
            sp.setMinimumWidth(80)
            sp.setMaximumWidth(140)
            self.ratio_spins.append(sp)
            row.addWidget(sp)
            # wire after both exist
            sl.valueChanged.connect(lambda v, idx=i: self._gear_from_slider(idx, v))
            sp.valueChanged.connect(lambda v, idx=i: self._gear_from_spin(idx, v))
            gear_l.addLayout(row)

        span_row = QHBoxLayout()
        self.span_lab = _label("Ratio span: —", "muted")
        span_row.addWidget(self.span_lab)
        span_row.addStretch(1)
        reset_ratios = QPushButton("Reset from template")
        reset_ratios.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_ratios.clicked.connect(self._reset_ratios_from_template)
        span_row.addWidget(reset_ratios)
        gear_l.addLayout(span_row)

        # Quick spacing helpers
        help_row = QHBoxLayout()
        for label, fn in (
            ("Close ratios", lambda: self._gear_pack(0.85)),
            ("Spread ratios", lambda: self._gear_pack(1.15)),
        ):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            help_row.addWidget(b)
        help_row.addStretch(1)
        gear_l.addLayout(help_row)
        gear_l.addStretch(1)
        tabs.addTab(gear_w, "Gearbox")

        edit_l.addWidget(tabs, 1)
        left.addWidget(edit_card, 1)

        # Live preview: any spin change refreshes graphs
        for w in (self.ps_spin, self.tq_spin, self.rev_spin, self.idle_spin, self.mass_spin, self.wb_spin):
            w.valueChanged.connect(self._on_stats_edited)
        self.drive_spin.currentIndexChanged.connect(self._on_stats_edited)
        self.label_edit.textChanged.connect(lambda *_: self._update_summary())
        # Sliders drive spins (spin signals then refresh graphs)
        self.ps_slider.valueChanged.connect(lambda v: self._from_slider(self.ps_spin, self.ps_slider, v, 1.0))
        self.tq_slider.valueChanged.connect(lambda v: self._from_slider(self.tq_spin, self.tq_slider, v, 0.1))
        self.rev_slider.valueChanged.connect(lambda v: self._from_slider(self.rev_spin, self.rev_slider, v, 1.0))
        self.mass_slider.valueChanged.connect(lambda v: self._from_slider(self.mass_spin, self.mass_slider, v, 1.0))
        # Spins drive slider positions only (no feedback loop)
        self.ps_spin.valueChanged.connect(lambda v: self._from_spin(self.ps_slider, v, 1.0))
        self.tq_spin.valueChanged.connect(lambda v: self._from_spin(self.tq_slider, v, 10.0))
        self.rev_spin.valueChanged.connect(lambda v: self._from_spin(self.rev_slider, v, 1.0))
        self.mass_spin.valueChanged.connect(lambda v: self._from_spin(self.mass_slider, v, 1.0))

        # Summary of pending edits
        sum_card = _card()
        sum_l = QVBoxLayout(sum_card)
        sum_l.setContentsMargins(10, 8, 10, 8)
        sum_l.setSpacing(4)
        sum_l.addWidget(_label("Summary", "cardTitle"))
        self.summary_lab = _label("Choose a template to begin.", "muted")
        self.summary_lab.setWordWrap(True)
        sum_l.addWidget(self.summary_lab)
        left.addWidget(sum_card)

        # Step 3 — create
        self.create_btn = QPushButton("3 · Create car (in memory)")
        self.create_btn.setObjectName("primary")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.setMinimumHeight(36)
        self.create_btn.setEnabled(False)
        self.create_btn.clicked.connect(self._create)
        left.addWidget(self.create_btn)

        # Wire game switch only after the rest of the UI exists
        last = get_last_game()
        if last == "gt4":
            self.game_combo.setCurrentIndex(1)
        self.game_combo.currentIndexChanged.connect(self._on_game_changed)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setWidget(left_host)
        left_scroll.setMinimumWidth(300)
        left_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._splitter.addWidget(left_scroll)

        # ---- RIGHT: stats + graphs ----
        right_host = QWidget()
        right = QVBoxLayout(right_host)
        right.setContentsMargins(8, 4, 4, 4)
        right.setSpacing(8)

        stats_card = _card()
        sl = QVBoxLayout(stats_card)
        sl.setContentsMargins(10, 8, 10, 8)
        sl.setSpacing(4)
        sl.addWidget(_label("Preview", "cardTitle"))
        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(16)
        self.stats_grid.setVerticalSpacing(4)
        self._stat_labels: Dict[str, QLabel] = {}
        for i, key in enumerate(
            [
                "Power",
                "Torque",
                "Rev limit",
                "Mass",
                "Wheelbase",
                "Layout",
                "Gears",
                "Price",
                "Year",
            ]
        ):
            r, c = divmod(i, 3)
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(_label(key, "fieldLabel"))
            val = QLabel("—")
            val.setStyleSheet("font-size: 14px; font-weight: 600;")
            self._stat_labels[key] = val
            cell.addWidget(val)
            self.stats_grid.addLayout(cell, r, c)
        sl.addLayout(self.stats_grid)
        right.addWidget(stats_card)

        # Dyno
        dyno_card = _card()
        dl = QVBoxLayout(dyno_card)
        dl.setContentsMargins(6, 6, 6, 6)
        dl.addWidget(_label("Dyno — torque & power", "cardTitle"))
        if HAS_MPL:
            self.dyno_fig = Figure(figsize=(5.0, 2.4), dpi=100)
            self.dyno_fig.patch.set_facecolor("#ffffff")
            self.dyno_ax = self.dyno_fig.add_subplot(111)
            self.dyno_ax2 = self.dyno_ax.twinx()
            self.dyno_canvas = FigureCanvasQTAgg(self.dyno_fig)
            self.dyno_canvas.setMinimumHeight(140)
            self.dyno_canvas.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.dyno_canvas.mpl_connect("resize_event", lambda e: self._on_mpl_resize("dyno"))
            dl.addWidget(self.dyno_canvas, 1)
        else:
            self.dyno_fig = self.dyno_ax = self.dyno_ax2 = self.dyno_canvas = None
            dl.addWidget(_label("Install matplotlib for graphs: pip install matplotlib", "muted"))
        right.addWidget(dyno_card, 2)

        # Gearbox
        gear_card = _card()
        gel = QVBoxLayout(gear_card)
        gel.setContentsMargins(6, 6, 6, 6)
        gel.addWidget(_label("Geared power — power delivery per gear", "cardTitle"))
        if HAS_MPL:
            self.gear_fig = Figure(figsize=(5.0, 2.0), dpi=100)
            self.gear_fig.patch.set_facecolor("#ffffff")
            self.gear_ax = self.gear_fig.add_subplot(111)
            self.gear_canvas = FigureCanvasQTAgg(self.gear_fig)
            self.gear_canvas.setMinimumHeight(120)
            self.gear_canvas.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.gear_canvas.mpl_connect("resize_event", lambda e: self._on_mpl_resize("gear"))
            gel.addWidget(self.gear_canvas, 1)
        else:
            self.gear_fig = self.gear_ax = self.gear_canvas = None
            gel.addWidget(_label("Install matplotlib for gearbox graph", "muted"))
        right.addWidget(gear_card, 2)

        right_host.setMinimumWidth(360)
        right_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._splitter.addWidget(right_host)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([400, 780])

        self._clear_graphs("Open a database and choose a template")

    # -------------------------------------------------------------- data load

    @staticmethod
    def _field(title: str, widget, tip: str = "") -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        lab = QLabel(title)
        lab.setObjectName("fieldLabel")
        if tip:
            lab.setToolTip(tip)
            widget.setToolTip(tip)
        if hasattr(widget, "setMinimumHeight"):
            widget.setMinimumHeight(26)
        if hasattr(widget, "setSizePolicy"):
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        col.addWidget(lab)
        col.addWidget(widget)
        return col

    @staticmethod
    def _slider(lo: int, hi: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setSingleStep(1)
        s.setPageStep(max(1, (hi - lo) // 20))
        s.setMinimumHeight(22)
        return s

    def _field_slider(self, title: str, spin, slider: QSlider, tip: str = "") -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        lab = QLabel(title)
        lab.setObjectName("fieldLabel")
        if tip:
            lab.setToolTip(tip)
        col.addWidget(lab)
        row = QHBoxLayout()
        row.setSpacing(8)
        slider.setMinimumHeight(24)
        row.addWidget(slider, 1)
        spin.setMinimumWidth(100)
        spin.setMaximumWidth(16777215)  # no artificial cap
        spin.setMinimumHeight(28)
        spin.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row.addWidget(spin)
        col.addLayout(row)
        return col

    def _scale_power(self, factor: float) -> None:
        """±% scales peaks and torque-curve table; 100% restores template."""
        if not self.current:
            return
        if abs(factor - 1.0) < 1e-9:
            self._fill_curve_table(self.current)
            self.ps_spin.setValue(float(self.current.ps or 0))
            self.tq_spin.setValue(float(self.current.torque or 0))
        else:
            self.ps_spin.setValue(max(0.0, self.ps_spin.value() * factor))
            self.tq_spin.setValue(max(0.0, self.tq_spin.value() * factor))
            self._curve_scale_torque(factor)
            return
        self._on_stats_edited()


    def _from_slider(self, spin, slider: QSlider, slider_val: int, scale: float) -> None:
        """Slider moved → update spin. Spin valueChanged refreshes graphs."""
        if getattr(self, "_seeding", False):
            return
        raw = float(slider_val) * scale
        # QSpinBox requires int; QDoubleSpinBox accepts float
        from PyQt6.QtWidgets import QSpinBox, QDoubleSpinBox
        if isinstance(spin, QSpinBox) and not isinstance(spin, QDoubleSpinBox):
            new_val = int(round(raw))
            if spin.value() == new_val:
                self._on_stats_edited()
                return
            spin.setValue(new_val)
        else:
            new_val = float(raw)
            if abs(float(spin.value()) - new_val) < 1e-9:
                self._on_stats_edited()
                return
            spin.setValue(new_val)

    def _from_spin(self, slider: QSlider, spin_val: float, mult: float) -> None:
        """Spin changed → move slider knob only (signals blocked so no loop)."""
        if getattr(self, "_seeding", False):
            return
        target = int(round(float(spin_val) * mult))
        if target > slider.maximum():
            slider.blockSignals(True)
            slider.setMaximum(max(target + 50, slider.maximum()))
            slider.blockSignals(False)
        if target < slider.minimum():
            target = slider.minimum()
        if slider.value() == target:
            return
        slider.blockSignals(True)
        slider.setValue(target)
        slider.blockSignals(False)



    def _set_dirty(self, dirty: bool = True) -> None:
        self._dirty = dirty
        base = "GT Car Creator"
        if self.game:
            base += f" — {self.game.upper()}"
        if self.folder:
            base += f" — {self.folder.name}"
        if dirty:
            base += " *"
        self.setWindowTitle(base)
        if dirty:
            self.status.showMessage("Unsaved changes in memory — Save database… to write", 4000)

    def closeEvent(self, event) -> None:
        if self._dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved cars",
                "You have cars created in memory that are not saved.\n\n"
                "Close anyway and lose them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()

    def _install_crash_log(self) -> None:
        """Write uncaught errors to ~/GTHC_car_creator_error.log (pythonw shows nothing)."""
        import traceback as _tb

        def _hook(etype, value, tb):
            try:
                msg = "".join(_tb.format_exception(etype, value, tb))
                (Path.home() / "GTHC_car_creator_error.log").write_text(msg, encoding="utf-8")
            except Exception:
                pass
            sys.__excepthook__(etype, value, tb)

        sys.excepthook = _hook

    def _safe_try_load_saved(self) -> None:
        try:
            self._try_load_saved()
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            self.status.showMessage(f"Load error: {e}", 10000)
            try:
                QMessageBox.warning(self, "Car Creator", f"Could not auto-load database:\n{e}")
            except Exception:
                pass
            try:
                log = Path.home() / "GTHC_car_creator_error.log"
                log.write_text(err, encoding="utf-8")
            except Exception:
                pass

    def _try_load_saved(self) -> None:
        """Load the path stored in folder_paths.json for the selected game."""
        game = self.game_combo.currentData() or "gt3"
        path = get_folder(game)
        if path is None or not path.is_dir():
            # Fall back to most recent existing path
            for p in get_recent(game):
                if p.is_dir():
                    path = p
                    break
        if path is None or not path.is_dir():
            self.folder_lab.setText("No saved path — click Open folder…")
            self.template_btn.setEnabled(False)
            self.template_btn.setText("Choose template car…")
            self.template_lab.setText("No template selected")
            self._template_index = -1
            self.create_btn.setEnabled(False)
            self.status.showMessage(
                f"No saved {game.upper()} folder in folder_paths.json. Open a folder to begin.",
                6000,
            )
            return
        self._load_path(path, game, quiet=True)


    def _reload_folder(self) -> None:
        if not self.folder or not self.game:
            self._try_load_saved()
            return
        if self._dirty:
            reply = QMessageBox.question(
                self,
                "Reload?",
                "Reload from disk and discard cars created in memory?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._load_path(self.folder, self.game, quiet=False)
        self._set_dirty(False)

    def _on_game_changed(self, *_args) -> None:
        if getattr(self, "_seeding", False):
            return
        if self._dirty:
            reply = QMessageBox.question(
                self,
                "Switch game?",
                "Switching game discards cars created in memory. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                # revert combo
                self.game_combo.blockSignals(True)
                idx = self.game_combo.findData(self.game) if self.game else 0
                if idx >= 0:
                    self.game_combo.setCurrentIndex(idx)
                self.game_combo.blockSignals(False)
                return
        self._try_load_saved()
        self._set_dirty(False)


    def _load_path(self, path: Path, game: str, quiet: bool = False) -> bool:
        """Load a database folder and remember it in folder_paths.json."""
        try:
            if game == "gt3":
                self._load_gt3(path)
            else:
                self._load_gt4(path)
        except Exception as e:
            if not quiet:
                QMessageBox.critical(self, "Load failed", str(e))
            else:
                self.folder_lab.setText(f"Saved path failed: {path.name}")
                self.status.showMessage(f"Could not load {path}: {e}", 8000)
            return False
        set_folder(game, path)
        self.game = game
        self.folder = path
        self.folder_lab.setText(str(path))
        self.folder_lab.setToolTip(str(path))
        self.create_btn.setEnabled(True)
        self._set_dirty(False)
        self.status.showMessage(
            f"Loaded {game.upper()} · {len(self.previews)} cars · {path}", 5000,
        )
        return True

    def _open_folder(self) -> None:
        game = self.game_combo.currentData() or "gt3"
        start = get_folder(game) or Path.home()
        if start and not Path(start).is_dir():
            start = Path.home()
        folder = QFileDialog.getExistingDirectory(
            self,
            f"Open {'GT3 paramdb' if game == 'gt3' else 'GT4 SpecDB'} folder",
            str(start),
        )
        if not folder:
            return
        self._load_path(Path(folder), game, quiet=False)

    def _load_gt3(self, folder: Path) -> None:
        from gt_engine import (
            open_db,
            car_count,
            car_hash,
            car_stats,
            car_names,
            hex64,
            engine_curve,
            read_drivetrain_finetune,
            classify_file,
            parse_stdb,
            parse_id_index,
        )

        # Classify every .db in the folder (paramdb + string/index mates)
        files = []  # list of {path, name, kind, suffix, raw}
        for p in sorted(folder.iterdir()):
            if not p.is_file() or not p.name.endswith(".db") or p.name.endswith(".bak"):
                continue
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            cls = classify_file(p.name, raw)
            if not cls:
                continue
            files.append({
                "path": p, "name": p.name, "kind": cls["kind"],
                "suffix": cls["suffix"], "raw": raw,
            })

        paramdbs = [f for f in files if f["kind"] == "paramdb"]
        if not paramdbs:
            raise FileNotFoundError("No paramdb*.db found in folder")

        # Prefer US, then EU, then JP, then first available
        def rank(suffix: str) -> int:
            s = (suffix or "").lower()
            return {"us": 0, "eu": 1, "jp": 2, "": 3}.get(s, 9)

        paramdbs.sort(key=lambda f: rank(f["suffix"]))
        chosen = paramdbs[0]

        def mate(kind: str, suffix: str):
            return next(
                (x for x in files if x["kind"] == kind and x["suffix"] == suffix),
                None,
            )

        suffix = chosen["suffix"]
        str_tbl = uni = id_str = None
        id_map = None
        for kind, attr_parse in (
            ("str", ("str_tbl", parse_stdb)),
            ("unistr", ("uni", parse_stdb)),
            ("idstr", ("id_str", parse_stdb)),
            ("idx", ("id_map", parse_id_index)),
        ):
            m = mate(kind, suffix)
            if not m:
                continue
            try:
                parsed = attr_parse[1](m["raw"])
                if attr_parse[0] == "str_tbl":
                    str_tbl = parsed
                elif attr_parse[0] == "uni":
                    uni = parsed
                elif attr_parse[0] == "id_str":
                    id_str = parsed
                elif attr_parse[0] == "id_map":
                    id_map = parsed
            except Exception:
                pass

        db = open_db(chosen["raw"])
        self.db = {
            "game": "gt3",
            "db": db,
            "path": chosen["path"],
            "raw": chosen["raw"],
            "suffix": suffix,
            "str_tbl": str_tbl,
            "uni": uni,
            "id_map": id_map,
            "id_str": id_str,
        }
        self.previews = []
        n = car_count(db)
        for i in range(n):
            hx = hex64(car_hash(db, i))
            st = car_stats(db, i)
            nm = car_names(db, i, uni, str_tbl, id_map, id_str)
            main = (nm.name or nm.code or "").strip()
            while main and main[0] in "-–—·•|_":
                main = main[1:].strip()
            if not main:
                main = f"Car {i}"
            display = main
            if nm.name and nm.code and nm.code not in main:
                display = f"{main}  ({nm.code})"
            # Curves / ratios loaded lazily on template select
            pv = PreviewCar(
                game="gt3",
                key=hx,
                name=display,
                label=hx,
                year=int(st.year or 0),
                price=int(st.price or 0),
                ps=float(st.ps) if st.ps else None,
                torque=float(st.torque) if st.torque else None,
                rev_limit=int(st.rev_limit) if st.rev_limit else None,
                mass=int(st.mass) if st.mass else None,
                wheelbase=int(st.wheelbase) if st.wheelbase else None,
                drive=st.drive,
                gears=st.gears,
                ratios=[],
                rpm=[],
                torque_curve=[],
                power_curve=[],
                curve_loaded=False,
                raw=i,
            )
            self.previews.append(pv)
        self.template_btn.setEnabled(bool(self.previews))
        self.template_btn.setText(f"Choose template car…  ({len(self.previews)} cars)")
        if self.previews:
            self._select_template(0)
    def _load_gt4(self, folder: Path) -> None:
        from gt4_engine import load_specdb

        db = load_specdb(folder)
        self.db = {"game": "gt4", "db": db, "path": folder}
        self.previews = []
        for car in db.cars:
            # Curves / chassis / ratios loaded lazily on template select
            pv = PreviewCar(
                game="gt4",
                key=car.row_id,
                name=car.name,
                label=car.label,
                year=int(car.year or 0),
                price=int(car.price or 0),
                ps=None,
                torque=None,
                rev_limit=None,
                mass=None,
                wheelbase=None,
                drive=None,
                gears=None,
                ratios=[],
                rpm=[],
                torque_curve=[],
                power_curve=[],
                curve_loaded=False,
                raw=car,
            )
            self.previews.append(pv)
        self.template_btn.setEnabled(bool(self.previews))
        self.template_btn.setText(f"Choose template car…  ({len(self.previews)} cars)")
        if self.previews:
            self._select_template(0)

    # -------------------------------------------------------------- preview

    def _ensure_curve_loaded(self, c: PreviewCar) -> None:
        """Load engine curve, ratios and chassis the first time a template is selected."""
        if c.curve_loaded:
            return
        if c.game == "gt3":
            from gt_engine import engine_curve, read_drivetrain_finetune
            db = self.db["db"]
            i = int(c.raw) if c.raw is not None else -1
            if i < 0:
                c.curve_loaded = True
                return
            try:
                curve = engine_curve(db, i)
            except Exception:
                curve = None
            try:
                dt = read_drivetrain_finetune(db, i)
            except Exception:
                dt = None
            if curve:
                c.rpm = list(curve.rpm or [])
                c.torque_curve = list(curve.torque or [])
                c.power_curve = list(curve.power or [])
                if curve.peak_ps and (c.ps is None or float(c.ps) < float(curve.peak_ps) * 0.5):
                    c.ps = float(curve.peak_ps)
                if c.torque_curve:
                    tmax = max(c.torque_curve)
                    if c.torque is None or float(c.torque) < tmax * 0.5:
                        c.torque = tmax
                elif curve.peak_torque:
                    c.torque = float(curve.peak_torque)
                if curve.rev_limit:
                    c.rev_limit = int(curve.rev_limit)
                elif c.rpm and not c.rev_limit:
                    c.rev_limit = int(max(c.rpm))
                if getattr(curve, "idle_rpm", None):
                    c.idle_rpm = int(curve.idle_rpm)
            ratios: List[float] = []
            if dt:
                for k in range(1, 9):
                    v = getattr(dt, f"ratio_{k}", None)
                    if v and v > 0:
                        ratios.append(float(v))
                if dt.gears:
                    c.gears = dt.gears
                if dt.drive is not None:
                    c.drive = dt.drive
            c.ratios = ratios
            if ratios and not c.gears:
                c.gears = len(ratios)
        else:
            from gt4_engine import engine_curve_for_car, read_finetune_for_car
            db = self.db["db"]
            car = c.raw
            try:
                curve = engine_curve_for_car(db, car)
            except Exception:
                curve = None
            try:
                ft = read_finetune_for_car(db, car)
            except Exception:
                ft = None
            if curve:
                c.rpm = list(curve.rpm or [])
                c.torque_curve = list(curve.torque or [])
                c.power_curve = list(curve.power or [])
                c.ps = float(curve.peak_ps) if curve.peak_ps else (
                    max(c.power_curve) if c.power_curve else None
                )
                c.torque = float(curve.peak_torque) if curve.peak_torque else None
                if c.torque_curve:
                    tmax = max(c.torque_curve)
                    if c.torque is None or float(c.torque) < tmax * 0.5:
                        c.torque = tmax
                if c.power_curve and (c.ps is None or float(c.ps) < max(c.power_curve) * 0.5):
                    c.ps = max(c.power_curve)
                c.rev_limit = (
                    int(curve.rev_limit) if curve.rev_limit
                    else (int(max(c.rpm)) if c.rpm else None)
                )
            if ft:
                if ft.chassis:
                    c.mass = ft.chassis.mass
                    c.wheelbase = ft.chassis.wheelbase
                if ft.drivetrain:
                    c.drive = ft.drivetrain.drive
                    ratios = []
                    for k in range(1, 9):
                        v = getattr(ft.drivetrain, f"ratio_{k}", None)
                        if v and v > 0:
                            ratios.append(float(v))
                    c.ratios = ratios
                    c.gears = ft.drivetrain.gears or (len(ratios) or None)
                if ft.engine and ft.engine.idle_rpm:
                    c.idle_rpm = int(ft.engine.idle_rpm)
        c.curve_loaded = True

    def _schedule_redraw(self, *, dyno: bool = False, gear: bool = False) -> None:
        if dyno:
            self._pending_dyno = True
        if gear:
            self._pending_gear = True
        if not self._redraw_timer.isActive():
            self._redraw_timer.start()

    def _flush_redraw(self) -> None:
        c = self.current
        do_dyno, do_gear = self._pending_dyno, self._pending_gear
        self._pending_dyno = False
        self._pending_gear = False
        if c is None:
            return
        if do_dyno:
            try:
                self._draw_dyno(c)
            except Exception:
                pass
        if do_gear:
            try:
                self._draw_gearbox(c)
            except Exception:
                pass

    def _on_template_changed(self) -> None:
        try:
            self._on_template_changed_impl()
        except Exception as e:
            import traceback
            self.status.showMessage(f"Template error: {e}", 8000)
            try:
                (Path.home() / "GTHC_car_creator_error.log").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except Exception:
                pass

    def _pick_template(self) -> None:
        if not self.previews:
            return
        cars = []
        for i, p in enumerate(self.previews):
            layout = ""
            if p.drive is not None and 0 <= p.drive < len(DRIVE_NAMES):
                layout = DRIVE_NAMES[p.drive]
            brand = guess_brand_from_text(p.name, p.label or "")
            cars.append(PickerCar(
                id=i,
                name=p.name,
                sub=p.label or "",
                search=f"{p.name} {p.label} {p.year} {p.ps or ''} {brand}".lower(),
                year=int(p.year or 0),
                power=float(p.ps or 0),
                layout=layout,
                extra=f"Cr {p.price:,}" if p.price else "",
                brand=brand,
            ))
        dlg = CarPickerDialog(cars, title="Choose template car", parent=self)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        rid = dlg.selected()
        if rid is None:
            return
        try:
            idx = int(rid)
        except Exception:
            return
        self._select_template(idx)

    def _select_template(self, idx: int) -> None:
        try:
            self._on_template_changed_impl(idx)
        except Exception as e:
            import traceback
            self.status.showMessage(f"Template error: {e}", 8000)
            try:
                (Path.home() / "GTHC_car_creator_error.log").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except Exception:
                pass

    def _on_template_changed_impl(self, idx: Optional[int] = None) -> None:
        if idx is None:
            idx = self._template_index
        if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(self.previews):
            self.current = None
            self._template_index = -1
            self._clear_graphs("Choose a template car")
            return
        self._template_index = idx
        self.current = self.previews[int(idx)]
        self._ensure_curve_loaded(self.current)
        self.template_lab.setText(self.current.name)
        self.template_btn.setText(self.current.name)
        c = self.current
        self._seeding = True
        for w in (
            self.price_spin, self.year_spin, self.mass_spin, self.wb_spin,
            self.ps_spin, self.tq_spin, self.rev_spin,
            self.ps_slider, self.tq_slider, self.rev_slider, self.mass_slider,
        ):
            w.blockSignals(True)
        try:
            self.price_spin.setValue(int(c.price or 0))
            self.year_spin.setValue(int(c.year or 2000) if (c.year or 0) >= 1900 else 2000)
            self.label_edit.setText(f"{(c.name or c.label or 'car').split('(')[0].strip()} Custom")
            mass = int(c.mass or 0)
            self.mass_spin.setValue(max(self.mass_spin.minimum(), mass) if mass else self.mass_spin.minimum())
            wb = int(c.wheelbase or 0)
            self.wb_spin.setValue(max(self.wb_spin.minimum(), wb) if wb else self.wb_spin.minimum())
            ps = float(c.ps or 0)
            tq = float(c.torque or 0)
            rev = int(c.rev_limit or 0)
            # Expand slider ranges if template exceeds defaults
            if ps > self.ps_slider.maximum():
                self.ps_slider.setMaximum(int(ps) + 100)
            if tq * 10 > self.tq_slider.maximum():
                self.tq_slider.setMaximum(int(tq * 10) + 50)
            if rev > self.rev_slider.maximum():
                self.rev_slider.setMaximum(rev + 500)
            if mass > self.mass_slider.maximum():
                self.mass_slider.setMaximum(mass + 200)
            self.ps_spin.setValue(ps)
            self.tq_spin.setValue(tq)
            if rev >= self.rev_spin.minimum():
                self.rev_spin.setValue(rev)
            self.ps_slider.setValue(int(round(ps)))
            self.tq_slider.setValue(int(round(tq * 10)))
            self.rev_slider.setValue(rev if rev >= self.rev_slider.minimum() else self.rev_slider.minimum())
            self.mass_slider.setValue(mass if mass >= self.mass_slider.minimum() else self.mass_slider.minimum())
        finally:
            for w in (
                self.price_spin, self.year_spin, self.mass_spin, self.wb_spin,
                self.ps_spin, self.tq_spin, self.rev_spin,
                self.ps_slider, self.tq_slider, self.rev_slider, self.mass_slider,
            ):
                w.blockSignals(False)
        # class / drivetrain combos
        tidx = self.type_spin.findData(0)
        # type not on PreviewCar — leave default Road unless we store it later
        didx = self.drive_spin.findData(int(c.drive) if c.drive is not None else 0)
        if didx >= 0:
            self.drive_spin.setCurrentIndex(didx)
        for i, sp in enumerate(self.ratio_spins):
            sp.blockSignals(True)
            val = float(c.ratios[i]) if i < len(c.ratios) else 0.0
            sp.setValue(val)
            sp.blockSignals(False)
            if i < len(self.ratio_sliders):
                self.ratio_sliders[i].blockSignals(True)
                self.ratio_sliders[i].setValue(int(round(val * 100)))
                self.ratio_sliders[i].blockSignals(False)
        self._fill_curve_table(c)
        self.idle_spin.blockSignals(True)
        self.idle_spin.setValue(int(c.idle_rpm) if c.idle_rpm else 800)
        self.idle_spin.blockSignals(False)
        self._update_span_label()
        self._seeding = False
        # Baseline curves for dyno ghost overlay
        self._baseline_rpm = list(c.rpm or [])
        self._baseline_tq = list(c.torque_curve or [])
        self._baseline_pw = list(c.power_curve or [])
        self._fill_stats(c)
        self._update_summary()
        self._draw_dyno(c)
        self._draw_gearbox(c)

    def _update_summary(self) -> None:
        if not hasattr(self, "summary_lab"):
            return
        if not self.current:
            self.summary_lab.setText("Choose a template to begin.")
            return
        name = self.label_edit.text().strip() or "(unnamed)"
        ratios = self._read_ratios() if hasattr(self, "ratio_spins") else []
        asp = self.aspiration_combo.currentText() if hasattr(self, "aspiration_combo") else ""
        lines = [
            f"<b>{name}</b>",
            f"From: {self.current.name}",
            f"{self.ps_spin.value():.0f} PS · {self.tq_spin.value():.1f} kgf·m · {self.rev_spin.value()} rpm",
            f"{self.mass_spin.value()} kg · {self.drive_spin.currentText()} · {len(ratios) or '—'} gears",
        ]
        if asp:
            lines.append(asp)
        if self._dirty:
            lines.append("<i>Unsaved car(s) in memory</i>")
        self.summary_lab.setText("<br/>".join(lines))

    def _read_ratios(self) -> List[float]:
        ratios: List[float] = []
        for sp in self.ratio_spins:
            v = float(sp.value())
            if v > 0:
                ratios.append(v)
        return ratios

    def _update_span_label(self) -> None:
        ratios = self._read_ratios()
        if len(ratios) >= 2 and ratios[-1] > 0:
            self.span_lab.setText(f"Ratio span 1st→top: {ratios[0]/ratios[-1]:.2f}× · {len(ratios)} gears")
        elif ratios:
            self.span_lab.setText(f"{len(ratios)} gear(s)")
        else:
            self.span_lab.setText("Ratio span: —")

    def _reset_ratios_from_template(self) -> None:
        if not self.current:
            return
        self._seeding = True
        for i, sp in enumerate(self.ratio_spins):
            sp.setValue(float(self.current.ratios[i]) if i < len(self.current.ratios) else 0.0)
        self._seeding = False
        self._update_span_label()
        self._schedule_redraw(gear=True)

    def _on_ratio_edited(self, *_args) -> None:
        if getattr(self, "_seeding", False):
            return
        self._update_span_label()
        self._schedule_redraw(gear=True)

    def _gear_from_slider(self, idx: int, slider_val: int) -> None:
        if getattr(self, "_seeding", False):
            return
        ratio = slider_val / 100.0
        sp = self.ratio_spins[idx]
        if abs(sp.value() - ratio) < 1e-9:
            self._on_ratio_edited()
            return
        sp.blockSignals(True)
        sp.setValue(ratio)
        sp.blockSignals(False)
        self._on_ratio_edited()

    def _gear_from_spin(self, idx: int, spin_val: float) -> None:
        if getattr(self, "_seeding", False):
            return
        sl = self.ratio_sliders[idx]
        target = int(round(float(spin_val) * 100))
        if target > sl.maximum():
            sl.setMaximum(target + 50)
        sl.blockSignals(True)
        sl.setValue(target)
        sl.blockSignals(False)
        self._on_ratio_edited()

    def _gear_pack(self, factor: float) -> None:
        """Tighten or spread ratios around the geometric mean."""
        ratios = self._read_ratios()
        if len(ratios) < 2:
            return
        import math
        log_mean = sum(math.log(r) for r in ratios) / len(ratios)
        new = []
        for i, r in enumerate(ratios):
            # pull toward or away from mean
            lr = math.log(r)
            lr2 = log_mean + (lr - log_mean) * factor
            new.append(max(0.05, math.exp(lr2)))
        self._seeding = True
        for i, sp in enumerate(self.ratio_spins):
            val = new[i] if i < len(new) else 0.0
            sp.setValue(val)
            if i < len(self.ratio_sliders):
                self.ratio_sliders[i].setValue(int(round(val * 100)))
        self._seeding = False
        self._on_ratio_edited()


    def _fill_curve_table(self, c: "PreviewCar") -> None:
        rpm = list(c.rpm or [])
        tq = list(c.torque_curve or [])
        n = min(len(rpm), len(tq))
        pairs = sorted(((int(rpm[i]), float(tq[i])) for i in range(n)), key=lambda p: p[0])
        self._seeding = True
        self.curve_table.blockSignals(True)
        self.curve_table.setRowCount(0)
        for r, t in pairs:
            self._curve_append_row(r, t)
        self.curve_table.blockSignals(False)
        self._seeding = False
        self._curve_refresh_power_and_stats()

    def _curve_append_row(self, rpm: int, torque: float) -> int:
        row = self.curve_table.rowCount()
        self.curve_table.insertRow(row)

        rpm_sp = QSpinBox()
        rpm_sp.setRange(500, 20000)
        rpm_sp.setSingleStep(100)
        rpm_sp.setSuffix(" rpm")
        rpm_sp.setValue(int(rpm))
        rpm_sp.setMinimumWidth(100)
        rpm_sp.valueChanged.connect(self._on_curve_edited)

        tq_sp = QDoubleSpinBox()
        tq_sp.setRange(0.0, 400.0)
        tq_sp.setDecimals(2)
        tq_sp.setSingleStep(0.5)
        tq_sp.setSuffix(" kgf·m")
        tq_sp.setValue(float(torque))
        tq_sp.setMinimumWidth(110)
        tq_sp.valueChanged.connect(self._on_curve_edited)

        pw_item = QTableWidgetItem("—")
        pw_item.setFlags(pw_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        pw_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.curve_table.setCellWidget(row, 0, rpm_sp)
        self.curve_table.setCellWidget(row, 1, tq_sp)
        self.curve_table.setItem(row, 2, pw_item)
        return row

    def _read_curve_points(self):
        rpm, tq = [], []
        for i in range(self.curve_table.rowCount()):
            rsp = self.curve_table.cellWidget(i, 0)
            tsp = self.curve_table.cellWidget(i, 1)
            if rsp is None or tsp is None:
                continue
            r = int(rsp.value())
            t = float(tsp.value())
            if r > 0:
                rpm.append(r)
                tq.append(t)
        pairs = sorted(zip(rpm, tq), key=lambda x: x[0])
        if not pairs:
            return [], []
        return [p[0] for p in pairs], [p[1] for p in pairs]

    def _curve_refresh_power_and_stats(self) -> None:
        rpm, tq = self._read_curve_points()
        peak_i = -1
        peak_tq = -1.0
        peak_ps = -1.0
        peak_ps_i = -1
        for i in range(self.curve_table.rowCount()):
            rsp = self.curve_table.cellWidget(i, 0)
            tsp = self.curve_table.cellWidget(i, 1)
            item = self.curve_table.item(i, 2)
            if rsp is None or tsp is None or item is None:
                continue
            r = int(rsp.value())
            t = float(tsp.value())
            ps = (t * r) / 716.2 if r else 0.0
            item.setText(f"{ps:.1f}")
            # highlight peak torque
            if t > peak_tq:
                peak_tq = t
                peak_i = i
            if ps > peak_ps:
                peak_ps = ps
                peak_ps_i = i
        for i in range(self.curve_table.rowCount()):
            for col in range(3):
                w = self.curve_table.cellWidget(i, col)
                it = self.curve_table.item(i, col)
                if i == peak_i:
                    if it:
                        it.setBackground(QColor("#dbeafe"))
                else:
                    if it:
                        it.setBackground(QColor("#ffffff"))
        if hasattr(self, "curve_stats_lab"):
            if not rpm:
                self.curve_stats_lab.setText("No points")
            else:
                pr = rpm[peak_i] if 0 <= peak_i < len(rpm) else 0
                # peak_i is table row; map carefully
                # recompute from sorted pairs
                pairs = list(zip(rpm, tq))
                ti = max(range(len(pairs)), key=lambda j: pairs[j][1]) if pairs else 0
                pi = max(range(len(pairs)), key=lambda j: (pairs[j][1] * pairs[j][0]) / 716.2) if pairs else 0
                self.curve_stats_lab.setText(
                    f"{len(rpm)} pts · peak {pairs[ti][1]:.1f} kgf·m @ {pairs[ti][0]} rpm"
                    f" · { (pairs[pi][1]*pairs[pi][0])/716.2 :.0f} PS @ {pairs[pi][0]} rpm"
                )

    def _on_curve_edited(self, *_args) -> None:
        if getattr(self, "_seeding", False) or not self.current:
            return
        self._curve_refresh_power_and_stats()
        rpm, tq = self._read_curve_points()
        if rpm and tq:
            self._seeding = True
            self.tq_spin.setValue(max(tq))
            pw = [(t * r) / 716.2 for r, t in zip(rpm, tq)]
            if pw:
                self.ps_spin.setValue(max(pw))
            self._seeding = False
            self._stat_labels["Torque"].setText(f"{max(tq):.1f} kgf·m")
            if pw:
                self._stat_labels["Power"].setText(f"{max(pw):.0f} PS")
        if hasattr(self, "_update_summary"):
            self._update_summary()
        self._schedule_redraw(dyno=True, gear=True)

    def _curve_add_point(self) -> None:
        last_rpm, last_tq = 1000, 30.0
        n = self.curve_table.rowCount()
        if n > 0:
            rsp = self.curve_table.cellWidget(n - 1, 0)
            tsp = self.curve_table.cellWidget(n - 1, 1)
            if rsp:
                last_rpm = int(rsp.value()) + 500
            if tsp:
                last_tq = float(tsp.value())
        self._seeding = True
        self._curve_append_row(last_rpm, last_tq)
        self._seeding = False
        self._on_curve_edited()

    def _curve_insert_point(self) -> None:
        row = self.curve_table.currentRow()
        if row < 0 or row >= self.curve_table.rowCount() - 1:
            self._curve_add_point()
            return
        r0 = self.curve_table.cellWidget(row, 0)
        r1 = self.curve_table.cellWidget(row + 1, 0)
        t0 = self.curve_table.cellWidget(row, 1)
        t1 = self.curve_table.cellWidget(row + 1, 1)
        if not all((r0, r1, t0, t1)):
            self._curve_add_point()
            return
        mid_r = (int(r0.value()) + int(r1.value())) // 2
        mid_t = (float(t0.value()) + float(t1.value())) / 2.0
        # Rebuild with inserted point
        rpm, tq = self._read_curve_points()
        pairs = sorted(zip(rpm, tq), key=lambda x: x[0])
        pairs.append((mid_r, mid_t))
        pairs = sorted(pairs, key=lambda x: x[0])
        self._seeding = True
        self.curve_table.setRowCount(0)
        for r, t in pairs:
            self._curve_append_row(r, t)
        self._seeding = False
        self._on_curve_edited()

    def _curve_remove_point(self) -> None:
        row = self.curve_table.currentRow()
        if row < 0:
            return
        if self.curve_table.rowCount() <= 2:
            QMessageBox.information(self, "Curve", "Keep at least two points.")
            return
        self._seeding = True
        self.curve_table.removeRow(row)
        self._seeding = False
        self._on_curve_edited()

    def _curve_smooth(self) -> None:
        """3-point moving average on torque (endpoints fixed)."""
        rpm, tq = self._read_curve_points()
        if len(tq) < 3:
            return
        new_tq = [tq[0]]
        for i in range(1, len(tq) - 1):
            new_tq.append((tq[i - 1] + tq[i] + tq[i + 1]) / 3.0)
        new_tq.append(tq[-1])
        self._seeding = True
        self.curve_table.setRowCount(0)
        for r, t in zip(rpm, new_tq):
            self._curve_append_row(r, t)
        self._seeding = False
        self._on_curve_edited()

    def _curve_scale_torque(self, factor: float) -> None:
        self._seeding = True
        for i in range(self.curve_table.rowCount()):
            tsp = self.curve_table.cellWidget(i, 1)
            if tsp:
                tsp.setValue(max(0.0, float(tsp.value()) * factor))
        self._seeding = False
        self._on_curve_edited()

    def _curve_reset(self) -> None:
        if self.current:
            self._fill_curve_table(self.current)
            self._on_curve_edited()

    def _on_stats_edited(self, *_args) -> None:
        if getattr(self, "_seeding", False) or not self.current:
            return
        try:
            self._on_stats_edited_impl()
        except Exception as e:
            self.status.showMessage(f"Preview update failed: {e}", 5000)

    def _on_stats_edited_impl(self) -> None:
        c = self.current
        self._stat_labels["Power"].setText(f"{self.ps_spin.value():.0f} PS" if self.ps_spin.value() else "—")
        self._stat_labels["Torque"].setText(f"{self.tq_spin.value():.1f} kgf·m" if self.tq_spin.value() else "—")
        self._stat_labels["Rev limit"].setText(f"{self.rev_spin.value():,} rpm" if self.rev_spin.value() else "—")
        self._stat_labels["Mass"].setText(f"{self.mass_spin.value():,} kg" if self.mass_spin.value() else "—")
        self._stat_labels["Wheelbase"].setText(f"{self.wb_spin.value()} mm" if self.wb_spin.value() else "—")
        d = self.drive_spin.currentData()
        if d is None:
            d = self.drive_spin.currentIndex()
        self._stat_labels["Layout"].setText(DRIVE_NAMES[d] if isinstance(d, int) and 0 <= d < len(DRIVE_NAMES) else "—")
        self._update_summary()
        self._schedule_redraw(dyno=True, gear=True)

    def _fill_stats(self, c: PreviewCar) -> None:
        def set_(key: str, text: str) -> None:
            self._stat_labels[key].setText(text)

        set_("Power", f"{c.ps:.0f} PS" if c.ps else "—")
        set_("Torque", f"{c.torque:.1f} kgf·m" if c.torque else "—")
        set_("Rev limit", f"{c.rev_limit:,} rpm" if c.rev_limit else "—")
        set_("Mass", f"{c.mass:,} kg" if c.mass else "—")
        set_("Wheelbase", f"{c.wheelbase} mm" if c.wheelbase else "—")
        if c.drive is not None and 0 <= c.drive < len(DRIVE_NAMES):
            set_("Layout", DRIVE_NAMES[c.drive])
        else:
            set_("Layout", "—")
        set_("Gears", f"{c.gears}-spd" if c.gears else "—")
        set_("Price", f"Cr {c.price:,}" if c.price else "—")
        set_("Year", str(c.year) if c.year else "—")

    def _clear_graphs(self, msg: str) -> None:
        if HAS_MPL and self.dyno_ax is not None:
            self.dyno_ax.clear()
            self.dyno_ax2.clear()
            self.dyno_ax.set_facecolor("#fafbfc")
            self.dyno_ax.text(
                0.5, 0.5, msg, ha="center", va="center",
                transform=self.dyno_ax.transAxes, color="#9ca3af",
            )
            self.dyno_ax.set_xticks([])
            self.dyno_ax.set_yticks([])
            self.dyno_ax2.set_yticks([])
            self.dyno_fig.tight_layout()
            self.dyno_canvas.draw_idle()
        if HAS_MPL and self.gear_ax is not None:
            self.gear_ax.clear()
            self.gear_ax.set_facecolor("#fafbfc")
            self.gear_ax.text(
                0.5, 0.5, msg, ha="center", va="center",
                transform=self.gear_ax.transAxes, color="#9ca3af",
            )
            self.gear_ax.set_xticks([])
            self.gear_ax.set_yticks([])
            self.gear_fig.tight_layout()
            self.gear_canvas.draw_idle()

    def _on_mpl_resize(self, which: str = "") -> None:
        """Keep matplotlib figures fitting the canvas after window resize."""
        try:
            if which in ("", "dyno") and self.dyno_fig is not None:
                self.dyno_fig.tight_layout()
                if self.dyno_canvas is not None:
                    self.dyno_canvas.draw_idle()
            if which in ("", "gear") and self.gear_fig is not None:
                self.gear_fig.tight_layout()
                if self.gear_canvas is not None:
                    self.gear_canvas.draw_idle()
        except Exception:
            pass

    def _scaled_curves(self, c: PreviewCar):

        """Curve from the editable table (or template), scaled to peak spins, cut at rev limit."""
        # Prefer live table points
        if hasattr(self, "curve_table") and self.curve_table.rowCount() > 0:
            rpm, tq = self._read_curve_points()
            pw = [(t * r) / 716.2 for r, t in zip(rpm, tq)]
        else:
            rpm = list(c.rpm or [])
            tq = list(c.torque_curve or [])
            pw = list(c.power_curve or [])
        if not rpm or not tq:
            return [], [], []
        peak_tq = float(self.tq_spin.value()) if hasattr(self, "tq_spin") else 0.0
        peak_ps = float(self.ps_spin.value()) if hasattr(self, "ps_spin") else 0.0
        rev = int(self.rev_spin.value()) if hasattr(self, "rev_spin") else 0
        base_tq = max(tq) if tq else 0.0
        base_pw = max(pw) if pw else 0.0
        # If table peaks already match spins, scale ≈ 1
        tq_scale = (peak_tq / base_tq) if (base_tq > 0 and peak_tq > 0) else 1.0
        pw_scale = (peak_ps / base_pw) if (base_pw > 0 and peak_ps > 0) else tq_scale
        out_rpm, out_tq, out_pw = [], [], []
        for i, r in enumerate(rpm):
            if rev and r > rev:
                break
            out_rpm.append(r)
            out_tq.append(tq[i] * tq_scale)
            if i < len(pw):
                out_pw.append(pw[i] * pw_scale)
            else:
                out_pw.append((tq[i] * tq_scale * r) / 716.2)
        return out_rpm, out_tq, out_pw

    def _draw_dyno(self, c: PreviewCar) -> None:
        if not HAS_MPL or self.dyno_ax is None:
            return
        self.dyno_ax.clear()
        self.dyno_ax2.clear()
        self.dyno_ax.set_facecolor("#fafbfc")
        rpm, tq, pw = self._scaled_curves(c)
        if not rpm or not tq:
            self.dyno_ax.text(
                0.5, 0.5, "No engine curve data", ha="center", va="center",
                transform=self.dyno_ax.transAxes, color="#9ca3af",
            )
            self.dyno_ax.set_xticks([])
            self.dyno_ax.set_yticks([])
            self.dyno_ax2.set_yticks([])
        else:
            # Ghost baseline (template) under edited curve
            br = getattr(self, "_baseline_rpm", None) or []
            bt = getattr(self, "_baseline_tq", None) or []
            bp = getattr(self, "_baseline_pw", None) or []
            if br and bt and len(br) == len(bt):
                self.dyno_ax.plot(br, bt, color="#93c5fd", lw=1.2, ls="--", alpha=0.7, label="Template tq")
            if br and bp and len(br) == len(bp):
                self.dyno_ax2.plot(br, bp, color="#fca5a5", lw=1.2, ls="--", alpha=0.7, label="Template PS")
            self.dyno_ax.plot(rpm, tq, color="#2563eb", lw=2.2, label="Torque")
            if pw and len(pw) == len(rpm):
                self.dyno_ax2.plot(rpm, pw, color="#dc2626", lw=2.2, label="Power")
            # Rev-limit marker so the control is visibly reflected
            rev = int(self.rev_spin.value()) if hasattr(self, "rev_spin") else 0
            if rev > 0:
                self.dyno_ax.axvline(
                    rev, color="#64748b", ls="--", lw=1.2, alpha=0.85, label="Rev limit",
                )
                # Ensure axis includes the marker even if curve ends earlier
                xmax = max(max(rpm), rev) * 1.02
                self.dyno_ax.set_xlim(left=min(rpm) * 0.98 if rpm else 0, right=xmax)
            self.dyno_ax.set_xlabel("RPM", fontsize=9)
            self.dyno_ax.set_ylabel("Torque (kgf·m)", color="#2563eb", fontsize=9)
            self.dyno_ax2.set_ylabel("Power (PS)", color="#dc2626", fontsize=9)
            self.dyno_ax.tick_params(labelsize=8)
            self.dyno_ax2.tick_params(labelsize=8)
            self.dyno_ax.grid(True, alpha=0.25)
            lines1, lab1 = self.dyno_ax.get_legend_handles_labels()
            lines2, lab2 = self.dyno_ax2.get_legend_handles_labels()
            if lines1 or lines2:
                self.dyno_ax.legend(lines1 + lines2, lab1 + lab2, loc="upper left", fontsize=8)
        try:
            self.dyno_fig.tight_layout()
        except Exception:
            pass
        try:
            self.dyno_canvas.draw_idle()
        except Exception:
            pass

    def _draw_gearbox(self, c: Optional[PreviewCar]) -> None:
        """Geared power graph: engine power mapped through each gear vs relative speed.

        For each gear, X = engine_RPM / ratio (proxy for road speed), Y = power (kW).
        Curves end at the redline. Similar to Team-BHP style geared power charts.
        """
        if not HAS_MPL or self.gear_ax is None:
            return
        self.gear_ax.clear()
        self.gear_ax.set_facecolor("#fafbfc")

        ratios = self._read_ratios() if hasattr(self, "ratio_spins") else []
        if not ratios and c is not None:
            ratios = [r for r in c.ratios if r and r > 0]

        if c:
            rpm, _tq, power_ps = self._scaled_curves(c)
        else:
            rpm, power_ps = [], []
        rev = self.rev_spin.value() if hasattr(self, "rev_spin") and self.rev_spin.value() else (
            c.rev_limit if c and c.rev_limit else (max(rpm) if rpm else 0)
        )

        if not ratios or not rpm or not power_ps or len(rpm) != len(power_ps):
            self.gear_ax.text(
                0.5, 0.5, "Need engine curve + gear ratios",
                ha="center", va="center",
                transform=self.gear_ax.transAxes, color="#9ca3af",
            )
            self.gear_ax.set_xticks([])
            self.gear_ax.set_yticks([])
            self.gear_fig.tight_layout()
            self.gear_canvas.draw_idle()
            return

        # Convert PS → kW for Y axis (as in the reference graph)
        power_kw = [p * 0.73549875 for p in power_ps]

        colors = GEAR_COLORS
        labels = [f"{GEAR_LABELS[i]} Gear" for i in range(len(ratios))]

        max_x = 0.0
        for i, ratio in enumerate(ratios):
            if ratio <= 0:
                continue
            xs, ys = [], []
            for r, pkw in zip(rpm, power_kw):
                if rev and r > rev:
                    break
                # Relative road-speed proxy (engine rpm / gear ratio)
                x = r / ratio
                xs.append(x)
                ys.append(pkw)
            if not xs:
                continue
            # Vertical drop at redline end for visual shift point
            xs.append(xs[-1])
            ys.append(0.0)
            col = colors[i % len(colors)]
            self.gear_ax.plot(xs, ys, color=col, lw=1.8, label=labels[i])
            max_x = max(max_x, max(xs))

        self.gear_ax.set_xlabel("Relative speed (RPM ÷ ratio)", fontsize=9)
        self.gear_ax.set_ylabel("Power (kW)", fontsize=9)
        self.gear_ax.tick_params(labelsize=8)
        self.gear_ax.grid(True, alpha=0.3)
        self.gear_ax.set_ylim(bottom=0)
        if max_x > 0:
            self.gear_ax.set_xlim(left=0, right=max_x * 1.05)
        leg = self.gear_ax.legend(loc="upper right", fontsize=7, framealpha=0.9)
        self.gear_ax.set_title("Geared Power Graph", fontsize=10, fontweight="600")
        try:
            self.gear_fig.tight_layout()
        except Exception:
            pass
        try:
            self.gear_canvas.draw_idle()
        except Exception:
            pass

    # -------------------------------------------------------------- create / save
    def _create(self) -> None:
        if not self.db or not self.current:
            QMessageBox.information(self, "Create", "Load a database and choose a template first.")
            return
        name = self.label_edit.text().strip() or "(unnamed)"
        reply = QMessageBox.question(
            self,
            "Create car?",
            f"Clone “{self.current.name}” into a new car “{name}”?\n\n"
            "Changes stay in memory until you Save database…",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.game == "gt3":
            self._create_gt3()
        else:
            self._create_gt4()

    def _create_gt3(self) -> None:
        from gt_engine import (
            clone_car_gt3, car_hash, hex64,
            FineTuneData, FineTuneEngine, FineTuneChassis, FineTuneDrivetrain, FineTuneInfo,
            apply_finetune, read_engine_finetune,
        )

        assert self.current is not None
        db = self.db["db"]
        ti = int(self.current.raw)
        try:
            new_i = clone_car_gt3(
                db,
                ti,
                price=self.price_spin.value(),
                year=self.year_spin.value(),
                car_type=int(self.type_spin.currentData() or 0),
                flags=self.flags_spin.value(),
            )
        except Exception as e:
            QMessageBox.warning(self, "Create failed", str(e))
            return
        # Apply edited stats onto the new row
        ratios = self._read_ratios()
        crpm, ctq = self._read_curve_points()
        if not crpm:
            crpm = list(self.current.rpm)
            ctq = list(self.current.torque_curve)
        eng = FineTuneEngine(
            rpm=crpm,
            torque=ctq,
            peak_ps=int(self.ps_spin.value()) if self.ps_spin.value() else None,
            peak_torque=self.tq_spin.value() or None,
            rev_limit=self.rev_spin.value() or None,
            idle_rpm=self.idle_spin.value() or None,
        )
        dt_kwargs = {f"ratio_{i+1}": (ratios[i] if i < len(ratios) else None) for i in range(8)}
        ft = FineTuneData(
            engine=eng,
            chassis=FineTuneChassis(
                mass=self.mass_spin.value() or None,
                wheelbase=self.wb_spin.value() or None,
            ),
            drivetrain=FineTuneDrivetrain(
                drive=int(self.drive_spin.currentData() if self.drive_spin.currentData() is not None else 0),
                gears=len(ratios) or None,
                **dt_kwargs,
            ),
            info=FineTuneInfo(
                price=self.price_spin.value(),
                year=self.year_spin.value(),
                car_type=int(self.type_spin.currentData() or 0),
                flags=self.flags_spin.value(),
            ),
        )
        try:
            apply_finetune(db, new_i, ft)
        except Exception as e:
            QMessageBox.warning(self, "Stats apply warning", str(e))

        # Custom display name into unicode string table (in memory)
        display = self.label_edit.text().strip()
        uni = self.db.get("uni")
        if display and uni is not None:
            from gt_engine import set_car_display_name
            uni = set_car_display_name(db, new_i, uni, display)
            self.db["uni"] = uni
            self.db["uni_dirty"] = True

        new_hex = hex64(car_hash(db, new_i))
        # Append preview in-memory (do NOT reload from disk)
        rpm, tq, pw = self._scaled_curves(self.current) if self.current else ([], [], [])
        ratios = self._read_ratios()
        pv = PreviewCar(
            game="gt3",
            key=new_hex,
            name=display or f"{self.current.name} (new)",
            label=new_hex,
            year=self.year_spin.value(),
            price=self.price_spin.value(),
            ps=self.ps_spin.value() or None,
            torque=self.tq_spin.value() or None,
            rev_limit=self.rev_spin.value() or None,
            mass=self.mass_spin.value() or None,
            wheelbase=self.wb_spin.value() or None,
            drive=int(self.drive_spin.currentData() or 0),
            gears=len(ratios) or None,
            ratios=ratios,
            rpm=rpm,
            torque_curve=tq,
            power_curve=pw,
            idle_rpm=self.idle_spin.value() or None,
            raw=new_i,
        )
        self.previews.append(pv)
        self._set_dirty(True)
        self.template_btn.setText(f"Choose template car…  ({len(self.previews)} cars)")
        self._select_template(len(self.previews) - 1)
        self.status.showMessage(
            f"Created “{pv.name}” in memory — Save database… to write files",
            8000,
        )
        QMessageBox.information(
            self,
            "Car created (in memory)",
            f"New car “{pv.name}” is ready in memory.\n"
            f"Index #{new_i}  ·  {new_hex[:16]}…\n\n"
            "It will disappear if you reload without saving.\n"
            "Click Save database… to write paramdb"
            + (" + name strings." if self.db.get("uni_dirty") else "."),
        )

    def _create_gt4(self) -> None:
        from gt4_engine import (
            clone_car_gt4, apply_finetune_gt4, read_finetune_for_car,
            FineTuneData, FineTuneEngine, FineTuneChassis, FineTuneDrivetrain, FineTuneInfo,
        )

        assert self.current is not None
        db = self.db["db"]
        template = self.current.raw
        label = self.label_edit.text().strip() or f"{template.label}_new"
        try:
            new_car = clone_car_gt4(
                db,
                template,
                price=self.price_spin.value(),
                year=self.year_spin.value(),
                label=label,
            )
        except Exception as e:
            QMessageBox.warning(self, "Create failed", str(e))
            return
        ratios = self._read_ratios()
        crpm, ctq = self._read_curve_points()
        if not crpm:
            crpm = list(self.current.rpm)
            ctq = list(self.current.torque_curve)
        eng = FineTuneEngine(
            rpm=crpm,
            torque=ctq,
            peak_ps=self.ps_spin.value() or None,
            peak_torque=self.tq_spin.value() or None,
            rev_limit=self.rev_spin.value() or None,
            idle_rpm=self.idle_spin.value() or None,
        )
        dt_kwargs = {f"ratio_{i+1}": (ratios[i] if i < len(ratios) else None) for i in range(8)}
        ft = FineTuneData(
            engine=eng,
            chassis=FineTuneChassis(
                mass=self.mass_spin.value() or None,
                wheelbase=self.wb_spin.value() or None,
            ),
            drivetrain=FineTuneDrivetrain(
                drive=int(self.drive_spin.currentData() if self.drive_spin.currentData() is not None else 0),
                gears=len(ratios) or None,
                **dt_kwargs,
            ),
            info=FineTuneInfo(price=self.price_spin.value(), year=self.year_spin.value()),
        )
        try:
            apply_finetune_gt4(db, new_car, ft)
        except Exception as e:
            QMessageBox.warning(self, "Stats apply warning", str(e))

        display = self.label_edit.text().strip() or new_car.name
        new_car.name = display
        rpm, tq, pw = self._scaled_curves(self.current) if self.current else ([], [], [])
        ratios = self._read_ratios()
        pv = PreviewCar(
            game="gt4",
            key=new_car.row_id,
            name=display,
            label=new_car.label,
            year=self.year_spin.value(),
            price=self.price_spin.value(),
            ps=self.ps_spin.value() or None,
            torque=self.tq_spin.value() or None,
            rev_limit=self.rev_spin.value() or None,
            mass=self.mass_spin.value() or None,
            wheelbase=self.wb_spin.value() or None,
            drive=int(self.drive_spin.currentData() or 0),
            gears=len(ratios) or None,
            ratios=ratios,
            rpm=rpm,
            torque_curve=tq,
            power_curve=pw,
            idle_rpm=self.idle_spin.value() or None,
            raw=new_car,
        )
        self.previews.append(pv)
        self._set_dirty(True)
        self.template_btn.setText(f"Choose template car…  ({len(self.previews)} cars)")
        self._select_template(len(self.previews) - 1)
        self.status.showMessage(
            f"Created “{display}” in memory — Save database… to write SpecDB",
            8000,
        )
        QMessageBox.information(
            self,
            "Car created (in memory)",
            f"New car “{display}” is ready in memory.\n"
            f"GENERIC_CAR id: {new_car.row_id}\n"
            f"DEFAULT_PARTS id: {new_car.default_parts_id}\n\n"
            "It will disappear if you reload without saving.\n"
            "Click Save database… to write SpecDB tables.",
        )


    def _save(self) -> None:
        if not self.db:
            QMessageBox.information(self, "Save", "Nothing loaded.")
            return
        if not self._dirty:
            reply = QMessageBox.question(
                self,
                "Save",
                "No new cars marked since load. Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if self.game == "gt3":
            from gt_engine import write_gtar, write_stdb

            path = self.db["path"]
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.is_file():
                bak.write_bytes(path.read_bytes())
            data = write_gtar(self.db["db"].arc)
            path.write_bytes(data)
            notes = [f"Wrote {path.name}"]
            # Unicode name table
            if self.db.get("uni_dirty") and self.db.get("uni") is not None:
                # Find matching paramunistr path
                folder = path.parent
                suffix = self.db.get("suffix") or ""
                candidates = []
                if suffix:
                    candidates.append(folder / f"paramunistr_{suffix}.db")
                candidates += [
                    folder / "paramunistr_us.db",
                    folder / "paramunistr.db",
                    folder / "paramunistr_eu.db",
                ]
                uni_path = next((p for p in candidates if p.is_file()), None)
                if uni_path is None:
                    # write next to paramdb
                    uni_path = folder / (f"paramunistr_{suffix}.db" if suffix else "paramunistr.db")
                uni_bak = uni_path.with_suffix(uni_path.suffix + ".bak")
                if uni_path.is_file() and not uni_bak.is_file():
                    uni_bak.write_bytes(uni_path.read_bytes())
                uni_path.write_bytes(write_stdb(self.db["uni"]))
                notes.append(f"Wrote {uni_path.name} (custom names)")
            self._set_dirty(False)
            self.status.showMessage(" · ".join(notes), 6000)
            QMessageBox.information(self, "Saved", "\n".join(notes) + f"\nBackup: {bak.name}")
        else:
            from gt4_engine import save_default_parts

            db = self.db["db"]
            # Ensure GENERIC_CAR is marked dirty via existing append path
            out = save_default_parts(db, backup=True)
            # Also write generic_car if the helper does not
            try:
                if db.generic_car is not None and db.generic_car.dirty_rows:
                    gc_path = Path(self.folder) / "GENERIC_CAR.dbt"
                    if gc_path.is_file():
                        bak = gc_path.with_suffix(".dbt.bak")
                        if not bak.is_file():
                            bak.write_bytes(gc_path.read_bytes())
                        gc_path.write_bytes(db.generic_car.to_uncompressed_bytes())
            except Exception as e:
                QMessageBox.warning(self, "GENERIC_CAR save", str(e))
            self._set_dirty(False)
            self.status.showMessage(f"Wrote SpecDB under {self.folder}", 5000)
            QMessageBox.information(
                self,
                "Saved",
                f"Wrote SpecDB tables.\n{out}",
            )



def main() -> int:
    import os

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.design import apply_app_theme

    apply_app_theme(app)
    win = CarCreatorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
