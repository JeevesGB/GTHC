from __future__ import annotations
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap

# GT4 / Tourist Trophy SpecDB maker IDs (hardcoded in-game)
GT4_MAKERS: Dict[int, str] = {
    0: '—',
    2: 'Acura',
    3: 'Alfa Romeo',
    4: 'Aston Martin',
    5: 'Audi',
    6: 'BMW',
    7: 'Chevrolet',
    8: 'Chrysler',
    9: 'Citroën',
    10: 'Daihatsu',
    11: 'Dodge',
    12: 'Fiat',
    13: 'Ford',
    14: 'Gillet',
    15: 'Honda',
    16: 'Hyundai',
    17: 'Jaguar',
    18: 'Lancia',
    19: 'Lister',
    20: 'Lotus',
    21: 'Mazda',
    22: 'Mercedes-Benz',
    23: 'MG',
    24: 'Mines',
    25: 'Mitsubishi',
    26: 'Mugen',
    27: 'Nismo',
    28: 'Nissan',
    29: 'Opel',
    30: 'Pagani',
    31: 'Panoz',
    32: 'Peugeot',
    33: 'Polyphony',
    34: 'Renault',
    35: 'Ruf',
    36: 'Shelby',
    37: 'Spoon',
    38: 'Subaru',
    39: 'Suzuki',
    41: 'Tommykaira',
    42: "Tom's",
    43: 'Toyota',
    44: 'TVR',
    46: 'Volkswagen',
    47: 'ASL',
    48: 'Dome',
    49: 'Infiniti',
    50: 'Lexus',
    51: 'Mini',
    52: 'Pontiac',
    53: 'Spyker',
    54: 'Cadillac',
    55: 'Plymouth',
    56: 'Isuzu',
    57: 'Autobianchi',
    58: 'Ginetta',
    59: 'Amuse',
    60: 'Saleen',
    62: 'Polyphony',
    63: 'Buick',
    64: 'Vemac',
    65: 'DMC',
    66: 'Eagle',
    67: 'Mercury',
    68: 'Triumph',
    69: 'Volvo',
    70: 'Hommell',
    71: 'Jensen',
    72: 'Marcos',
    73: 'Scion',
    74: 'Blitz',
    75: 'Cizeta',
    76: 'HKS',
    77: 'Pescarolo',
    78: 'FPV',
    79: 'Opera Performance',
    80: 'Caterham',
    81: 'AC',
    82: 'Bentley',
    83: 'SEAT',
    84: 'Land Rover',
    85: 'Holden',
    86: 'Alpine',
    87: 'RE Amemiya',
    88: 'Nike',
    90: 'Trial',
    91: 'Tickford',
    92: 'TRD',
    93: 'Chaparral',
    94: 'HPA',
    96: 'Spirra',
}

# Display name -> logo filename stem (under ui/brands/)
_BRAND_LOGO_FILES: Dict[str, str] = {
    "ac": "ac",
    "ac cars": "ac",
    "acura": "acura",
    "alfa romeo": "alfa-romeo",
    "alfa-romeo": "alfa-romeo",
    "audi": "audi",
    "bmw": "bmw",
    "chevrolet": "chevrolet",
    "chrysler": "chrysler",
    "citroen": "citroen",
    "citroën": "citroen",
    "daihatsu": "daihatsu",
    "dodge": "dodge",
    "fiat": "fiat",
    "ford": "ford",
    "ford au": "ford",
    "gillet": "gillet",
    "honda": "honda",
    "7honda": "honda",
    "jaguar": "jaguar",
    "lister": "lister",
    "lotus": "lotus",
    "mazda": "mazda",
    "mercedes": "mercedes-benz",
    "mercedes-benz": "mercedes-benz",
    "mines": "mines",
    "mini": "mini",
    "mg / mini": "mini",
    "mg": "mini",
    "mitsubishi": "mitsubishi",
    "mugen": "mugen",
    "nismo": "nismo",
    "nissan": "nissan",
    "opel": "opel",
    "pagani": "pagani",
    "panoz": "panoz",
    "peugeot": "peugeot",
    "renault": "renault",
    "ruf": "ruf",
    "spoon": "spoon",
    "subaru": "subaru",
    "suzuki": "suzuki",
    "tickford": "tickford",
    "tommykaira": "tommykaira",
    "tom's": "tom_s",
    "toms": "tom_s",
    "toyota": "toyota",
    "trd": "trd",
    "tvr": "tvr",
    "vauxhall": "vauxhall",
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
}

