from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QColor, QKeySequence, QPalette
from PyQt6.QtWidgets import (
    QApplication,QButtonGroup,QDialog,QDialogButtonBox,
    QFileDialog,QFrame,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QMainWindow,QMessageBox,QPushButton,QRadioButton,
    QScrollArea,QSplitter,QStatusBar,QTableWidget,
    QTableWidgetItem,QToolBar,QVBoxLayout,QWidget,
)
from ui.folder_paths import get_folder, set_folder
from ui.design import (
    APP_STYLE,
    COLORS,
    card as _card,
    donor_button as _donor_btn,
    rule as _rule,
    set_donor_button,
)
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


class CarPickerDialog(QDialog):

    def __init__(
        self,
        cars: List[CarInfo],
        title: str = "Choose a car",
        allow_keep: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 440)
        self.setStyleSheet(APP_STYLE)
        self._cars = cars
        self._allow_keep = allow_keep
        self._result: Optional[object] = None  # int id, or "" for keep

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.addWidget(_label(title, "cardTitle"))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, label, year…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)

        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.list.itemDoubleClicked.connect(self._accept_item)
        self.list.itemActivated.connect(self._accept_item)
        root.addWidget(self.list, 1)

        self.count_lab = _label("", "muted")
        root.addWidget(self.count_lab)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._filter("")
        self.search.setFocus()

    def _filter(self, q: str) -> None:
        self.list.clear()
        terms = [t for t in q.lower().split() if t]
        if self._allow_keep and not terms:
            item = QListWidgetItem("Keep this car's own")
            item.setData(Qt.ItemDataRole.UserRole, "")
            item.setSizeHint(QSize(100, 28))
            self.list.addItem(item)
        hits = [
            c
            for c in self._cars
            if all(
                t in (c.name + " " + c.label + " " + str(c.year)).lower() for t in terms
            )
        ]
        for c in hits[:400]:
            sub = f"{c.label} · {c.year}" if c.year else c.label
            item = QListWidgetItem(f"{c.name}\n{sub}")
            item.setData(Qt.ItemDataRole.UserRole, c.row_id)
            item.setSizeHint(QSize(100, 40))
            self.list.addItem(item)
        extra = max(0, len(hits) - 400)
        self.count_lab.setText(
            f"{len(hits)} cars" + (" (showing 400)" if extra else "")
        )
        if self.list.count():
            self.list.setCurrentRow(0)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self._result = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _accept(self) -> None:
        cur = self.list.currentItem()
        if cur:
            self._result = cur.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def selected(self):
        return self._result


