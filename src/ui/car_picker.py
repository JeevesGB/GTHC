from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.design import APP_STYLE
from ui.makers import brand_badge_pixmap


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


class CarPickerDialog(QDialog):

    COLS = ("", "Brand", "Name", "Year", "Power", "Layout", "Details")

    def __init__(
        self,
        cars: Sequence[PickerCar],
        title: str = "Choose a car",
        specials: Optional[List[Tuple[Any, str, str]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 580)
        self.setMinimumSize(600, 420)
        self.setStyleSheet(APP_STYLE)
        self._cars = list(cars)
        self._specials = specials or []
        self._result: Any = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.addWidget(_label(title, "cardTitle"))

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, brand, power, year…  (/ to focus)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)

        self.brand_box = QComboBox()
        self.brand_box.setMinimumWidth(140)
        self.brand_box.addItem("All brands", "")
        brands = sorted({(c.brand or "").strip() for c in self._cars if (c.brand or "").strip() and c.brand != "—"})
        for b in brands:
            self.brand_box.addItem(b, b)
        self.brand_box.currentIndexChanged.connect(self._filter)
        top.addWidget(self.brand_box)

        self.sort_box = QComboBox()
        self.sort_box.addItem("Brand A–Z", "brand")
        self.sort_box.addItem("Name A–Z", "name")
        self.sort_box.addItem("Year ↑", "year_asc")
        self.sort_box.addItem("Year ↓", "year_desc")
        self.sort_box.addItem("Power ↑", "power_asc")
        self.sort_box.addItem("Power ↓", "power_desc")
        self.sort_box.currentIndexChanged.connect(self._filter)
        top.addWidget(self.sort_box)
        root.addLayout(top)

        yr = QHBoxLayout()
        yr.addWidget(_label("Year", "fieldLabel"))
        self.year_min = QLineEdit()
        self.year_min.setPlaceholderText("min")
        self.year_min.setFixedWidth(56)
        self.year_min.setClearButtonEnabled(True)
        self.year_min.textChanged.connect(self._filter)
        yr.addWidget(self.year_min)
        yr.addWidget(QLabel("–"))
        self.year_max = QLineEdit()
        self.year_max.setPlaceholderText("max")
        self.year_max.setFixedWidth(56)
        self.year_max.setClearButtonEnabled(True)
        self.year_max.textChanged.connect(self._filter)
        yr.addWidget(self.year_max)
        yr.addStretch()
        yr.addWidget(_label("Double-click a row to select", "muted"))
        root.addLayout(yr)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(list(self.COLS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        from PyQt6.QtCore import QSize as _QSize
        self.table.setIconSize(_QSize(28, 28))
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # badge
        self.table.setColumnWidth(0, 44)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._accept_row)
        root.addWidget(self.table, 1)

        self.count_lab = _label("", "muted")
        root.addWidget(self.count_lab)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._filter()
        self.search.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Slash and not self.search.hasFocus():
            self.search.setFocus()
            self.search.selectAll()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.table.currentRow() >= 0:
                self._accept()
                event.accept()
                return
        super().keyPressEvent(event)

    def _parse_year(self, edit: QLineEdit) -> Optional[int]:
        t = edit.text().strip()
        if not t:
            return None
        try:
            return int(t)
        except ValueError:
            return None

    def _add_row(
        self,
        row_id: Any,
        brand: str,
        name: str,
        year: str,
        power: str,
        layout: str,
        details: str,
        special: bool = False,
    ) -> None:
        from PyQt6.QtGui import QIcon

        r = self.table.rowCount()
        self.table.insertRow(r)

        # Badge
        badge_item = QTableWidgetItem()
        badge_item.setData(Qt.ItemDataRole.UserRole, row_id)
        badge_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if not special and brand and brand != "—":
            badge_item.setIcon(QIcon(brand_badge_pixmap(brand, 28)))
            badge_item.setToolTip(brand)
        self.table.setItem(r, 0, badge_item)

        cells = [brand if not special else "", name, year, power, layout, details]
        bold = QFont()
        bold.setBold(True)
        for col, text in enumerate(cells, start=1):
            item = QTableWidgetItem(text)
            if col == 2 and not special:
                item.setFont(bold)
            if special:
                item.setForeground(Qt.GlobalColor.darkGray)
            if col in (3, 4):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, col, item)

    def _filter(self, *_args) -> None:
        self.table.setRowCount(0)
        terms = [t for t in self.search.text().lower().split() if t]
        y_min = self._parse_year(self.year_min)
        y_max = self._parse_year(self.year_max)
        sort_key = self.sort_box.currentData()
        brand_filter = self.brand_box.currentData() or ""

        if not terms and y_min is None and y_max is None and not brand_filter:
            for sid, main, sub in self._specials:
                self._add_row(sid, "", main, "", "", "", sub or "", special=True)

        hits: List[PickerCar] = []
        for c in self._cars:
            if brand_filter and (c.brand or "") != brand_filter:
                continue
            if y_min is not None and (not c.year or c.year < y_min):
                continue
            if y_max is not None and (not c.year or c.year > y_max):
                continue
            blob = (
                c.search
                or f"{c.name} {c.sub} {c.year} {c.layout} {c.extra} {c.power} {c.brand}"
            ).lower()
            if all(t in blob for t in terms):
                hits.append(c)

        def name_key(c: PickerCar) -> str:
            return _clean_name(c.name).lower()

        if sort_key == "brand":
            hits.sort(key=lambda c: ((c.brand or "ÿ").lower(), name_key(c)))
        elif sort_key == "year_asc":
            hits.sort(key=lambda c: (c.year or 9999, name_key(c)))
        elif sort_key == "year_desc":
            hits.sort(key=lambda c: (-(c.year or 0), name_key(c)))
        elif sort_key == "power_asc":
            hits.sort(key=lambda c: (c.power or 0, name_key(c)))
        elif sort_key == "power_desc":
            hits.sort(key=lambda c: (-(c.power or 0), name_key(c)))
        else:
            hits.sort(key=name_key)

        for c in hits:
            name = _clean_name(c.name)
            year = str(c.year) if c.year else ""
            if c.power:
                power = (
                    f"{c.power:.0f} PS"
                    if float(c.power) == int(c.power)
                    else f"{c.power} PS"
                )
            else:
                power = ""
            layout = c.layout or ""
            bits = []
            for part in (c.sub, c.extra):
                if part and part.strip():
                    bits.append(part.strip())
            details = " · ".join(bits)
            self._add_row(c.id, c.brand or "—", name, year, power, layout, details)

        self.count_lab.setText(
            f"{len(hits)} cars"
            + (f" · {brand_filter}" if brand_filter else "")
        )
        if self.table.rowCount():
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 2)

    def _row_id(self, row: int) -> Any:
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _accept_row(self, row: int, _col: int = 0) -> None:
        if row < 0:
            return
        self._result = self._row_id(row)
        self.accept()

    def _accept(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self._result = self._row_id(row)
        self.accept()

    def selected(self) -> Any:
        return self._result

    def selected_hex(self) -> Any:
        return self._result
