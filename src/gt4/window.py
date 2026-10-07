from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QPalette,
)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from ui.folder_paths import get_folder, get_recent, set_folder
from ui.design import (
    APP_STYLE,
    COLORS,
    card as _card,
    donor_button as _donor_btn,
    rule as _rule,
    set_donor_button,
)
from ui.car_picker import CarPickerDialog, PickerCar
try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    FigureCanvasQTAgg = None  # type: ignore
    Figure = None  # type: ignore
from gt4.gt4_engine import (
    HYBRID_PARTS,
    CarInfo,
    SpecDB,
    apply_part_swap,
    load_specdb,
    engine_curve_for_car,
    EngineCurve,
    save_default_parts,
    write_hybrids_summary,
    backup_default_parts,
    export_hybrids_zip,
)

PATHS_KEY = "gt4"

GROUPS = [
    {
        "key": "engine",
        "label": "Engine & power",
        "parts": [
            ("Engine", "Engine"),
            ("NATune", "NA Tune"),
            ("Turbo", "Turbo"),
            ("Muffler", "Muffler"),
            ("Computer", "Computer"),
            ("Intercooler", "Intercooler"),
            ("Displacement", "Displacement"),
        ],
    },
    {
        "key": "drivetrain",
        "label": "Drivetrain & gearing",
        "parts": [
            ("DriveTrain", "Drivetrain"),
            ("Gear", "Gear"),
            ("Clutch", "Clutch"),
            ("Flywheel", "Flywheel"),
            ("PropellerShaft", "Propeller shaft"),
            ("LSD", "LSD"),
        ],
    },
    {
        "key": "chassis",
        "label": "Chassis, suspension & brakes",
        "parts": [
            ("Chassis", "Chassis"),
            ("Suspension", "Suspension"),
            ("Brake", "Brake"),
            ("BrakeCtrl", "Brake controller"),
            ("Steer", "Steering"),
            ("Lightweight", "Lightweight"),
            ("RacingModify", "Racing modify"),
            ("ASCC", "ASCC"),
            ("TCSC", "TCSC"),
        ],
    },
    {
        "key": "tyres",
        "label": "Tyres",
        "parts": [
            ("FrontTire", "Front tyre"),
            ("RearTire", "Rear tyre"),
            ("F_Tire_G", "Front tyre (G)"),
            ("R_Tire_G", "Rear tyre (G)"),
        ],
    },
]


def _label(text: str, obj: str = "") -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    return lab


@dataclass
class PlanRecord:
    id: int
    target_id: int
    target_name: str
    mode: str  # "link" for now
    picks: Dict[str, int]  # part key -> donor car id
    summary: str