class GT4HybridWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GT4 Hybrid Creator")
        self.resize(1100, 720)
        self.setMinimumSize(860, 520)
        self.setStyleSheet(APP_STYLE)

        self.db: Optional[SpecDB] = None
        self.folder: Optional[Path] = None
        self.target_id: Optional[int] = None
        self.mode: str = "link"  
        self.group: Dict[str, Optional[int]] = {}  # group key -> donor car id
        self.parts: Dict[str, Optional[int]] = {}  # part key -> donor car id or "" keep
        self.open_groups: Dict[str, bool] = {}
        self.plans: List[PlanRecord] = []
        self.next_id = 1

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
        tb.addSeparator()
        self.toolbar_path = _label("No SpecDB folder", "path")
        self.toolbar_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
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
        ll.setSpacing(6)

        tcard = _card()
        tl = QVBoxLayout(tcard)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setSpacing(4)
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
        self.groups_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.groups_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.groups_widget = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_widget)
        self.groups_layout.setContentsMargins(0, 0, 2, 0)
        self.groups_layout.setSpacing(6)
        self.groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groups_scroll.setWidget(self.groups_widget)
        ll.addWidget(self.groups_scroll, 1)
        split.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(320)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        scard = _card()
        sl = QVBoxLayout(scard)
        sl.setContentsMargins(10, 8, 10, 8)
        sl.setSpacing(6)

        sh = QHBoxLayout()
        self.spec_title = _label("Spec sheet", "cardTitle")
        sh.addWidget(self.spec_title)
        sh.addStretch()
        self.spec_tag = _label("", "tag")
        sh.addWidget(self.spec_tag)
        sl.addLayout(sh)

        self.spec_empty = _label("Choose a car to see details.", "muted")
        sl.addWidget(self.spec_empty)

        self.spec_table = QTableWidget(0, 2)
        self.spec_table.setHorizontalHeaderLabels(["Spec", "Value"])
        hdr = self.spec_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.spec_table.verticalHeader().setVisible(False)
        self.spec_table.verticalHeader().setDefaultSectionSize(22)
        self.spec_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.spec_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.spec_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.spec_table.setShowGrid(False)
        self.spec_table.setMaximumHeight(200)
        sl.addWidget(self.spec_table)

        self.dyno_frame = QFrame()
        self.dyno_frame.setObjectName("card")
        self.dyno_frame.setMinimumHeight(150)
        self.dyno_frame.setMaximumHeight(190)
        dyno_l = QVBoxLayout(self.dyno_frame)
        dyno_l.setContentsMargins(4, 4, 4, 4)
        dyno_l.setSpacing(0)
        if HAS_MPL:
            self.dyno_fig = Figure(figsize=(4.2, 1.6), dpi=100)
            self.dyno_fig.patch.set_facecolor("#ffffff")
            self.dyno_ax = self.dyno_fig.add_subplot(111)
            self.dyno_ax2 = self.dyno_ax.twinx()
            self.dyno_canvas = FigureCanvasQTAgg(self.dyno_fig)
            self.dyno_canvas.setMinimumHeight(140)
            dyno_l.addWidget(self.dyno_canvas)
            self._clear_dyno()
        else:
            self.dyno_fig = self.dyno_ax = self.dyno_ax2 = self.dyno_canvas = None
            miss = _label("Install matplotlib for the dynograph:  pip install matplotlib", "muted")
            miss.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dyno_l.addWidget(miss)
        sl.addWidget(self.dyno_frame)

        self.plan_summary = _label("", "muted")
        self.plan_summary.setWordWrap(True)
        sl.addWidget(self.plan_summary)
        sl.addWidget(_rule())

        sl.addWidget(_label("HOW PARTS ARE APPLIED", "fieldLabel"))
        self.mode_group = QButtonGroup(self)
        self.radio_link = QRadioButton("Link to the donor's parts")
        self.radio_link.setToolTip(
            "DEFAULT_PARTS keys point at the donor part rows. Recommended for SpecDB."
        )
        self.radio_link.setChecked(True)
        self.mode_group.addButton(self.radio_link)
        sl.addWidget(self.radio_link)
        sl.addWidget(
            _label(
                "Only DEFAULT_PARTS keys change (link mode). Writing .dbt is not available yet.",
                "muted",
            )
        )

        self.apply_btn = QPushButton("Add to list.")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_hybrid)
        sl.addWidget(self.apply_btn)
        rl.addWidget(scard)

        ccard = _card()
        cl = QVBoxLayout(ccard)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(4)
        ch = QHBoxLayout()
        ch.addWidget(_label("Hybrid list", "cardTitle"))
        ch.addStretch()
        self.changes_count = _label("0", "tag")
        ch.addWidget(self.changes_count)
        cl.addLayout(ch)

        self.changes_list = QListWidget()
        self.changes_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.changes_list.setMinimumHeight(80)
        cl.addWidget(self.changes_list, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.dl_btn = QPushButton("Save hybrids…")
        self.dl_btn.setObjectName("primary")
        self.dl_btn.setEnabled(False)
        self.dl_btn.setToolTip("Saving compressed SpecDB tables is not implemented yet.")
        self.dl_btn.clicked.connect(self._save_stub)
        row.addWidget(self.dl_btn)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_plan)
        row.addWidget(self.remove_btn)
        cl.addLayout(row)
        cl.addWidget(
            _label(
                "Hybrids apply in memory for now. Disk save for Huffman .dbt coming later.",
                "muted",
            )
        )
        rl.addWidget(ccard, 1)

        split.addWidget(right)
        split.setSizes([560, 480])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.work_area.setVisible(False)

    def _try_load_saved(self) -> None:
        saved = get_folder(PATHS_KEY)
        if saved and saved.is_dir():
            self._load_folder(saved, quiet=True)
        else:
            QTimer.singleShot(50, self._choose_folder)

    def _choose_folder(self) -> None:
        start = str(self.folder) if self.folder else str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "Select GT4 SpecDB folder", start
        )
        if path:
            self._load_folder(Path(path))

    def _load_folder(self, folder: Path, quiet: bool = False) -> None:
        try:
            db = load_specdb(folder)
        except Exception as e:
            QMessageBox.critical(self, "Failed to load SpecDB", str(e))
            return
        self.db = db
        self.folder = folder
        self.target_id = None
        self.group.clear()
        self.parts.clear()
        self.plans.clear()
        set_folder(PATHS_KEY, folder)
        self.toolbar_path.setText(str(folder))
        self.toolbar_count.setText(f"{len(db.cars)} cars")
        self.empty_state.setVisible(False)
        self.work_area.setVisible(True)
        self._refresh()
        msg = f"Loaded {len(db.cars)} cars from {folder.name}"
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

    def _pick(self, slot: str) -> None:
        if not self.db:
            return
        allow_keep = slot not in ("target", "all") and not slot.startswith("g:")
        title = "Car to change" if slot == "target" else "Donor for group"
        if slot.startswith("p:"):
            title = "Donor for part"
        dlg = CarPickerDialog(
            self.db.cars, title=title, allow_keep=allow_keep, parent=self
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
            f"Hybrid added (in memory) · {car.name}", 4000
        )

    def _remove_plan(self) -> None:
        row = self.changes_list.currentRow()
        if 0 <= row < len(self.plans):
            self.plans.pop(row)
            self._refresh()

    def _save_stub(self) -> None:
        QMessageBox.information(
            self,
            "Save not available yet",
            "Writing Huffman-compressed SpecDB tables is not implemented yet.\n"
            "Hybrids in this session exist only in memory.",
        )

    def _toggle_group(self, key: str) -> None:
        self.open_groups[key] = not self.open_groups.get(key, False)
        self._refresh_groups()

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
            gl.setContentsMargins(10, 8, 10, 8)
            gl.setSpacing(4)

            head = QHBoxLayout()
            head.addWidget(_label(g["label"], "cardTitle"))
            head.addStretch()
            is_open = self.open_groups.get(g["key"], False)
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
        self.spec_title.setText(car.name)
        self.spec_tag.setText(car.label)
        self.spec_empty.setVisible(False)
        self.spec_table.setVisible(True)

        picks = self._build_picks()
        before_curve = engine_curve_for_car(self.db, car)
        after_curve = before_curve
        if "Engine" in picks:
            donor = self.db.by_id.get(picks["Engine"])
            if donor:
                after_curve = engine_curve_for_car(self.db, donor)
        self._update_dyno(before_curve, after_curve)
        rows = [
            ("Label", car.label),
            ("Year", str(car.year) if car.year else "–"),
            ("Price", f"Cr {car.price:,}" if car.price else "–"),
            ("DEFAULT_PARTS id", str(car.default_parts_id)),
        ]
        for part_key, lab in HYBRID_PARTS:
            key = car.parts.get(part_key)
            val = f"{key[0]}" if key else "–"
            if part_key in picks:
                d = self.db.by_id.get(picks[part_key])
                val = f"→ {d.name if d else picks[part_key]}"
            rows.append((lab, val))

        self.spec_table.setRowCount(len(rows))
        accent_bg = QColor("#eff4ff")
        accent_fg = QColor("#2563eb")
        for i, (lab, val) in enumerate(rows):
            self.spec_table.setItem(i, 0, QTableWidgetItem(lab))
            item = QTableWidgetItem(val)
            if val.startswith("→"):
                item.setBackground(accent_bg)
                item.setForeground(accent_fg)
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.spec_table.setItem(i, 1, item)

        if picks:
            self.plan_summary.setText(self._describe_picks(picks))
            self.apply_btn.setEnabled(True)
        else:
            self.plan_summary.setText("Pick at least one donor to preview.")

    def _refresh_changes(self) -> None:
        self.changes_list.clear()
        for p in self.plans:
            item = QListWidgetItem(f"{p.target_name}\n{p.summary}")
            item.setSizeHint(QSize(100, 48))
            self.changes_list.addItem(item)
        self.changes_count.setText(str(len(self.plans)))
        self.dl_btn.setEnabled(bool(self.plans))
