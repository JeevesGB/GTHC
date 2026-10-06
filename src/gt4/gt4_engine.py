from __future__ import annotations
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def _u8(b: bytes, off: int) -> int:
    return b[off]

def _i16(b: bytes, off: int, be: bool = False) -> int:
    return struct.unpack_from(">h" if be else "<h", b, off)[0]

def _u16(b: bytes, off: int, be: bool = False) -> int:
    return struct.unpack_from(">H" if be else "<H", b, off)[0]

def _i32(b: bytes, off: int, be: bool = False) -> int:
    return struct.unpack_from(">i" if be else "<i", b, off)[0]

def _u32(b: bytes, off: int, be: bool = False) -> int:
    return struct.unpack_from(">I" if be else "<I", b, off)[0]


@dataclass
class IdiTable:
    path: Path
    raw: bytes
    little: bool
    count: int
    table_id: int
    # id -> label
    labels: Dict[int, str] = field(default_factory=dict)
    entries: List[Tuple[int, str]] = field(default_factory=list)

def load_sdb(path: Path) -> List[str]:
    raw = path.read_bytes()
    if raw[:4] != b"GTST":
        raise ValueError(f"{path.name}: not GTST")
    count = _i32(raw, 4, False)
    strings: List[str] = []
    str_base = 0x10 + count * 4
    nul = 0  # marker for byte 0
    for i in range(count):
        off = _i32(raw, 0x10 + i * 4, False)
        pos = str_base + off + 2  # skip length prefix
        end = pos
        while end < len(raw) and raw[end] != 0:
            end += 1
        strings.append(raw[pos:end].decode("utf-8", errors="replace"))
    return strings

def load_idi(path: Path) -> IdiTable:
    raw = path.read_bytes()
    if raw[:4] != b"GTID":
        raise ValueError(f"{path.name}: not GTID")
    little = raw[4] != 0
    count = _i32(raw, 4, not little)
    table_id = _i32(raw, 0x0C, not little)
    entries: List[Tuple[int, str]] = []
    labels: Dict[int, str] = {}
    str_base = 0x10 + count * 8
    for i in range(count):
        label_off = _i32(raw, 0x10 + i * 8, not little)
        row_id = _i32(raw, 0x10 + i * 8 + 4, not little)
        pos = str_base + label_off + 2  # skip u16 length
        end = raw.find(b"\x00", pos)
        if end < 0:
            end = min(pos + 64, len(raw))
        label = raw[pos:end].decode("ascii", errors="replace")
        entries.append((row_id, label))
        labels[row_id] = label
    return IdiTable(path=path, raw=raw, little=little, count=count, table_id=table_id, labels=labels, entries=entries)