class GT4HybridWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GT4 Hybrid Creator")
        self.resize(1140, 740)
        self.setMinimumSize(900, 540)
        self.setStyleSheet(APP_STYLE)
        self.setAcceptDrops(True)

        self.db: Optional[SpecDB] = None
        self.folder: Optional[Path] = None
        self.target_id: Optional[int] = None
        self.mode: str = "link"
        self.group: Dict[str, Optional[int]] = {}  # group key -> donor car id
        self.parts: Dict[str, Optional[int]] = {}  # part key -> donor car id or "" keep
        self.open_groups: Dict[str, bool] = {}
        self.plans: List[PlanRecord] = []
        self.next_id = 1
        self._saved_dirty_count = 0  # dirty rows at last successful save
        self._stock_parts: Dict[int, Dict[str, Tuple[int, int]]] = {}

        self._build_ui()
        QTimer.singleShot(80, self._try_load_saved)

    def _build_ui(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        self.addToolBar(tb)

        act = QAction("Change folder…", self)
        act.setShortcut(QKeySequence.StandardKey.Open)
        act.triggered.connect(self._choose_folder)
        tb.addAction(act)

        act_recent = QAction("Recent", self)
        act_recent.triggered.connect(self._show_recent_menu)
        tb.addAction(act_recent)

        act_bak = QAction("Backup now…", self)
        act_bak.setShortcut(QKeySequence("Ctrl+B"))
        act_bak.triggered.connect(self._backup_now)
        tb.addAction(act_bak)

        act_save = QAction("Save", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._save_hybrids)
        tb.addAction(act_save)

        tb.addSeparator()
        self.toolbar_path = _label("No SpecDB folder", "path")
        self.toolbar_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.toolbar_path.setMaximumWidth(420)
        tb.addWidget(self.toolbar_path)
        tb.addSeparator()
        self.toolbar_count = _label("", "tag")
        tb.addWidget(self.toolbar_count)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        head = QHBoxLayout()
        head.addWidget(_label("GT4 Hybrid Creator", "title"))
        head.addStretch()
        root.addLayout(head)

        self.empty_state = _card()
        es = QVBoxLayout(self.empty_state)
        es.setContentsMargins(24, 32, 24, 32)
        es.setSpacing(8)
        es.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es.addWidget(
            _label("Open a SpecDB folder to get started", "cardTitle"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        hint = _label(
            "Select a folder such as GT4_PREMIUM_US2560 (GENERIC_CAR.dbt, DEFAULT_PARTS.dbt).",
            "muted",
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        es.addWidget(hint)
        btn = QPushButton("Open SpecDB folder…")
        btn.setObjectName("primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedWidth(180)
        btn.clicked.connect(self._choose_folder)
        es.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_state)

        self.work_area = QWidget()
        wl = QVBoxLayout(self.work_area)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        wl.addWidget(split)
        root.addWidget(self.work_area, 1)

        left = QWidget()
        left.setMinimumWidth(340)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        tcard = _card()
        tl = QVBoxLayout(tcard)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(2)
        tl.addWidget(_label("Car to change", "cardTitle"))
        tl.addWidget(_label("TARGET", "fieldLabel"))
        self.target_btn = _donor_btn("Choose a car")
        self.target_btn.clicked.connect(lambda: self._pick("target"))
        tl.addWidget(self.target_btn)
        self.target_hint = _label(
            "Keeps its body and model. Mechanical parts come from donors below.",
            "muted",
        )
        self.target_hint.setWordWrap(True)
        tl.addWidget(self.target_hint)
        self.quick_btn = QPushButton("Copy all parts from one car…")
        self.quick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_btn.clicked.connect(lambda: self._pick("all"))
        self.quick_btn.setEnabled(False)
        tl.addWidget(self.quick_btn)
        ll.addWidget(tcard)

        self.groups_scroll = QScrollArea()
        self.groups_scroll.setWidgetResizable(True)
        self.groups_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.groups_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.groups_widget = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_widget)
        self.groups_layout.setContentsMargins(0, 0, 2, 0)
        self.groups_layout.setSpacing(4)
        self.groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groups_scroll.setWidget(self.groups_widget)
        ll.addWidget(self.groups_scroll, 2)

        ccard = _card()
        cl = QVBoxLayout(ccard)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(3)
        ch = QHBoxLayout()
        ch.addWidget(_label("Hybrid list", "cardTitle"))
        ch.addStretch()
        self.changes_count = _label("0", "tag")
        ch.addWidget(self.changes_count)
        cl.addLayout(ch)

        self.changes_table = QTableWidget(0, 4)
        self.changes_table.setHorizontalHeaderLabels(["Target", "Parts", "Mode", "Summary"])
        chdr = self.changes_table.horizontalHeader()
        chdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        chdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        chdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        chdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.changes_table.verticalHeader().setVisible(False)
        self.changes_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.changes_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.changes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.changes_table.setMinimumHeight(100)
        self.changes_table.doubleClicked.connect(self._edit_plan)
        cl.addWidget(self.changes_table, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.dl_btn = QPushButton("Save hybrids…")
        self.dl_btn.setObjectName("primary")
        self.dl_btn.setEnabled(False)
        self.dl_btn.setToolTip(
            "Write into SpecDB, or export a ZIP that leaves the folder unchanged."
        )
        self.dl_btn.clicked.connect(self._save_hybrids)
        row.addWidget(self.dl_btn)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setToolTip("Reload this hybrid into the editor")
        self.edit_btn.clicked.connect(self._edit_plan)
        row.addWidget(self.edit_btn)
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.clicked.connect(self._duplicate_plan)
        row.addWidget(self.dup_btn)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(self._remove_plan)
        row.addWidget(self.remove_btn)
        cl.addLayout(row)
        cl.addWidget(
            _label(
                "Save writes uncompressed DEFAULT_PARTS.dbt. ZIP export leaves the folder untouched.",
                "muted",
            )
        )
        self.save_banner = _label("", "successBanner")
        self.save_banner.setVisible(False)
        self.save_banner.setWordWrap(True)
        cl.addWidget(self.save_banner)
        ll.addWidget(ccard, 1)
        split.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(380)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        scard = _card()
        sl = QVBoxLayout(scard)
        sl.setContentsMargins(8, 6, 8, 6)
        sl.setSpacing(4)

        sh = QHBoxLayout()
        self.spec_title = _label("Spec sheet", "cardTitle")
        sh.addWidget(self.spec_title)
        sh.addStretch()
        self.spec_tag = _label("", "tag")
        sh.addWidget(self.spec_tag)
        sl.addLayout(sh)

        self.spec_empty = _label("Choose a car to see details.", "muted")
        sl.addWidget(self.spec_empty)

        self.spec_table = QTableWidget(0, 4)
        self.spec_table.setHorizontalHeaderLabels(["Spec", "Stock", "Hybrid", "Δ"])
        hdr = self.spec_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.spec_table.verticalHeader().setVisible(False)
        self.spec_table.verticalHeader().setDefaultSectionSize(22)
        self.spec_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.spec_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.spec_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.spec_table.setShowGrid(False)
        self.spec_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sl.addWidget(self.spec_table, 2)

        self.dyno_frame = QFrame()
        self.dyno_frame.setObjectName("card")
        self.dyno_frame.setMinimumHeight(220)
        self.dyno_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dyno_l = QVBoxLayout(self.dyno_frame)
        dyno_l.setContentsMargins(2, 2, 2, 2)
        dyno_l.setSpacing(0)
        if HAS_MPL:
            self.dyno_fig = Figure(figsize=(5.2, 2.8), dpi=100)
            self.dyno_fig.patch.set_facecolor("#ffffff")
            self.dyno_ax = self.dyno_fig.add_subplot(111)
            self.dyno_ax2 = self.dyno_ax.twinx()
            self.dyno_canvas = FigureCanvasQTAgg(self.dyno_fig)
            self.dyno_canvas.setMinimumHeight(200)
            self.dyno_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            dyno_l.addWidget(self.dyno_canvas)
            self._clear_dyno()
        else:
            self.dyno_fig = self.dyno_ax = self.dyno_ax2 = self.dyno_canvas = None
            miss = _label("Install matplotlib for the dynograph:  pip install matplotlib", "muted")
            miss.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dyno_l.addWidget(miss)
        sl.addWidget(self.dyno_frame, 3)

        self.plan_summary = _label("", "muted")
        self.plan_summary.setWordWrap(True)
        self.plan_summary.setMaximumHeight(36)
        sl.addWidget(self.plan_summary)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.mode_group = QButtonGroup(self)
        self.radio_link = QRadioButton("Link to donor parts")
        self.radio_link.setToolTip(
            "DEFAULT_PARTS keys point at the donor part rows. Recommended for SpecDB."
        )
        self.radio_link.setChecked(True)
        self.mode_group.addButton(self.radio_link)
        mode_row.addWidget(self.radio_link)
        mode_row.addStretch()
        self.apply_btn = QPushButton("Add to list")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_hybrid)
        mode_row.addWidget(self.apply_btn)
        sl.addLayout(mode_row)

        rl.addWidget(scard, 1)

        split.addWidget(right)
        split.setSizes([560, 480])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.load_bar = QProgressBar()
        self.load_bar.setMaximumWidth(140)
        self.load_bar.setFixedHeight(12)
        self.load_bar.setTextVisible(False)
        self.load_bar.setVisible(False)
        self.status.addPermanentWidget(self.load_bar)
        self.work_area.setVisible(False)

    def _try_load_saved(self) -> None:
        saved = get_folder(PATHS_KEY)
        if saved and saved.is_dir():
            self._load_folder(saved, quiet=True)
        else:
            QTimer.singleShot(50, self._choose_folder)

    def _elide_path(self, path: Path, max_chars: int = 48) -> str:
        s = str(path)
        if len(s) <= max_chars:
            return s
        return "…" + s[-(max_chars - 1) :]

    def _show_recent_menu(self) -> None:
        menu = QMenu(self)
        recent = get_recent(PATHS_KEY)
        if not recent:
            act = menu.addAction("No recent folders")
            act.setEnabled(False)
        else:
            for p in recent:
                act = menu.addAction(str(p))
                act.triggered.connect(lambda checked=False, path=p: self._load_folder(path))
        menu.exec(self.mapToGlobal(QPoint(80, 40)))

    def _backup_now(self) -> None:
        if not self.db:
            QMessageBox.information(self, "Backup", "Open a SpecDB folder first.")
            return
        try:
            bak = backup_default_parts(self.db)
        except Exception as e:
            QMessageBox.critical(self, "Backup failed", str(e))
            return
        self.status.showMessage(f"Backup written: {bak.name}", 5000)
        QMessageBox.information(self, "Backup", f"Copied to:\n{bak}")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                self._load_folder(p)
                return
            if p.is_file() and p.parent.is_dir():
                self._load_folder(p.parent)
                return

    def closeEvent(self, event) -> None:
        dirty = False
        if self.db and self.db.default_parts:
            dirty = len(self.db.default_parts.dirty_rows) > self._saved_dirty_count
        if dirty or (self.plans and dirty):
            reply = QMessageBox.question(
                self,
                "Unsaved changes",
                "You have unsaved hybrid changes. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()

    def _choose_folder(self) -> None:
        start = str(self.folder) if self.folder else str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "Select GT4 SpecDB folder", start
        )
        if path:
            self._load_folder(Path(path))

    def _load_folder(self, folder: Path, quiet: bool = False) -> None:
        self.status.showMessage(f"Loading SpecDB from {folder.name}…")
        if hasattr(self, "load_bar"):
            self.load_bar.setVisible(True)
            self.load_bar.setRange(0, 0)  # indeterminate
        QApplication.processEvents()
        try:
            db = load_specdb(folder)
        except Exception as e:
            if hasattr(self, "load_bar"):
                self.load_bar.setVisible(False)
            QMessageBox.critical(
                self,
                "Failed to load SpecDB",
                f"{e}\n\nExpected files: GENERIC_CAR.dbt, DEFAULT_PARTS.dbt "
                "(and matching .idi files).",
            )
            return
        if hasattr(self, "load_bar"):
            self.load_bar.setVisible(False)
        self.db = db
        self.folder = folder
        self.target_id = None
        self.group.clear()
        self.parts.clear()
        self.plans.clear()
        self._saved_dirty_count = 0
        self._stock_parts = {c.row_id: dict(c.parts) for c in db.cars}
        set_folder(PATHS_KEY, folder)
        self.toolbar_path.setText(self._elide_path(folder))
        self.toolbar_path.setToolTip(str(folder))
        self.toolbar_count.setText(f"{len(db.cars)} cars")
        self.empty_state.setVisible(False)
        self.work_area.setVisible(True)
        if hasattr(self, "save_banner"):
            self.save_banner.setVisible(False)
        self._refresh()
        notes = f" · {len(db.notes)} note(s)" if db.notes else ""
        msg = f"Loaded {len(db.cars)} cars from {folder.name}{notes}"
        self.status.showMessage(msg, 4000 if quiet else 5000)

    def _effective_donor(self, part_key: str, group_key: str) -> Optional[int]:
        if part_key in self.parts:
            v = self.parts[part_key]
            if v == "" or v is None:
                return None  # keep
            return int(v)
        g = self.group.get(group_key)
        if g:
            return int(g)
        return None

    def _build_picks(self) -> Dict[str, int]:
        picks: Dict[str, int] = {}
        if self.target_id is None:
            return picks
        for g in GROUPS:
            for part_key, _ in g["parts"]:
                donor = self._effective_donor(part_key, g["key"])
                if donor is not None and donor != self.target_id:
                    picks[part_key] = donor
        return picks

    def _describe_picks(self, picks: Dict[str, int]) -> str:
        if not self.db:
            return ""
        by: Dict[int, List[str]] = {}
        labels = {k: lab for g in GROUPS for k, lab in g["parts"]}
        for part_key, donor_id in picks.items():
            by.setdefault(donor_id, []).append(labels.get(part_key, part_key))
        parts = []
        for did, labs in by.items():
            c = self.db.by_id.get(did)
            name = c.name if c else f"#{did}"
            parts.append(f"{name}: {', '.join(labs)}")
        return " · ".join(parts)

    def _picker_cars(self) -> list:
        out = []
        if not self.db:
            return out
        for c in self.db.cars:
            eng = c.parts.get("Engine")
            extra = f"eng {eng[0]}" if eng else ""
            brand = getattr(c, "brand", "") or ""
            out.append(
                PickerCar(
                    id=c.row_id,
                    name=c.name,
                    sub=c.label,
                    search=f"{c.name} {c.label} {c.year} {extra} {brand}",
                    year=c.year or 0,
                    power=0.0,
                    layout="",
                    extra=extra,
                    brand=brand,
                )
            )
        return out

    def _pick(self, slot: str) -> None:
        if not self.db:
            return
        allow_keep = slot not in ("target", "all") and not slot.startswith("g:")
        title = "Car to change" if slot == "target" else "Donor for group"
        if slot.startswith("p:"):
            title = "Donor for part"
        specials = []
        if allow_keep:
            specials.append(("", "Keep this car's own", ""))
        dlg = CarPickerDialog(
            self._picker_cars(), title=title, specials=specials, parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sel = dlg.selected()
        if sel is None:
            return
        if slot == "target":
            self.target_id = int(sel) if sel != "" else None
            self.group.clear()
            self.parts.clear()
        elif slot == "all":
            if sel == "":
                self.group.clear()
            else:
                for g in GROUPS:
                    self.group[g["key"]] = int(sel)
        elif slot.startswith("g:"):
            key = slot.split(":", 1)[1]
            self.group[key] = None if sel == "" else int(sel)
        elif slot.startswith("p:"):
            key = slot.split(":", 1)[1]
            self.parts[key] = "" if sel == "" else int(sel)
        self._refresh()

    def _apply_hybrid(self) -> None:
        if not self.db or self.target_id is None:
            return
        picks = self._build_picks()
        if not picks:
            return
        car = self.db.by_id[self.target_id]
        for part_key, donor_id in picks.items():
            try:
                apply_part_swap(self.db, self.target_id, part_key, donor_id)
            except Exception as e:
                QMessageBox.warning(self, "Apply failed", f"{part_key}: {e}")
                return
        rec = PlanRecord(
            id=self.next_id,
            target_id=self.target_id,
            target_name=car.name,
            mode=self.mode,
            picks=dict(picks),
            summary=self._describe_picks(picks),
        )
        self.next_id += 1
        self.plans.append(rec)
        self.group.clear()
        self.parts.clear()
        self.target_id = None
        self._refresh()
        self.status.showMessage(
            f"Hybrid added · {car.name} — use Save hybrids… to write DEFAULT_PARTS.dbt",
            5000,
        )

    def _remove_plan(self) -> None:
        row = self.changes_table.currentRow()
        if 0 <= row < len(self.plans):
            self.plans.pop(row)
            self._refresh()

    def _edit_plan(self) -> None:
        row = self.changes_table.currentRow()
        if not (0 <= row < len(self.plans)) or not self.db:
            return
        plan = self.plans[row]
        self.target_id = plan.target_id
        self.group.clear()
        self.parts.clear()
        for part_key, donor_id in plan.picks.items():
            self.parts[part_key] = donor_id
        self._refresh()
        self.status.showMessage(f"Editing · {plan.target_name}", 3000)

    def _duplicate_plan(self) -> None:
        row = self.changes_table.currentRow()
        if not (0 <= row < len(self.plans)):
            return
        src = self.plans[row]
        rec = PlanRecord(
            id=self.next_id,
            target_id=src.target_id,
            target_name=src.target_name,
            mode=src.mode,
            picks=dict(src.picks),
            summary=src.summary,
        )
        self.next_id += 1
        self.plans.append(rec)
        self._refresh()
        self.status.showMessage(f"Duplicated · {src.target_name}", 3000)

    def _plan_dicts(self) -> List[dict]:
        return [
            {
                "target_id": p.target_id,
                "target_name": p.target_name,
                "mode": p.mode,
                "summary": p.summary,
            }
            for p in self.plans
        ]

    def _save_hybrids(self) -> None:
        if not self.db or not self.plans:
            return
        if self.db.default_parts is None or not self.db.default_parts.dirty_rows:
            QMessageBox.information(
                self,
                "Nothing to save",
                "No DEFAULT_PARTS changes are pending. Add hybrids first.",
            )
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Save hybrids")
        msg.setText(
            f"{len(self.plans)} hybrid(s), "
            f"{len(self.db.default_parts.dirty_rows)} modified DEFAULT_PARTS row(s).\n\n"
            "How do you want to save?"
        )
        write_btn = msg.addButton("Write into SpecDB folder", QMessageBox.ButtonRole.AcceptRole)
        zip_btn = msg.addButton("Export ZIP (folder unchanged)", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked is write_btn:
            dest_dir = self.folder or Path.home()
            dest = Path(dest_dir) / "DEFAULT_PARTS.dbt"
            reply = QMessageBox.question(
                self,
                "Confirm write",
                f"Overwrite:\n{dest}\n\nA .bak is created the first time.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                written = save_default_parts(self.db, dest=dest, backup=True)
                summary = Path(dest_dir) / "hybrids.txt"
                write_hybrids_summary(self.db, self._plan_dicts(), summary)
            except Exception as e:
                QMessageBox.critical(self, "Save failed", str(e))
                return
            self._saved_dirty_count = len(self.db.default_parts.dirty_rows)
            self._show_save_success(f"Wrote {written.name} · {summary.name}")
            self.status.showMessage(f"Saved {written}", 6000)

        elif clicked is zip_btn:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export hybrids ZIP",
                str((self.folder or Path.home()) / "gt4_hybrids.zip"),
                "ZIP files (*.zip)",
            )
            if not path:
                return
            try:
                zpath = export_hybrids_zip(self.db, self._plan_dicts(), Path(path))
            except Exception as e:
                QMessageBox.critical(self, "Export failed", str(e))
                return
            self._show_save_success(f"Exported {zpath.name} (SpecDB folder unchanged)")
            self.status.showMessage(f"Exported {zpath}", 6000)

    def _show_save_success(self, text: str) -> None:
        if hasattr(self, "save_banner"):
            self.save_banner.setText(f"✓  {text}")
            self.save_banner.setVisible(True)
            QTimer.singleShot(8000, lambda: self.save_banner.setVisible(False))

    def _toggle_group(self, key: str) -> None:
        self.open_groups[key] = not self.open_groups.get(key, False)
        self._refresh_groups()

    def _reset_group(self, key: str, part_keys: List[str]) -> None:
        self.group.pop(key, None)
        for pk in part_keys:
            self.parts.pop(pk, None)
        self._refresh()

    def _refresh(self) -> None:
        has = self.db is not None and bool(self.db.cars)
        self.empty_state.setVisible(not has)
        self.work_area.setVisible(has)
        if not has:
            return
        self._refresh_target()
        self._refresh_groups()
        self._refresh_spec()
        self._refresh_changes()

    def _car_caption(self, car_id: Optional[object], unset: str) -> Tuple[str, str, bool]:
        if car_id is None or car_id == "":
            return unset, "", False
        if not self.db or int(car_id) not in self.db.by_id:
            return f"#{car_id}", "", True
        c = self.db.by_id[int(car_id)]
        sub = f"{c.label} · {c.year}" if c.year else c.label
        return c.name, sub, True

    def _set_donor_btn(self, btn: QPushButton, main: str, sub: str, active: bool) -> None:
        set_donor_button(btn, main, sub, active)

    def _refresh_target(self) -> None:
        main, sub, active = self._car_caption(self.target_id, "Choose a car")
        self._set_donor_btn(self.target_btn, main, sub, active)
        self.quick_btn.setEnabled(self.target_id is not None)

    def _refresh_groups(self) -> None:
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self.db or self.target_id is None:
            return
        target = self.db.by_id[self.target_id]

        for g in GROUPS:
            items = [
                (k, lab)
                for k, lab in g["parts"]
                if k in target.parts
            ]
            if not items:
                continue

            card = _card()
            gl = QVBoxLayout(card)
            gl.setContentsMargins(8, 5, 8, 5)
            gl.setSpacing(2)

            head = QHBoxLayout()
            head.addWidget(_label(g["label"], "cardTitle"))
            changed = 0
            for pk, _ in items:
                if self._effective_donor(pk, g["key"]) is not None:
                    changed += 1
            if changed:
                head.addWidget(_label(f"{changed} changed", "badge"))
            head.addStretch()
            is_open = self.open_groups.get(g["key"], False)
            if changed:
                reset = QPushButton("Reset")
                reset.setObjectName("link")
                reset.setCursor(Qt.CursorShape.PointingHandCursor)
                reset.setToolTip("Clear donors for this group")
                part_keys = [p for p, _ in items]
                reset.clicked.connect(
                    lambda checked=False, k=g["key"], pks=part_keys: self._reset_group(k, pks)
                )
                head.addWidget(reset)
            toggle = QPushButton("Hide" if is_open else "Part by part")
            toggle.setObjectName("link")
            toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle.clicked.connect(
                lambda checked=False, k=g["key"]: self._toggle_group(k)
            )
            head.addWidget(toggle)
            gl.addLayout(head)

            gl.addWidget(_label("TAKE ALL FROM", "fieldLabel"))
            gv = self.group.get(g["key"])
            main, sub, active = self._car_caption(gv, "Keep this car's own")
            gbtn = _donor_btn(main, sub, active)
            gbtn.clicked.connect(
                lambda checked=False, s=f"g:{g['key']}": self._pick(s)
            )
            gl.addWidget(gbtn)

            if is_open:
                gl.addWidget(_rule())
                for part_key, lab in items:
                    sel = self.parts.get(part_key)
                    if part_key in self.parts:
                        unset = "Keep this car's own"
                        main, sub, active = self._car_caption(
                            sel if sel != "" else None, unset
                        )
                        if sel == "":
                            main, sub, active = "Keep this car's own", "", False
                    else:
                        # inheriting group
                        eff = self._effective_donor(part_key, g["key"])
                        if eff:
                            main, sub, active = self._car_caption(eff, "Group donor")
                            main = main  # show resolved donor
                            # but mark as group-sourced: not locked active style unless explicit
                            active = False
                            main, sub, _ = self._car_caption(eff, "Group donor")
                            sub = (sub + " · from group") if sub else "from group"
                        else:
                            main, sub, active = "Keep this car's own", "", False

                    row = QHBoxLayout()
                    row.setSpacing(8)
                    lab_w = QLabel(lab)
                    lab_w.setStyleSheet("font-size: 12px;")
                    lab_w.setMinimumWidth(110)
                    row.addWidget(lab_w)
                    pbtn = _donor_btn(main, sub, active)
                    pbtn.setMinimumHeight(28)
                    pbtn.clicked.connect(
                        lambda checked=False, s=f"p:{part_key}": self._pick(s)
                    )
                    row.addWidget(pbtn, 1)
                    gl.addLayout(row)

            self.groups_layout.addWidget(card)

    def _clear_dyno(self) -> None:
        if not HAS_MPL or self.dyno_ax is None:
            return
        self.dyno_ax.clear()
        self.dyno_ax2.clear()
        self.dyno_ax.set_facecolor("#fafbfc")
        self.dyno_ax.text(
            0.5, 0.5, "Select a car to show the dynograph",
            ha="center", va="center", transform=self.dyno_ax.transAxes,
            color="#9ca3af", fontsize=9,
        )
        self.dyno_ax.set_xticks([])
        self.dyno_ax.set_yticks([])
        self.dyno_ax2.set_yticks([])
        for spine in list(self.dyno_ax.spines.values()) + list(self.dyno_ax2.spines.values()):
            spine.set_visible(False)
        self.dyno_fig.tight_layout(pad=0.3)
        self.dyno_canvas.draw_idle()

    def _update_dyno(self, before: "EngineCurve | None", after: "EngineCurve | None") -> None:
        if not HAS_MPL or self.dyno_ax is None:
            return
        self.dyno_ax.clear()
        self.dyno_ax2.clear()
        self.dyno_ax.set_facecolor("#ffffff")
        if not before and not after:
            self._clear_dyno()
            return

        def plot_curve(curve, tq_style, ps_style, tq_label, ps_label):
            if not curve or not curve.rpm:
                return
            powers = list(curve.power)
            if curve.peak_ps and powers and max(powers) > 0:
                scale = curve.peak_ps / max(powers)
                powers = [p * scale for p in powers]
            self.dyno_ax.plot(curve.rpm, curve.torque, tq_style, label=tq_label, linewidth=1.6)
            self.dyno_ax2.plot(curve.rpm, powers, ps_style, label=ps_label, linewidth=1.6)

        changed = (
            after and before
            and (after.rpm != before.rpm or after.torque != before.torque)
        )
        if changed:
            plot_curve(before, "#94a3b8", "#cbd5e1", "Torque (stock)", "PS (stock)")
            plot_curve(after, "#2563eb", "#dc2626", "Torque (hybrid)", "PS (hybrid)")
        else:
            curve = after or before
            plot_curve(curve, "#2563eb", "#dc2626", "Torque kgf·m", "Power PS")

        # Peak annotations
        for curve, color in ((after or before, "#dc2626"),):
            if curve and curve.peak_ps and curve.rpm and curve.power:
                powers = list(curve.power)
                if max(powers) > 0 and curve.peak_ps:
                    scale = curve.peak_ps / max(powers)
                    powers = [p * scale for p in powers]
                i_max = max(range(len(powers)), key=lambda i: powers[i])
                self.dyno_ax2.annotate(
                    f"{curve.peak_ps:.0f} PS",
                    xy=(curve.rpm[i_max], powers[i_max]),
                    xytext=(6, 6),
                    textcoords="offset points",
                    fontsize=7,
                    color=color,
                    fontweight="bold",
                )
            if curve and curve.rev_limit:
                self.dyno_ax.axvline(
                    curve.rev_limit, color="#f59e0b", linestyle="--", linewidth=0.8, alpha=0.7
                )

        self.dyno_ax.set_xlabel("RPM", fontsize=8, color="#6b7280")
        self.dyno_ax.set_ylabel("Torque (kgf·m)", fontsize=8, color="#2563eb")
        self.dyno_ax2.set_ylabel("Power (PS)", fontsize=8, color="#dc2626")
        self.dyno_ax.tick_params(labelsize=7, colors="#6b7280")
        self.dyno_ax2.tick_params(labelsize=7, colors="#6b7280")
        self.dyno_ax.grid(True, alpha=0.25, linewidth=0.6)
        self.dyno_ax.spines["top"].set_visible(False)
        self.dyno_ax2.spines["top"].set_visible(False)
        lines1, labels1 = self.dyno_ax.get_legend_handles_labels()
        lines2, labels2 = self.dyno_ax2.get_legend_handles_labels()
        if lines1 or lines2:
            self.dyno_ax.legend(
                lines1 + lines2, labels1 + labels2,
                loc="upper left", fontsize=7, framealpha=0.9,
            )
        self.dyno_fig.tight_layout(pad=0.35)
        self.dyno_canvas.draw_idle()

    def _refresh_spec(self) -> None:
        self.spec_table.setRowCount(0)
        self.plan_summary.setText("")
        self.apply_btn.setEnabled(False)

        if not self.db or self.target_id is None or self.target_id not in self.db.by_id:
            self.spec_title.setText("Spec sheet")
            self.spec_tag.setText("")
            self.spec_empty.setVisible(True)
            self.spec_table.setVisible(False)
            self._clear_dyno()
            return

        car = self.db.by_id[self.target_id]
        stock = self._stock_parts.get(car.row_id, dict(car.parts))
        self.spec_title.setText(car.name)
        self.spec_tag.setText(car.label)
        self.spec_empty.setVisible(False)
        self.spec_table.setVisible(True)

        picks = self._build_picks()
        # Stock curve from original engine key
        stock_car = CarInfo(
            row_id=car.row_id,
            label=car.label,
            name=car.name,
            year=car.year,
            price=car.price,
            default_parts_id=car.default_parts_id,
            default_parts_table=car.default_parts_table,
            parts=stock,
            maker_id=getattr(car, "maker_id", 0),
            brand=getattr(car, "brand", ""),
        )
        before_curve = engine_curve_for_car(self.db, stock_car)
        after_curve = before_curve
        if "Engine" in picks:
            donor = self.db.by_id.get(picks["Engine"])
            if donor:
                after_curve = engine_curve_for_car(self.db, donor)
        elif car.parts.get("Engine") != stock.get("Engine"):
            after_curve = engine_curve_for_car(self.db, car)
        self._update_dyno(before_curve, after_curve)

        # Info rows (no delta)
        info_rows = [
            ("Label", car.label, car.label, ""),
            ("Year", str(car.year) if car.year else "–", str(car.year) if car.year else "–", ""),
            ("Price", f"Cr {car.price:,}" if car.price else "–", f"Cr {car.price:,}" if car.price else "–", ""),
        ]
        if before_curve and before_curve.peak_ps:
            stock_ps = f"{before_curve.peak_ps:.0f} PS"
        else:
            stock_ps = "–"
        if after_curve and after_curve.peak_ps:
            hyb_ps = f"{after_curve.peak_ps:.0f} PS"
        else:
            hyb_ps = stock_ps
        delta_ps = ""
        if before_curve and after_curve and before_curve.peak_ps and after_curve.peak_ps:
            d = after_curve.peak_ps - before_curve.peak_ps
            if abs(d) >= 0.5:
                delta_ps = f"{d:+.0f} PS"
        info_rows.append(("Peak power", stock_ps, hyb_ps, delta_ps))

        for part_key, lab in HYBRID_PARTS:
            sk = stock.get(part_key)
            stock_val = f"{sk[0]}" if sk else "–"
            if part_key in picks:
                d = self.db.by_id.get(picks[part_key])
                hyb_val = d.name if d else str(picks[part_key])
                delta = "changed" if (not sk or (d and d.parts.get(part_key) != sk)) else ""
            else:
                ck = car.parts.get(part_key)
                hyb_val = f"{ck[0]}" if ck else "–"
                delta = "changed" if ck != sk else ""
            info_rows.append((lab, stock_val, hyb_val, delta))

        accent_bg = QColor(COLORS["accent_soft"])
        accent_fg = QColor(COLORS["accent"])
        up_fg = QColor(COLORS["delta_up"])
        down_fg = QColor(COLORS["delta_down"])
        self.spec_table.setRowCount(len(info_rows))
        for i, (lab, stock_v, hyb_v, delta) in enumerate(info_rows):
            self.spec_table.setItem(i, 0, QTableWidgetItem(lab))
            self.spec_table.setItem(i, 1, QTableWidgetItem(stock_v))
            hyb_item = QTableWidgetItem(hyb_v)
            if delta:
                hyb_item.setBackground(accent_bg)
                hyb_item.setForeground(accent_fg)
                f = hyb_item.font()
                f.setBold(True)
                hyb_item.setFont(f)
            self.spec_table.setItem(i, 2, hyb_item)
            d_item = QTableWidgetItem(delta)
            if delta.endswith("PS"):
                d_item.setForeground(up_fg if delta.startswith("+") else down_fg)
                f = d_item.font()
                f.setBold(True)
                d_item.setFont(f)
            elif delta == "changed":
                d_item.setForeground(accent_fg)
            self.spec_table.setItem(i, 3, d_item)

        if picks:
            self.plan_summary.setText(self._describe_picks(picks))
            self.apply_btn.setEnabled(True)
        else:
            self.plan_summary.setText("Pick at least one donor to preview.")

    def _refresh_changes(self) -> None:
        self.changes_table.setRowCount(0)
        for p in self.plans:
            r = self.changes_table.rowCount()
            self.changes_table.insertRow(r)
            n = len(p.picks)
            self.changes_table.setItem(r, 0, QTableWidgetItem(p.target_name))
            self.changes_table.setItem(r, 1, QTableWidgetItem(str(n)))
            self.changes_table.setItem(r, 2, QTableWidgetItem(p.mode))
            self.changes_table.setItem(r, 3, QTableWidgetItem(p.summary))
        n = len(self.plans)
        self.changes_count.setText(str(n))
        label = f"Save hybrids… ({n})" if n else "Save hybrids…"
        self.dl_btn.setText(label)
        self.dl_btn.setEnabled(bool(self.plans))

