from __future__ import annotations
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QPalette,
)
try:
    import matplotlib
    matplotlib.use("Agg")  
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    FigureCanvasQTAgg = None  
    Figure = None  
from PyQt6.QtWidgets import (
    QApplication,QButtonGroup,QDialog,QDialogButtonBox,
    QFileDialog,QFrame,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QMainWindow,QMessageBox,QPushButton,QRadioButton,
    QProgressBar,QScrollArea,QSizePolicy,QSplitter,QStatusBar,
    QTableWidget,QTableWidgetItem,QTabWidget,QToolBar,
    QVBoxLayout,QWidget,
)

from gt_engine import (
    CAR_TYPES,
    DRIVE_NAMES,
    GROUPS,
    INFO_DEFS,
    PART_DEFS,
    CarStats,
    Db,
    ReportEntry,
    StringTable,
    apply_plan,
    car_count,
    car_hash,
    car_names,
    car_stats,
    classify_file,
    hex64,
    make_zip,
    open_db,
    parse_id_index,
    parse_stdb,
    pointer,
    preview_plan,
    write_gtar,
    engine_curve,
    EngineCurve,
)
SETTINGS_ORG = "GT3HybridGarage"
PATHS_KEY = "gt3"
try:
    from ui.folder_paths import get_folder, set_folder
    from ui.design import APP_STYLE, COLORS, apply_app_theme, card as _shared_card, donor_button as _shared_donor, rule as _shared_rule, set_donor_button
    from ui.car_picker import CarPickerDialog, PickerCar
except ImportError:
    # Standalone: gt3/hybrid_gui.py run directly
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from ui.folder_paths import get_folder, set_folder
    from ui.design import APP_STYLE, COLORS, apply_app_theme, card as _shared_card, donor_button as _shared_donor, rule as _shared_rule, set_donor_button
    from ui.car_picker import CarPickerDialog, PickerCar

@dataclass
class LoadedFile:
    path: Path
    name: str
    kind: str
    suffix: str
    raw: bytes

@dataclass
class CarInfo:
    index: int
    hex: str
    main: str
    sub: str
    stats: CarStats
    named: bool
    search: str
    brand: str = ""

@dataclass
class Region:
    file: LoadedFile
    suffix: str
    label: str
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    db: Optional[Db] = None
    visible: Set[str] = field(default_factory=set)
    cars: List[CarInfo] = field(default_factory=list)
    by_hex: Dict[str, CarInfo] = field(default_factory=dict)
    has_names: bool = False
    str_tbl: Optional[StringTable] = None
    uni: Optional[StringTable] = None
    id_map: Optional[Dict[int, int]] = None
    id_str: Optional[StringTable] = None

@dataclass
class PlanRecord:
    id: int
    target: str
    target_name: str
    mode: str
    picks: Dict[str, str]
    info: Dict[str, str]
    summary: str

def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f

def _rule() -> QFrame:
    f = QFrame()
    f.setObjectName("rule")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f

def _label(text: str, obj: str = "") -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    return lab

def _donor_btn(main: str, sub: str = "", active: bool = False) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("donor")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(24)
    btn.setText(main if not sub else f"{main}\n{sub}")
    if active:
        btn.setStyleSheet(
            "QPushButton#donor { text-align: left; padding: 5px 8px; "
            "border-color: #2563eb; background: #eff4ff; }"
        )
    else:
        btn.setStyleSheet("QPushButton#donor { text-align: left; padding: 5px 8px; }")
    return btn


