"""Car picker — brand icons first, then a searchable list for that maker."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont, QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.design import APP_STYLE
from ui.makers import brand_badge_pixmap, guess_brand_from_text


@dataclass
class PickerCar:
    id: Any
    name: str
    sub: str = ""
    search: str = ""
    year: int = 0
    power: float = 0.0
    layout: str = ""
    extra: str = ""
    brand: str = ""


def _label(text: str, obj: str = "") -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    return lab


def _clean_name(name: str) -> str:
    s = (name or "").strip()
    while s and s[0] in "-–—·•|_/\\":
        s = s[1:].strip()
    return s or name or "—"


def _normalize_brand(brand: str, name: str = "") -> str:
    b = (brand or "").strip()
    if not b or b == "—":
        b = guess_brand_from_text(name, brand) or "Other"
    if not b or b == "—":
        return "Other"
    return b


class CarPickerDialog(QDialog):
    """Two-step picker: manufacturer grid → car list."""

    COLS = ("", "Name", "Year", "Power", "Layout", "Details")
    BRAND_ICON = 72
    BRAND_TILE = 110

    def __init__(
        self,
        cars: Sequence[PickerCar],
        title: str = "Choose a car",
        specials: Optional[List[Tuple[Any, str, str]]] = None,
        parent=None,
        brand_first: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 620)
        self.setMinimumSize(640, 460)
        self.setStyleSheet(APP_STYLE)
        self._cars = list(cars)
        self._specials = specials or []
        self._result: Any = None
        self._brand_filter = ""
        self._brand_first = brand_first

        # Group by brand
        self._by_brand: Dict[str, List[PickerCar]] = defaultdict(list)
        for c in self._cars:
            b = _normalize_brand(c.brand, c.name)
            c.brand = b
            if not c.search:
                c.search = f"{c.name} {c.sub} {c.brand} {c.year} {c.power}".lower()
            self._by_brand[b].append(c)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header row
        head = QHBoxLayout()
        self.title_lab = _label(title, "cardTitle")
        head.addWidget(self.title_lab, 1)
        self.back_btn = QPushButton("← All manufacturers")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self._show_brands)
        head.addWidget(self.back_btn)
        root.addLayout(head)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # ---- Page 0: brand grid ----
        brand_page = QWidget()
        bp = QVBoxLayout(brand_page)
        bp.setContentsMargins(0, 0, 0, 0)
        bp.setSpacing(6)
        bp.addWidget(_label("Select a manufacturer", "muted"))

        brand_search_row = QHBoxLayout()
        self.brand_search = QLineEdit()
        self.brand_search.setPlaceholderText("Filter manufacturers…")
        self.brand_search.setClearButtonEnabled(True)
        self.brand_search.textChanged.connect(self._filter_brands)
        brand_search_row.addWidget(self.brand_search, 1)
        bp.addLayout(brand_search_row)

        self.brand_list = QListWidget()
        self.brand_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.brand_list.setIconSize(QSize(self.BRAND_ICON, self.BRAND_ICON))
        self.brand_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.brand_list.setMovement(QListWidget.Movement.Static)
        self.brand_list.setSpacing(10)
        self.brand_list.setWordWrap(True)
        self.brand_list.setUniformItemSizes(True)
        self.brand_list.setGridSize(QSize(self.BRAND_TILE, self.BRAND_TILE + 28))
        self.brand_list.itemClicked.connect(self._on_brand_clicked)
        self.brand_list.itemDoubleClicked.connect(self._on_brand_clicked)
        bp.addWidget(self.brand_list, 1)
        self.brand_count_lab = _label("", "muted")
        bp.addWidget(self.brand_count_lab)
        self.stack.addWidget(brand_page)

        # ---- Page 1: car table ----
        car_page = QWidget()
        cp = QVBoxLayout(car_page)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(6)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, power, year…  (/ to focus)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_cars)
        top.addWidget(self.search, 1)

        self.sort_box = QComboBox()
        self.sort_box.addItem("Name A–Z", "name")
        self.sort_box.addItem("Year ↑", "year_asc")
        self.sort_box.addItem("Year ↓", "year_desc")
        self.sort_box.addItem("Power ↑", "power_asc")
        self.sort_box.addItem("Power ↓", "power_desc")
        self.sort_box.currentIndexChanged.connect(self._filter_cars)
        top.addWidget(self.sort_box)
        cp.addLayout(top)

        yr = QHBoxLayout()
        yr.addWidget(_label("Year", "fieldLabel"))
        self.year_min = QLineEdit()
        self.year_min.setPlaceholderText("min")
        self.year_min.setFixedWidth(56)
        self.year_min.setClearButtonEnabled(True)
        self.year_min.textChanged.connect(self._filter_cars)
        yr.addWidget(self.year_min)
        yr.addWidget(QLabel("–"))
        self.year_max = QLineEdit()
        self.year_max.setPlaceholderText("max")
        self.year_max.setFixedWidth(56)
        self.year_max.setClearButtonEnabled(True)
        self.year_max.textChanged.connect(self._filter_cars)
        yr.addWidget(self.year_max)
        yr.addStretch()
        yr.addWidget(_label("Double-click a row to select", "muted"))
        cp.addLayout(yr)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(list(self.COLS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setIconSize(QSize(28, 28))
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 44)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._accept_row)
        cp.addWidget(self.table, 1)

        self.count_lab = _label("", "muted")
        cp.addWidget(self.count_lab)
        self.stack.addWidget(car_page)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._populate_brands()
        if brand_first:
            self._show_brands()
        else:
            self._brand_filter = ""
            self._show_cars("")

    # ------------------------------------------------------------------ brands
    def _populate_brands(self, filter_text: str = "") -> None:
        self.brand_list.clear()
        ft = (filter_text or "").strip().lower()
        brands = sorted(self._by_brand.keys(), key=lambda s: s.lower())
        # Put "Other" last
        if "Other" in brands:
            brands = [b for b in brands if b != "Other"] + ["Other"]
        shown = 0
        for b in brands:
            if ft and ft not in b.lower():
                continue
            count = len(self._by_brand[b])
            item = QListWidgetItem(f"{b}\n{count}")
            item.setData(Qt.ItemDataRole.UserRole, b)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            pm = brand_badge_pixmap(b, self.BRAND_ICON)
            item.setIcon(QIcon(pm))
            item.setSizeHint(QSize(self.BRAND_TILE, self.BRAND_TILE + 24))
            item.setToolTip(f"{b} — {count} car{'s' if count != 1 else ''}")
            self.brand_list.addItem(item)
            shown += 1
        self.brand_count_lab.setText(f"{shown} manufacturer{'s' if shown != 1 else ''}")

    def _filter_brands(self, *_args) -> None:
        self._populate_brands(self.brand_search.text())

    def _on_brand_clicked(self, item: QListWidgetItem) -> None:
        brand = item.data(Qt.ItemDataRole.UserRole)
        if not brand:
            return
        self._show_cars(str(brand))

    def _show_brands(self) -> None:
        self._brand_filter = ""
        self.back_btn.setVisible(False)
        self.title_lab.setText(self.windowTitle())
        self.stack.setCurrentIndex(0)
        self.brand_search.setFocus()

    def _show_cars(self, brand: str) -> None:
        self._brand_filter = brand
        self.back_btn.setVisible(bool(brand) and self._brand_first)
        if brand:
            self.title_lab.setText(brand)
        else:
            self.title_lab.setText(self.windowTitle())
        self.stack.setCurrentIndex(1)
        self.search.clear()
        self._filter_cars()
        self.search.setFocus()

    # ------------------------------------------------------------------ cars
    def _add_row(
        self,
        car_id: Any,
        name: str,
        year: str,
        power: str,
        layout: str,
        details: str,
        brand: str,
    ) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        badge = QTableWidgetItem()
        badge.setData(Qt.ItemDataRole.UserRole, car_id)
        badge.setIcon(QIcon(brand_badge_pixmap(brand, 28)))
        badge.setFlags(badge.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, 0, badge)
        self.table.setItem(r, 1, QTableWidgetItem(_clean_name(name)))
        self.table.setItem(r, 2, QTableWidgetItem(year))
        self.table.setItem(r, 3, QTableWidgetItem(power))
        self.table.setItem(r, 4, QTableWidgetItem(layout))
        self.table.setItem(r, 5, QTableWidgetItem(details))

    def _filter_cars(self, *_args) -> None:
        self.table.setRowCount(0)
        terms = [t for t in self.search.text().lower().split() if t]
        sort_key = self.sort_box.currentData() or "name"

        def year_ok(y: int) -> bool:
            try:
                ymin = int(self.year_min.text()) if self.year_min.text().strip() else None
            except ValueError:
                ymin = None
            try:
                ymax = int(self.year_max.text()) if self.year_max.text().strip() else None
            except ValueError:
                ymax = None
            if ymin is not None and y and y < ymin:
                return False
            if ymax is not None and y and y > ymax:
                return False
            return True

        if self._brand_filter:
            pool = list(self._by_brand.get(self._brand_filter, []))
        else:
            pool = list(self._cars)

        hits: List[PickerCar] = []
        for c in pool:
            blob = (c.search or f"{c.name} {c.brand} {c.year} {c.power}").lower()
            if terms and not all(t in blob for t in terms):
                continue
            if not year_ok(int(c.year or 0)):
                continue
            hits.append(c)

        def sort_fn(c: PickerCar):
            if sort_key == "year_asc":
                return (c.year or 0, c.name.lower())
            if sort_key == "year_desc":
                return (-(c.year or 0), c.name.lower())
            if sort_key == "power_asc":
                return (c.power or 0, c.name.lower())
            if sort_key == "power_desc":
                return (-(c.power or 0), c.name.lower())
            return c.name.lower()

        hits.sort(key=sort_fn)

        for c in hits:
            year = str(c.year) if c.year else ""
            if c.power:
                power = f"{c.power:.0f} PS" if c.power >= 10 else f"{c.power:.1f} PS"
            else:
                power = ""
            bits = [p.strip() for p in (c.sub, c.extra) if p and p.strip()]
            self._add_row(
                c.id,
                c.name,
                year,
                power,
                c.layout or "",
                " · ".join(bits),
                c.brand,
            )

        brand_note = f" · {self._brand_filter}" if self._brand_filter else ""
        self.count_lab.setText(f"{len(hits)} car{'s' if len(hits) != 1 else ''}{brand_note}")
        if self.table.rowCount():
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 1)

    def _row_id(self, row: int) -> Any:
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _accept_row(self, row: int, _col: int = 0) -> None:
        if row < 0:
            return
        self._result = self._row_id(row)
        self.accept()

    def _accept(self) -> None:
        if self.stack.currentIndex() == 0:
            # On brand page: enter selected brand instead of closing empty
            items = self.brand_list.selectedItems()
            if items:
                self._on_brand_clicked(items[0])
            return
        row = self.table.currentRow()
        if row >= 0:
            self._result = self._row_id(row)
            self.accept()

    def selected(self) -> Any:
        return self._result

    def selected_hex(self) -> Any:
        return self._result

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Slash:
            if self.stack.currentIndex() == 0:
                self.brand_search.setFocus()
                self.brand_search.selectAll()
            else:
                self.search.setFocus()
                self.search.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Backspace and self.stack.currentIndex() == 1:
            if not self.search.hasFocus() or not self.search.text():
                self._show_brands()
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.stack.currentIndex() == 1:
                self._accept()
                event.accept()
                return
        super().keyPressEvent(event)