class DbtTable:
    def __init__(self, path: Path):
        self.path = path
        self.raw = path.read_bytes()
        if self.raw[:4] != b"GTDB":
            raise ValueError(f"{path.name}: not GTDB")
        t = struct.unpack_from("<H", self.raw, 4)[0]
        self.big = t >= 0x100
        be = self.big
        self.attr = _u16(self.raw, 4, be)
        self.aligned = _u16(self.raw, 6, be)
        self.row_count = _u32(self.raw, 8, be)
        self.row_size = _i32(self.raw, 12, be)
        self.compressed = (self.attr & 1) != 0

        self.row_ids: List[int] = []
        self.row_offs: List[int] = []
        for i in range(self.row_count):
            base = 0x10 + i * 8
            self.row_ids.append(_i32(self.raw, base, be))
            self.row_offs.append(_i32(self.raw, base + 4, be))

        pos = 0x10 + self.row_count * 8
        self.code_book_info = pos
        if self.compressed:
            self.data_list = pos + 0x08
            self.code_list = pos + 0x208
            rel = _i32(self.raw, pos, be)
            self.template_info = pos + rel
            self.template_data = self.template_info + 0x08
            rel2 = _i32(self.raw, self.template_info, be)
            self.data_block = self.template_info + rel2
        else:
            self.data_list = self.code_list = self.template_info = self.template_data = 0
            self.data_block = pos

    def get_row_by_index(self, index: int) -> bytes:
        if index < 0 or index >= self.row_count:
            raise IndexError(index)
        off = self.row_offs[index]
        pos = self.data_block + off
        if not self.compressed:
            return self.raw[pos : pos + self.row_size]
        return self._extract_row(pos)

    def get_row_by_id(self, row_id: int) -> Optional[bytes]:
        lo, hi = 0, self.row_count - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            cur = self.row_ids[mid]
            if cur == row_id:
                return self.get_row_by_index(mid)
            if cur < row_id:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def _extract_row(self, pos: int) -> bytes:
        huff = self._extract_huffman_part(pos)
        return self._extract_diff_dict(huff)

    def _extract_huffman_part(self, pos: int) -> bytes:
        part_count = self.raw[pos]
        out = bytearray(part_count)
        bit_offset = 0
        for i in range(part_count):
            current_byte = bit_offset // 8
            p = pos + current_byte + 1
            val = 0
            for sh in range(4):
                if p + sh < len(self.raw):
                    val |= self.raw[p + sh] << (8 * sh)
            val >>= bit_offset - current_byte * 8
            bits, byte_val = self._process_huffman_code(val)
            out[i] = byte_val
            bit_offset += bits
        return bytes(out)

    def _process_huffman_code(self, code: int) -> Tuple[int, int]:
        # lookup table for codes <= 8 bits
        lookup = self.data_list + (code & 0xFF) * 2
        code_bit_size = self.raw[lookup + 1]
        if code_bit_size == 0:
            return self._search_huffman_code(code)
        return code_bit_size, self.raw[lookup]

    def _search_huffman_code(self, code_bits: int) -> Tuple[int, int]:
        be = self.big
        for bit_index in range(9, 32):
            target = code_bits & ((1 << bit_index) - 1)
            entry_count = _i32(self.raw, self.code_book_info + 4, be)
            lo, hi = -1, entry_count
            while lo + 1 != hi:
                mid = (lo + hi) // 2
                entry = self.code_list + mid * 8
                code_bit_size = self.raw[entry]
                code = _i32(self.raw, entry + 4, be)
                if code == target and code_bit_size == bit_index:
                    return bit_index, self.raw[entry + 1]
                if bit_index > code_bit_size:
                    lo = mid
                elif bit_index < code_bit_size:
                    hi = mid
                elif target > code:
                    lo = mid
                else:
                    hi = mid
        raise ValueError("SearchHuffmanCode failed — table corrupt?")

    def _extract_diff_dict(self, entry: bytes) -> bytes:
        if not entry:
            raise ValueError("empty huffman entry")
        kind = entry[0] >> 6
        data_index = entry[0] & 0x3F
        raw_entry = entry[1:]
        row_size = self.row_size
        be = self.big

        if kind == 0:  # template copy
            off = self.template_data + data_index * row_size
            return self.raw[off : off + row_size]
        if kind == 1:  # raw row
            return raw_entry[:row_size]
        if kind == 2:  # template + bit patch
            off = self.template_data + data_index * row_size
            row = bytearray(self.raw[off : off + row_size])
            repl_off = 1 + row_size // 8
            if row_size % 8:
                repl_off += 1
            for i in range(row_size):
                if (raw_entry[i // 8] >> (i % 8)) & 1:
                    if repl_off < len(entry):
                        row[i] = entry[repl_off]
                        repl_off += 1
            return bytes(row)
        raise ValueError(f"unsupported compression type {kind}")

# (name, type, size) — type: key|i32|i16|u16|u8|i8|bool
GENERIC_CAR_COLS = [
    ("DefaultParts", "key", 8),
    ("Price", "i32", 4),
    ("Year", "i16", 2),
    ("RegulationDisplacementFlags", "i16", 2),
    ("Maker", "u8", 1),
    ("Category", "u8", 1),
    ("GeneralFlags", "u8", 1),
    ("ConceptCarType", "u8", 1),
    ("OpenModel", "u8", 1),
    ("NoChangeWheel", "u8", 1),
    ("NoChangeWing", "u8", 1),
    ("SuperchargerOriginally", "u8", 1),
]

DEFAULT_PARTS_COLS = [
    ("Brake", "key", 8),
    ("BrakeCtrl", "key", 8),
    ("Suspension", "key", 8),
    ("ASCC", "key", 8),
    ("TCSC", "key", 8),
    ("Chassis", "key", 8),
    ("RacingModify", "key", 8),
    ("Lightweight", "key", 8),
    ("Steer", "key", 8),
    ("DriveTrain", "key", 8),
    ("Gear", "key", 8),
    ("Engine", "key", 8),
    ("NATune", "key", 8),
    ("Turbo", "key", 8),
    ("Displacement", "key", 8),
    ("Computer", "key", 8),
    ("Intercooler", "key", 8),
    ("Muffler", "key", 8),
    ("Clutch", "key", 8),
    ("Flywheel", "key", 8),
    ("PropellerShaft", "key", 8),
    ("LSD", "key", 8),
    ("FrontTire", "key", 8),
    ("RearTire", "key", 8),
    ("F_Tire_G", "key", 8),
    ("R_Tire_G", "key", 8),
]
# Hybrid-relevant part slots (label for UI)
HYBRID_PARTS = [
    ("Engine", "Engine"),
    ("Chassis", "Chassis"),
    ("Gear", "Gear"),
    ("DriveTrain", "Drivetrain"),
    ("Suspension", "Suspension"),
    ("Brake", "Brake"),
    ("NATune", "NA Tune"),
    ("Turbo", "Turbo"),
    ("Muffler", "Muffler"),
    ("Clutch", "Clutch"),
    ("LSD", "LSD"),
    ("FrontTire", "Front tyre"),
    ("RearTire", "Rear tyre"),
]


def parse_row(data: bytes, cols: List[Tuple[str, str, int]], little: bool = True) -> Dict[str, object]:
    out: Dict[str, object] = {}
    pos = 0
    be = not little
    for name, typ, size in cols:
        if pos + size > len(data):
            break
        if typ == "key":
            if little:
                key = _i32(data, pos, False)
                table_id = _i32(data, pos + 4, False)
            else:
                table_id = _i32(data, pos, True)
                key = _i32(data, pos + 4, True)
            out[name] = (key, table_id)
        elif typ == "i32":
            out[name] = _i32(data, pos, be)
        elif typ == "i16":
            out[name] = _i16(data, pos, be)
        elif typ == "u16":
            out[name] = _u16(data, pos, be)
        elif typ in ("u8", "bool"):
            out[name] = data[pos]
        elif typ == "i8":
            out[name] = struct.unpack_from("b", data, pos)[0]
        pos += size
    return out


def write_key(buf: bytearray, off: int, key: int, table_id: int, little: bool = True) -> None:
    if little:
        struct.pack_into("<ii", buf, off, key, table_id)
    else:
        struct.pack_into(">ii", buf, off, table_id, key)


def col_offset(cols: List[Tuple[str, str, int]], name: str) -> int:
    pos = 0
    for n, _, size in cols:
        if n == name:
            return pos
        pos += size
    raise KeyError(name)


@dataclass
class CarInfo:
    row_id: int
    label: str
    name: str
    year: int
    price: int
    default_parts_id: int
    default_parts_table: int
    parts: Dict[str, Tuple[int, int]]  # part name -> (key, table_id)


@dataclass
class SpecDB:
    folder: Path
    cars: List[CarInfo] = field(default_factory=list)
    by_id: Dict[int, CarInfo] = field(default_factory=dict)
    by_label: Dict[str, CarInfo] = field(default_factory=dict)
    engine_labels: Dict[int, str] = field(default_factory=dict)
    engine_table: Optional[DbtTable] = None
    generic_car: Optional[DbtTable] = None
    default_parts: Optional[DbtTable] = None
    generic_car_idi: Optional[IdiTable] = None
    default_parts_idi: Optional[IdiTable] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class EngineCurve:
    rpm: List[int]
    torque: List[float]  # kgf·m
    power: List[float]   # PS
    peak_ps: Optional[float] = None
    peak_torque: Optional[float] = None
    rev_limit: Optional[int] = None


def engine_curve_from_row(row: bytes) -> Optional[EngineCurve]:
    if not row or len(row) < 100:
        return None
    # GT4 Premium: strings(6*4)=24, soundNum u16, psvalue i16, torquevalue i16,
    # torqueA-X (24 i16), then flags/rpm bytes.
    ps_raw = _i16(row, 28, False)
    tq_raw = _i16(row, 30, False)
    torques_raw = [_i16(row, 32 + 2 * i, False) for i in range(24)]
    # rpmA starts at offset 85 (empirical for GT4 Premium US)
    rpms_raw = list(row[85:85 + 24])
    # RedLine near end
    red = row[110] if len(row) > 110 else 0

    rpms: List[int] = []
    tqs: List[float] = []
    for i in range(24):
        t = torques_raw[i]
        r = rpms_raw[i]
        if t <= 0 or r <= 0:
            continue
        rpms.append(r * 100)
        tqs.append(t / 100.0)
    if not rpms:
        return None
    powers = [(tq * rpm) / 716.2 for tq, rpm in zip(tqs, rpms)]
    peak_ps = (ps_raw / 10.0) if ps_raw else None
    peak_tq = (tq_raw / 100.0) if tq_raw else (max(tqs) if tqs else None)
    return EngineCurve(
        rpm=rpms,
        torque=tqs,
        power=powers,
        peak_ps=peak_ps,
        peak_torque=peak_tq,
        rev_limit=(red * 100) if red else None,
    )

def engine_curve_for_car(db: "SpecDB", car: CarInfo) -> Optional[EngineCurve]:
    eng = car.parts.get("Engine")
    if not eng or not db.engine_table:
        return None
    row = db.engine_table.get_row_by_id(eng[0])
    if not row:
        return None
    return engine_curve_from_row(row)

def load_specdb(folder: Path) -> SpecDB:
    folder = folder.resolve()
    db = SpecDB(folder=folder)

    gc_dbt = folder / "GENERIC_CAR.dbt"
    gc_idi = folder / "GENERIC_CAR.idi"
    dp_dbt = folder / "DEFAULT_PARTS.dbt"
    dp_idi = folder / "DEFAULT_PARTS.idi"
    for p in (gc_dbt, gc_idi, dp_dbt, dp_idi):
        if not p.is_file():
            raise FileNotFoundError(f"Missing {p.name} in {folder}")

    db.generic_car = DbtTable(gc_dbt)
    db.generic_car_idi = load_idi(gc_idi)
    db.default_parts = DbtTable(dp_dbt)
    db.default_parts_idi = load_idi(dp_idi)

    eng_dbt = folder / "ENGINE.dbt"
    eng_idi = folder / "ENGINE.idi"
    if eng_dbt.is_file():
        try:
            db.engine_table = DbtTable(eng_dbt)
        except Exception as e:
            db.notes.append(f"ENGINE.dbt: {e}")
    if eng_idi.is_file():
        try:
            db.engine_labels = load_idi(eng_idi).labels
        except Exception as e:
            db.notes.append(f"ENGINE.idi: {e}")

    name_map: Dict[int, str] = {}
    grade_map: Dict[int, str] = {}
    for locale in ("american", "british", "japanese"):
        cn_dbt = folder / f"CAR_NAME_{locale}.dbt"
        sdb_path = folder / f"{locale}_StrDB.sdb"
        if not cn_dbt.is_file() or not sdb_path.is_file():
            continue
        try:
            strings = load_sdb(sdb_path)
            cn_t = DbtTable(cn_dbt)
            for idx, rid in enumerate(cn_t.row_ids):
                try:
                    row = cn_t.get_row_by_index(idx)
                except Exception:
                    continue
                if len(row) < 12:
                    continue
                name_i = _i32(row, 0, cn_t.big)
                grade_i = _i32(row, 4, cn_t.big)
                short_i = _i32(row, 8, cn_t.big)
                def _s(i: int) -> str:
                    return strings[i] if 0 <= i < len(strings) else ""
                name = _s(name_i) or _s(short_i) or _s(grade_i)
                if name:
                    name_map[rid] = name
                grade = _s(grade_i)
                if grade:
                    grade_map[rid] = grade
            if name_map:
                break
        except Exception as e:
            db.notes.append(f"CAR_NAME_{locale}: {e}")

    for idx, rid in enumerate(db.generic_car.row_ids):
        label = db.generic_car_idi.labels.get(rid, f"#{rid}")
        try:
            row = db.generic_car.get_row_by_index(idx)
        except Exception as e:
            db.notes.append(f"GENERIC_CAR id {rid}: {e}")
            continue
        parsed = parse_row(row, GENERIC_CAR_COLS, little=not db.generic_car.big)
        dp_key = parsed.get("DefaultParts")
        if not isinstance(dp_key, tuple):
            continue
        parts_id, parts_table = dp_key
        parts: Dict[str, Tuple[int, int]] = {}
        dp_row = db.default_parts.get_row_by_id(parts_id)
        if dp_row:
            dp_parsed = parse_row(dp_row, DEFAULT_PARTS_COLS, little=not db.default_parts.big)
            for pname, _, _ in DEFAULT_PARTS_COLS:
                v = dp_parsed.get(pname)
                if isinstance(v, tuple):
                    parts[pname] = v

        display = (name_map.get(rid) or "").strip() or label
        eng = parts.get("Engine")
        eng_lab = db.engine_labels.get(eng[0], "") if eng else ""
        car = CarInfo(
            row_id=rid,
            label=label,
            name=display,
            year=int(parsed.get("Year") or 0),
            price=int(parsed.get("Price") or 0),
            default_parts_id=parts_id,
            default_parts_table=parts_table,
            parts=parts,
        )
        db.cars.append(car)
        db.by_id[rid] = car
        db.by_label[label] = car

    db.cars.sort(key=lambda c: c.name.lower())
    return db

def apply_part_swap(
    db: SpecDB,
    target_id: int,
    part_name: str,
    donor_id: int,
) -> None:
    if db.default_parts is None or db.generic_car is None:
        raise RuntimeError("SpecDB not loaded")
    target = db.by_id[target_id]
    donor = db.by_id[donor_id]
    if part_name not in donor.parts:
        raise KeyError(f"Donor has no {part_name}")
    new_key = donor.parts[part_name]

    # Load mutable DEFAULT_PARTS row for target
    dp = db.default_parts
    # find index
    try:
        idx = dp.row_ids.index(target.default_parts_id)
    except ValueError as e:
        raise KeyError("target DEFAULT_PARTS row missing") from e

    row = bytearray(dp.get_row_by_index(idx))
    off = col_offset(DEFAULT_PARTS_COLS, part_name)
    write_key(row, off, new_key[0], new_key[1], little=not dp.big)

    target.parts[part_name] = new_key