class HybridGarage(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GT3 Hybrid Creator")
        self.resize(1100, 720)
        self.setMinimumSize(860, 520)
        self.setAcceptDrops(True)
        self.setStyleSheet(APP_STYLE)

        self.files: List[LoadedFile] = []
        self.notes: List[str] = []
        self.regions: List[Region] = []
        self.active_region = 0
        self.target: str = ""
        self.mode: str = "copy"
        self.group: Dict[str, str] = {}
        self.parts: Dict[str, str] = {}
        self.info_sel: Dict[str, str] = {}
        self.open_groups: Dict[str, bool] = {}
        self.plans: List[PlanRecord] = []
        self.next_id = 1
        self.results: Dict[int, List[Dict[str, Any]]] = {}
        self.db_folder: Optional[Path] = None

        self._build_ui()
        self._try_load_saved_folder()
        self._refresh()

    def _build_ui(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        self.addToolBar(tb)

        act = QAction("Change folder…", self)
        act.setShortcut(QKeySequence.StandardKey.Open)
        act.triggered.connect(self._choose_folder)
        tb.addAction(act)
        act_bak = QAction("Backup now…", self)
        act_bak.setToolTip("Copy loaded paramdb files to *.bak in the database folder")
        act_bak.triggered.connect(self._backup_database)
        tb.addAction(act_bak)
        tb.addSeparator()
        self.toolbar_path = _label("No database folder", "path")
        self.toolbar_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tb.addWidget(self.toolbar_path)
        tb.addSeparator()
        self.toolbar_regions = _label("", "tag")
        tb.addWidget(self.toolbar_regions)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(_label("GT3 Hybrid Creator", "title"))
        head.addStretch()
        self.region_tabs = QTabWidget()
        self.region_tabs.setDocumentMode(True)
        self.region_tabs.tabBar().setExpanding(False)
        self.region_tabs.currentChanged.connect(self._on_region_tab)
        self.region_tabs.setMaximumHeight(28)
        head.addWidget(self.region_tabs)
        root.addLayout(head)

        self.empty_state = _card()
        es = QVBoxLayout(self.empty_state)
        es.setContentsMargins(24, 32, 24, 32)
        es.setSpacing(8)
        es.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es.addWidget(_label("Open a database folder to get started", "cardTitle"), 0, Qt.AlignmentFlag.AlignCenter)
        hint = _label(
            "Select the folder containing paramdb.db and related files. The path is remembered.",
            "muted",
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        es.addWidget(hint)
        btn = QPushButton("Open database folder…")
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

        # LEFT: target, part groups, hybrid list
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
            "Keeps its 3D model and body. Parts come from donors below.", "muted"
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

        # Hybrid list under groups (left side)
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
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(self._download_zip)
        row.addWidget(self.dl_btn)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.clicked.connect(self._edit_plan)
        row.addWidget(self.edit_btn)
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dup_btn.clicked.connect(self._duplicate_plan)
        row.addWidget(self.dup_btn)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.clicked.connect(self._remove_plan)
        row.addWidget(self.remove_btn)
        cl.addLayout(row)
        cl.addWidget(_label("Writes *.bak backups when saving into the folder.", "muted"))
        ll.addWidget(ccard, 1)
        split.addWidget(left)

        # RIGHT: spec sheet + dyno only
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
        self.spec_region_tag = _label("", "tag")
        sh.addWidget(self.spec_region_tag)
        sl.addLayout(sh)

        self.spec_empty = _label("Choose a car to see the comparison.", "muted")
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
        self.radio_copy = QRadioButton("Overwrite")
        self.radio_copy.setToolTip("Rewrites stock part rows with donor figures. Shop options stay this car's.")
        self.radio_link = QRadioButton("Link")
        self.radio_link.setToolTip("Only the car entry pointers change.")
        self.radio_copy.setChecked(True)
        self.mode_group.addButton(self.radio_copy)
        self.mode_group.addButton(self.radio_link)
        self.radio_copy.toggled.connect(self._on_mode)
        mode_row.addWidget(self.radio_copy)
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

    def _try_load_saved_folder(self) -> None:
        p = get_folder(PATHS_KEY)
        if p and p.is_dir():
            self._load_folder(p, quiet=True)
            return
        QTimer.singleShot(80, self._choose_folder)

    def _choose_folder(self) -> None:
        start = str(self.db_folder) if self.db_folder else str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Select GT3 database folder", start)
        if path:
            self._load_folder(Path(path))
        elif not self.db_folder:
            self.status.showMessage("No database folder selected.", 3000)

    def _clear_session(self) -> None:
        self.files.clear()
        self.notes.clear()
        self.regions.clear()
        self.active_region = 0
        self.target = ""
        self.group.clear()
        self.parts.clear()
        self.info_sel.clear()
        self.plans.clear()
        self.results.clear()

    def _load_folder(self, folder: Path, quiet: bool = False) -> None:
        folder = folder.resolve()
        if not folder.is_dir():
            if not quiet:
                QMessageBox.warning(self, "Not a folder", f"{folder} is not a directory.")
            return
        self.status.showMessage(f"Loading database from {folder.name}…")
        if hasattr(self, "load_bar"):
            self.load_bar.setVisible(True)
            self.load_bar.setRange(0, 0)
        QApplication.processEvents()
        self._clear_session()
        self.db_folder = folder
        set_folder(PATHS_KEY, folder)
        loaded = 0
        for p in sorted(folder.iterdir()):
            if not p.is_file() or not p.name.endswith(".db") or p.name.endswith(".bak"):
                continue
            try:
                raw = p.read_bytes()
            except OSError as e:
                self.notes.append(f"{p.name}: {e}")
                continue
            cls = classify_file(p.name, raw)
            if not cls:
                continue
            self.files.append(
                LoadedFile(path=p, name=p.name, kind=cls["kind"], suffix=cls["suffix"], raw=raw)
            )
            loaded += 1
        if not any(f.kind == "paramdb" for f in self.files):
            self.notes.append(f"No paramdb*.db found in {folder}.")
        self._rebuild_regions()
        self._replay()
        self._refresh()
        if hasattr(self, "load_bar"):
            self.load_bar.setVisible(False)
        ok = sum(1 for r in self.regions if not r.error)
        if not quiet:
            self.status.showMessage(f"Loaded {ok} region(s) · {loaded} file(s)", 5000)

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

    def _rebuild_regions(self) -> None:
        regions: List[Region] = []
        for f in self.files:
            if f.kind != "paramdb":
                continue
            r = Region(file=f, suffix=f.suffix, label=(f.suffix.upper() if f.suffix else "JP"))
            try:
                open_db(f.raw)
            except ValueError as e:
                r.error = str(e)
                regions.append(r)
                continue

            def mate(kind: str, suffix: str = f.suffix) -> Optional[LoadedFile]:
                return next((x for x in self.files if x.kind == kind and x.suffix == suffix), None)

            def parse(kind: str, fn, attr: str) -> None:
                m = mate(kind)
                if not m:
                    return
                try:
                    setattr(r, attr, fn(m.raw))
                except Exception as e:
                    r.warnings.append(f"{m.name}: {e}")

            parse("str", parse_stdb, "str_tbl")
            parse("unistr", parse_stdb, "uni")
            parse("idx", parse_id_index, "id_map")
            parse("idstr", parse_stdb, "id_str")
            regions.append(r)
        self.regions = regions
        if self.active_region >= len(regions):
            self.active_region = 0

    def _replay(self) -> None:
        self.results = {}
        for r in self.regions:
            if r.error:
                continue
            r.db = open_db(r.file.raw)
            r.visible = set()
            n = car_count(r.db)
            for d in PART_DEFS:
                for i in range(n):
                    if pointer(r.db, i, d):
                        r.visible.add(d.key)
                        break
            for p in self.plans:
                plan = {"target": p.target, "mode": p.mode, "picks": p.picks, "info": p.info}
                res = apply_plan(r.db, plan)
                self.results.setdefault(p.id, []).append(
                    {"region": r.label, "ok": res.ok, "reason": res.reason, "report": res.report}
                )
            self._build_cars(r)
        reg = self._region()
        if self.target and reg and self.target not in reg.by_hex:
            self.target = ""

    def _build_cars(self, r: Region) -> None:
        assert r.db is not None
        r.cars = []
        r.by_hex = {}
        n = car_count(r.db)
        for i in range(n):
            hx = hex64(car_hash(r.db, i))
            st = car_stats(r.db, i)
            nm = car_names(r.db, i, r.uni, r.str_tbl, r.id_map, r.id_str)
            drive = "" if st.drive is None else (DRIVE_NAMES[st.drive] if st.drive < len(DRIVE_NAMES) else "")
            spec_parts = [
                f"{st.ps} PS" if st.ps else None,
                drive or None,
                f"{st.mass} kg" if st.mass else None,
                str(st.year) if st.year else None,
            ]
            spec = " · ".join(p for p in spec_parts if p)
            main = (nm.name or nm.code or "").strip()
            # Game strings sometimes start with a dash/bullet
            while main and main[0] in "-–—·•|_":
                main = main[1:].strip()
            sub = spec
            if not main:
                main = " · ".join(p for p in [drive, f"{st.ps} PS" if st.ps else "no PS"] if p)
                sub = " · ".join(
                    p for p in [f"{st.mass} kg" if st.mass else None, str(st.year) if st.year else None, f"#{hx[:6]}"] if p
                )
            elif nm.name and nm.code:
                sub = f"{nm.code} · {spec}"
            try:
                from ui.makers import guess_brand_from_text
                brand = guess_brand_from_text(nm.maker, main, nm.code)
            except Exception:
                brand = (nm.maker or "").strip() or ""
            car = CarInfo(
                index=i, hex=hx, main=main, sub=sub, stats=st,
                named=bool(nm.name or nm.code),
                search=(main + " " + sub + " " + hx + " " + brand).lower(),
                brand=brand,
            )
            r.cars.append(car)
            r.by_hex[hx] = car
        r.has_names = any(c.named for c in r.cars)
        r.cars.sort(key=(lambda c: c.main.lower()) if r.has_names else (lambda c: -(c.stats.ps or 0)))

    def _region(self) -> Optional[Region]:
        if not self.regions or self.active_region >= len(self.regions):
            return None
        r = self.regions[self.active_region]
        return r if not r.error else None

    def _effective(self, slot_val: Optional[str], group_val: Optional[str]) -> str:
        v = slot_val if slot_val not in (None, "") else (group_val or "")
        if v == "keep":
            v = ""
        return v if v and v != self.target else ""

    def _build_plan(self) -> Optional[Dict[str, Any]]:
        r = self._region()
        if not r or not self.target:
            return None
        picks: Dict[str, str] = {}
        info: Dict[str, str] = {}
        for d in PART_DEFS:
            if d.key in r.visible:
                v = self._effective(self.parts.get(d.key), self.group.get(d.group))
                if v:
                    picks[d.key] = v
        for d in INFO_DEFS:
            v = self._effective(self.info_sel.get(d.key), self.group.get("info"))
            if v:
                info[d.key] = v
        return {"target": self.target, "mode": self.mode, "picks": picks, "info": info}

    def _plan_empty(self, plan: Optional[Dict[str, Any]]) -> bool:
        return not plan or (not plan.get("picks") and not plan.get("info"))

    def _describe_plan(self, plan: Dict[str, Any]) -> str:
        r = self._region()
        by: Dict[str, List[str]] = {}
        for d in PART_DEFS:
            hx = plan.get("picks", {}).get(d.key)
            if hx:
                by.setdefault(hx, []).append(d.label)
        for d in INFO_DEFS:
            hx = plan.get("info", {}).get(d.key)
            if hx:
                by.setdefault(hx, []).append(d.label)
        parts = []
        for hx, labels in by.items():
            c = r.by_hex.get(hx) if r else None
            parts.append(f"{c.main if c else '#' + hx[:6]}: {', '.join(labels)}")
        return " · ".join(parts)

    def _picker_cars(self, r) -> list:
        out = []
        for c in r.cars:
            st = c.stats
            ps = float(st.ps or 0)
            layout = getattr(st, "drive", "") or ""
            if isinstance(layout, (int, float)):
                layout = str(layout)
            out.append(
                PickerCar(
                    id=c.hex,
                    name=c.main,
                    sub=c.sub or "",
                    search=c.search,
                    year=int(getattr(st, "year", 0) or 0),
                    power=ps,
                    layout=str(layout),
                    extra="",
                    brand=getattr(c, "brand", "") or "",
                )
            )
        return out

    def _pick(self, slot: str) -> None:
        r = self._region()
        if not r:
            return
        specials: List[Tuple[str, str, str]] = []
        title = "Choose a car"
        if slot == "target":
            title = "Car to change"
        elif slot == "all" or slot.startswith("g:"):
            specials.append(("", "Keep this car's own", ""))
            title = "Donor for group"
        elif slot.startswith("p:") or slot.startswith("i:"):
            specials.append(("", "Use the group donor", ""))
            specials.append(("keep", "Keep this car's own", ""))
            title = "Donor for part"
        dlg = CarPickerDialog(
            self._picker_cars(r), title=title, specials=specials, parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        hx = dlg.selected_hex()
        if hx is None:
            return
        if slot == "target":
            self.target = hx
        elif slot == "all":
            for g in ("engine", "drivetrain", "chassis", "tyres"):
                self.group[g] = hx
        else:
            kind, key = slot.split(":", 1)
            if kind == "g":
                self.group[key] = hx
            elif kind == "p":
                self.parts[key] = hx
            elif kind == "i":
                self.info_sel[key] = hx
        self._refresh()

    def _apply_hybrid(self) -> None:
        r = self._region()
        plan = self._build_plan()
        if not r or self._plan_empty(plan):
            return
        assert plan is not None
        car = r.by_hex[self.target]
        rec = PlanRecord(
            id=self.next_id, target=plan["target"], target_name=car.main,
            mode=plan["mode"], picks=dict(plan["picks"]), info=dict(plan["info"]),
            summary=self._describe_plan(plan),
        )
        self.next_id += 1
        self.plans.append(rec)
        self.group.clear()
        self.parts.clear()
        self.info_sel.clear()
        self.target = ""
        self._replay()
        self._refresh()
        self.status.showMessage(
            f"Hybrid added · {[x.label for x in self.regions if not x.error]}", 4000
        )

    def _remove_plan(self) -> None:
        row = self.changes_table.currentRow()
        if 0 <= row < len(self.plans):
            self.plans.pop(row)
            self._replay()
            self._refresh()

    def _download_zip(self) -> None:
        if not self.plans:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Save hybrids")
        msg.setText("Save patched paramdb files?")
        msg.setInformativeText(
            "Write into folder creates *.bak backups on first save. ZIP leaves the folder unchanged."
        )
        b_folder = msg.addButton("Write into folder", QMessageBox.ButtonRole.AcceptRole)
        b_zip = msg.addButton("Export ZIP…", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is b_folder:
            self._save_into_folder()
        elif clicked is b_zip:
            self._export_zip()

    def _patched_paramdbs(self) -> List[Tuple[LoadedFile, bytes]]:
        return [
            (r.file, write_gtar(r.db.arc))
            for r in self.regions
            if not r.error and r.db is not None
        ]

    def _hybrid_summary_text(self) -> str:
        lines = ["GT3 Hybrid Creator", ""]
        for i, p in enumerate(self.plans, 1):
            mode = "overwrite" if p.mode == "copy" else "link"
            lines.append(f"{i}. {p.target_name} <- {p.summary} [{mode}]")
        return "\n".join(lines) + "\n"

    def _backup_database(self) -> None:
        if not self.db_folder:
            QMessageBox.warning(self, "No folder", "Open a database folder first.")
            return
        # Only back up the files we actually loaded (paramdb + str/unistr/id tables)
        targets = list(self.files)
        if not targets:
            QMessageBox.warning(self, "Nothing to back up", "No data files are loaded.")
            return

        existing = [f for f in targets if f.path.with_suffix(f.path.suffix + ".bak").exists()]
        overwrite = False
        if existing:
            ans = QMessageBox.question(
                self,
                "Overwrite existing backups?",
                f"{len(existing)} of {len(targets)} file(s) already have a .bak copy.\n\n"
                "Yes = replace those .bak files\n"
                "No = only create missing backups\n"
                "Cancel = do nothing",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Cancel:
                return
            overwrite = ans == QMessageBox.StandardButton.Yes

        written: list[str] = []
        skipped: list[str] = []
        try:
            for f in targets:
                bak = f.path.with_suffix(f.path.suffix + ".bak")
                if bak.exists() and not overwrite:
                    skipped.append(bak.name)
                    continue
                shutil.copy2(f.path, bak)
                written.append(bak.name)
        except OSError as e:
            QMessageBox.critical(self, "Backup failed", str(e))
            return

        msg = f"Created/updated {len(written)} backup(s)."
        if skipped:
            msg += f" Skipped {len(skipped)} existing .bak file(s)."
        self.status.showMessage(msg, 5000)
        detail = ""
        if written:
            detail += "Backed up:\n  " + "\n  ".join(written)
        if skipped:
            detail += ("\n\n" if detail else "") + "Skipped:\n  " + "\n  ".join(skipped)
        QMessageBox.information(self, "Backup complete", detail or msg)

    def _save_into_folder(self) -> None:
        if not self.db_folder:
            return
        written = []
        try:
            for lf, data in self._patched_paramdbs():
                bak = lf.path.with_suffix(lf.path.suffix + ".bak")
                if lf.path.exists() and not bak.exists():
                    shutil.copy2(lf.path, bak)
                lf.path.write_bytes(data)
                written.append(lf.name)
            (self.db_folder / "hybrids.txt").write_text(self._hybrid_summary_text(), encoding="utf-8")
            written.append("hybrids.txt")
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        self.status.showMessage(f"Wrote {len(written)} file(s)", 5000)
        QMessageBox.information(self, "Saved", "Updated:\n  " + "\n  ".join(written))

    def _export_zip(self) -> None:
        files = [(lf.name, data) for lf, data in self._patched_paramdbs()]
        files.append(("hybrids.txt", self._hybrid_summary_text().encode("utf-8")))
        data = make_zip(files)
        start = str(self.db_folder) if self.db_folder else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ZIP",
            str(Path(start) / "gt3-hybrid-paramdb.zip") if start else "gt3-hybrid-paramdb.zip",
            "ZIP (*.zip)",
        )
        if not path:
            return
        try:
            Path(path).write_bytes(data)
            self.status.showMessage(f"Saved {path}", 4000)
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_mode(self) -> None:
        self.mode = "copy" if self.radio_copy.isChecked() else "link"
        self._refresh_spec()

    def _on_region_tab(self, index: int) -> None:
        if index < 0:
            return
        self.active_region = index
        self.target = ""
        self._refresh()

    def _refresh(self) -> None:
        has = bool(self.db_folder and any(not r.error for r in self.regions))
        self.empty_state.setVisible(not has)
        self.work_area.setVisible(has)
        self.toolbar_path.setText(str(self.db_folder) if self.db_folder else "No database folder")
        ok = sum(1 for r in self.regions if not r.error)
        self.toolbar_regions.setText(f"{ok} region{'s' if ok != 1 else ''}" if self.regions else "")
        if not has:
            return
        self._refresh_region_tabs()
        self._refresh_target()
        self._refresh_groups()
        self._refresh_spec()
        self._refresh_changes()

    def _refresh_region_tabs(self) -> None:
        self.region_tabs.blockSignals(True)
        self.region_tabs.clear()
        for r in self.regions:
            self.region_tabs.addTab(QWidget(), r.label + (" !" if r.error else ""))
        if self.regions:
            self.region_tabs.setCurrentIndex(self.active_region)
        self.region_tabs.blockSignals(False)
        self.region_tabs.setVisible(len(self.regions) > 1)

    def _car_parts(self, hx: Optional[str], unset: str) -> Tuple[str, str, bool]:
        if not hx or hx == "keep":
            return (unset if hx != "keep" else "Keep this car's own", "", False)
        r = self._region()
        c = r.by_hex.get(hx) if r else None
        if c:
            return c.main, c.sub, True
        return f"#{hx[:8]}", "", True

    def _set_donor_btn(self, btn: QPushButton, main: str, sub: str, active: bool) -> None:
        btn.setText(main if not sub else f"{main}\n{sub}")
        if active:
            btn.setStyleSheet(
                "QPushButton#donor { text-align: left; padding: 5px 8px; "
                "border-color: #2563eb; background: #eff4ff; }"
            )
        else:
            btn.setStyleSheet("QPushButton#donor { text-align: left; padding: 5px 8px; }")

    def _refresh_target(self) -> None:
        main, sub, active = self._car_parts(self.target or None, "Choose a car")
        self._set_donor_btn(self.target_btn, main, sub, active)
        self.quick_btn.setEnabled(bool(self.target and self._region()))

    def _refresh_groups(self) -> None:
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        r = self._region()
        if not r or not self.target:
            return
        for g in GROUPS:
            if g["key"] == "info":
                items = list(INFO_DEFS)
            else:
                items = [d for d in PART_DEFS if d.group == g["key"] and d.key in r.visible]
            if not items:
                continue
            card = _card()
            gl = QVBoxLayout(card)
            gl.setContentsMargins(8, 5, 8, 5)
            gl.setSpacing(2)
            head = QHBoxLayout()
            head.addWidget(_label(g["label"], "cardTitle"))
            head.addStretch()
            open_key = g["key"]
            is_open = self.open_groups.get(open_key, False)
            toggle = QPushButton("Hide" if is_open else "Part by part")
            toggle.setObjectName("link")
            toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle.clicked.connect(lambda checked=False, k=open_key: self._toggle_group(k))
            head.addWidget(toggle)
            gl.addLayout(head)
            gl.addWidget(_label("TAKE ALL FROM", "fieldLabel"))
            gv = self.group.get(g["key"], "")
            main, sub, active = self._car_parts(gv or None, "Keep this car's own")
            gbtn = _donor_btn(main, sub, active)
            gbtn.clicked.connect(lambda checked=False, s=f"g:{g['key']}": self._pick(s))
            gl.addWidget(gbtn)
            if is_open:
                gl.addWidget(_rule())
                for d in items:
                    is_info = g["key"] == "info"
                    slot = f"i:{d.key}" if is_info else f"p:{d.key}"
                    sel = self.info_sel.get(d.key) if is_info else self.parts.get(d.key)
                    eff = self._effective(sel, self.group.get(g["key"]))
                    unset = "Group donor" if eff else "Keep this car's own"
                    main, sub, active = self._car_parts(sel if sel else None, unset)
                    row = QHBoxLayout()
                    row.setSpacing(8)
                    lab = QLabel(d.label)
                    lab.setStyleSheet("font-size: 12px;")
                    lab.setMinimumWidth(110)
                    row.addWidget(lab)
                    pbtn = _donor_btn(main, sub, active)
                    pbtn.setMinimumHeight(24)
                    pbtn.clicked.connect(lambda checked=False, s=slot: self._pick(s))
                    row.addWidget(pbtn, 1)
                    gl.addLayout(row)
            self.groups_layout.addWidget(card)

    def _toggle_group(self, key: str) -> None:
        self.open_groups[key] = not self.open_groups.get(key, False)
        self._refresh_groups()

    def _fmt(self, key: str, val) -> str:
        if key == "ps":
            return f"{val} PS" if val else "–"
        if key == "torque":
            return f"{val:.1f} kgf·m" if val is not None else "–"
        if key == "rev_limit":
            return f"{val:,} rpm" if val else "–"
        if key == "mass":
            return f"{val:,} kg" if val else "–"
        if key == "pw":
            return f"{val:.2f} kg/PS" if val is not None else "–"
        if key == "drive":
            return "–" if val is None else (DRIVE_NAMES[val] if val < len(DRIVE_NAMES) else str(val))
        if key == "gears":
            return f"{val}-spd" if val else "–"
        if key == "wheelbase":
            return f"{val} mm" if val else "–"
        if key == "price":
            return f"Cr {val:,}" if val is not None else "–"
        if key == "year":
            return str(val) if val else "–"
        if key == "type":
            return CAR_TYPES[val] if val is not None and val < len(CAR_TYPES) else str(val)
        return str(val) if val is not None else "–"

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
            # Scale power to listed peak PS when available so the graph matches the placard
            powers = list(curve.power)
            if curve.peak_ps and powers and max(powers) > 0:
                scale = curve.peak_ps / max(powers)
                powers = [p * scale for p in powers]
            self.dyno_ax.plot(curve.rpm, curve.torque, tq_style, label=tq_label, linewidth=1.6)
            self.dyno_ax2.plot(curve.rpm, powers, ps_style, label=ps_label, linewidth=1.6)

        if after and before and (
            after.rpm != before.rpm or after.torque != before.torque
        ):
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
        # Combined legend
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
        r = self._region()
        plan = self._build_plan()
        self.spec_table.setRowCount(0)
        self.plan_summary.setText("")
        self.apply_btn.setEnabled(False)
        if not r or not self.target or self.target not in r.by_hex:
            self.spec_title.setText("Spec sheet")
            self.spec_region_tag.setText("")
            self.spec_empty.setVisible(True)
            self.spec_table.setVisible(False)
            self._clear_dyno()
            return
        car = r.by_hex[self.target]
        self.spec_title.setText(car.main)
        self.spec_region_tag.setText(r.label)
        self.spec_empty.setVisible(False)
        self.spec_table.setVisible(True)
        before = car.stats
        after = before
        before_curve = engine_curve(r.db, car.index) if r.db else None
        after_curve = before_curve
        if not self._plan_empty(plan):
            assert plan is not None and r.db is not None
            copy_db, ti, _, stats = preview_plan(r.db, plan)
            if stats:
                after = stats
            if ti >= 0:
                after_curve = engine_curve(copy_db, ti)
            self.plan_summary.setText(self._describe_plan(plan))
            self.apply_btn.setEnabled(True)
        else:
            self.plan_summary.setText("Pick at least one donor to preview.")
        self._update_dyno(before_curve, after_curve)
        rows = [
            ("Power", "ps"), ("Torque", "torque"), ("Rev limit", "rev_limit"),
            ("Weight", "mass"), ("kg/PS", "pw"), ("Layout", "drive"),
            ("Gears", "gears"), ("Wheelbase", "wheelbase"),
            ("Price", "price"), ("Year", "year"), ("Class", "type"),
        ]
        accent_bg = QColor(COLORS["accent_soft"])
        accent_fg = QColor(COLORS["accent"])
        up_fg = QColor(COLORS.get("delta_up", "#16a34a"))
        down_fg = QColor(COLORS.get("delta_down", "#dc2626"))
        self.spec_table.setRowCount(len(rows))
        for i, (lab, key) in enumerate(rows):
            bv = getattr(before, key, None)
            av = getattr(after, key, None)
            b = self._fmt(key, bv)
            a = self._fmt(key, av)
            self.spec_table.setItem(i, 0, QTableWidgetItem(lab))
            self.spec_table.setItem(i, 1, QTableWidgetItem(b))
            item = QTableWidgetItem(a)
            if b != a:
                item.setBackground(accent_bg)
                item.setForeground(accent_fg)
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.spec_table.setItem(i, 2, item)
            delta = ""
            if isinstance(bv, (int, float)) and isinstance(av, (int, float)) and bv != av:
                d = av - bv
                if key in ("ps", "torque", "mass", "pw", "price", "rev_limit", "gears", "wheelbase", "year"):
                    if isinstance(d, float) and not float(d).is_integer():
                        delta = f"{d:+.1f}"
                    else:
                        delta = f"{d:+.0f}"
            d_item = QTableWidgetItem(delta)
            if delta.startswith("+"):
                d_item.setForeground(up_fg)
            elif delta.startswith("-"):
                d_item.setForeground(down_fg)
            self.spec_table.setItem(i, 3, d_item)

    def _refresh_changes(self) -> None:
        self.changes_table.setRowCount(0)
        for p in self.plans:
            r = self.changes_table.rowCount()
            self.changes_table.insertRow(r)
            n = len(p.picks) + len(p.info)
            mode = "overwrite" if p.mode == "copy" else "link"
            self.changes_table.setItem(r, 0, QTableWidgetItem(p.target_name))
            self.changes_table.setItem(r, 1, QTableWidgetItem(str(n)))
            self.changes_table.setItem(r, 2, QTableWidgetItem(mode))
            self.changes_table.setItem(r, 3, QTableWidgetItem(p.summary))
        n = len(self.plans)
        self.changes_count.setText(str(n))
        self.dl_btn.setText(f"Save hybrids… ({n})" if n else "Save hybrids…")
        self.dl_btn.setEnabled(bool(self.plans))

    def _edit_plan(self) -> None:
        row = self.changes_table.currentRow()
        if not (0 <= row < len(self.plans)):
            return
        plan = self.plans[row]
        self.target = plan.target
        self.group.clear()
        self.parts.clear()
        self.info_sel.clear()
        for k, v in plan.picks.items():
            self.parts[k] = v
        for k, v in plan.info.items():
            self.info_sel[k] = v
        self._refresh()
        self.status.showMessage(f"Editing · {plan.target_name}", 3000)

    def _duplicate_plan(self) -> None:
        row = self.changes_table.currentRow()
        if not (0 <= row < len(self.plans)):
            return
        src = self.plans[row]
        rec = PlanRecord(
            id=self.next_id,
            target=src.target,
            target_name=src.target_name,
            mode=src.mode,
            picks=dict(src.picks),
            info=dict(src.info),
            summary=src.summary,
        )
        self.next_id += 1
        self.plans.append(rec)
        self._replay()
        self._refresh()
        self.status.showMessage(f"Duplicated · {src.target_name}", 3000)



def main() -> int:
    import os
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    if HAS_MPL:
        try:
            matplotlib.use("QtAgg", force=True)
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("GT3 Hybrid Creator")
    app.setOrganizationName(SETTINGS_ORG)
    apply_app_theme(app)
    win = HybridGarage()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