_BRAND_PALETTE = [
    "#1e40af", "#b91c1c", "#047857", "#7c3aed", "#c2410c",
    "#0e7490", "#be123c", "#4d7c0f", "#4338ca", "#a16207",
    "#155e75", "#9f1239", "#166534", "#5b21b6", "#9a3412",
]


def _brands_dir() -> Path:
    root = Path(__file__).resolve().parent
    # Frozen (PyInstaller): logos live under _MEIPASS/ui/brands
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = Path(meipass) / "ui" / "brands"
        if cand.is_dir():
            return cand
    return root / "brands"


def maker_name(maker_id: int) -> str:
    return GT4_MAKERS.get(int(maker_id), f"Maker {maker_id}")


def brand_color(brand: str) -> QColor:
    if not brand or brand == "—":
        return QColor("#6b7280")
    h = sum(ord(c) for c in brand.lower())
    return QColor(_BRAND_PALETTE[h % len(_BRAND_PALETTE)])


def brand_initials(brand: str) -> str:
    if not brand or brand == "—":
        return "?"
    parts = [p for p in brand.replace("-", " ").replace("/", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    s = parts[0] if parts else brand
    return s[:2].upper()


def _logo_stem(brand: str) -> Optional[str]:
    key = (brand or "").strip().lower()
    if not key or key == "—":
        return None
    if key in _BRAND_LOGO_FILES:
        return _BRAND_LOGO_FILES[key]
    # fuzzy: strip punctuation
    key2 = key.replace("é", "e").replace("ü", "u")
    if key2 in _BRAND_LOGO_FILES:
        return _BRAND_LOGO_FILES[key2]
    return None


def brand_logo_path(brand: str) -> Optional[Path]:
    stem = _logo_stem(brand)
    if not stem:
        return None
    path = _brands_dir() / f"{stem}.png"
    return path if path.is_file() else None


def _generated_badge(brand: str, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = brand_color(brand)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 4, 4)
    p.fillPath(path, color)
    p.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", max(7, size // 3))
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, brand_initials(brand))
    p.end()
    return pm


@lru_cache(maxsize=256)
def brand_badge_pixmap(brand: str, size: int = 22) -> QPixmap:
    """Real PNG logo when available, otherwise a generated initials badge."""
    path = brand_logo_path(brand)
    if path is not None:
        src = QPixmap(str(path))
        if not src.isNull():
            return src.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return _generated_badge(brand, size)


def guess_brand_from_text(*parts: str) -> str:
    """Best-effort brand from free-text (GT3 string tables)."""
    blob = " ".join(p for p in parts if p).strip()
    if not blob:
        return "—"
    lower = blob.lower()
    # Logo stems as extra aliases (mines, nismo, spoon, …)
    extra = [k.title() if k.islower() else k for k in _BRAND_LOGO_FILES]
    names = sorted(
        set(list(GT4_MAKERS.values()) + list(_BRAND_LOGO_FILES.keys())),
        key=len,
        reverse=True,
    )
    for name in names:
        if not name or name == "—":
            continue
        if name.lower() in lower:
            # Prefer canonical display form when we know it
            for mid, disp in GT4_MAKERS.items():
                if disp.lower() == name.lower():
                    return disp
            # Title-case logo key
            stem = _BRAND_LOGO_FILES.get(name.lower())
            if stem:
                for disp in GT4_MAKERS.values():
                    if _logo_stem(disp) == stem:
                        return disp
            return name.title() if name.islower() else name
    first = blob.split()[0]
    for name in GT4_MAKERS.values():
        if name == "—":
            continue
        if name.lower().startswith(first.lower()) or first.lower().startswith(name.lower()[:4]):
            return name
    return first.title() if first else "—"
