from __future__ import annotations
import struct
import zipfile
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

        # index -> modified row bytes (after hybrid edits)
        self.dirty_rows: Dict[int, bytes] = {}

    def get_row_by_index(self, index: int) -> bytes:
        if index < 0 or index >= self.row_count:
            raise IndexError(index)
        if index in self.dirty_rows:
            return self.dirty_rows[index]
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

    def set_row_by_index(self, index: int, data: bytes) -> None:
        if index < 0 or index >= self.row_count:
            raise IndexError(index)
        if len(data) != self.row_size:
            raise ValueError(
                f"row size {len(data)} != expected {self.row_size}"
            )
        self.dirty_rows[index] = bytes(data)

    def append_row(self, row_id: int, data: bytes) -> int:
        """Append a new row. Returns the new index. Marks it dirty."""
        if len(data) != self.row_size:
            raise ValueError(
                f"row size {len(data)} != expected {self.row_size}"
            )
        if row_id in self.row_ids:
            raise ValueError(f"row id {row_id} already exists")
        idx = self.row_count
        self.row_ids.append(int(row_id))
        self.row_offs.append(0)  # unused once dirty
        self.dirty_rows[idx] = bytes(data)
        self.row_count += 1
        return idx

    def to_uncompressed_bytes(self) -> bytes:
        """Serialize the full table as an uncompressed GTDB file.

        SpecDB loaders accept both compressed and uncompressed tables.
        Writing uncompressed avoids re-implementing Huffman encoding.
        """
        be = self.big
        # Clear the compress bit; keep endianness signalling intact.
        attr = self.attr & ~1
        if be and attr < 0x100:
            attr |= 0x100

        header = bytearray(16)
        header[0:4] = b"GTDB"
        if be:
            struct.pack_into(">HHI i", header, 4, attr, self.aligned, self.row_count, self.row_size)
        else:
            struct.pack_into("<HHI i", header, 4, attr, self.aligned, self.row_count, self.row_size)

        index_block = bytearray(self.row_count * 8)
        data_block = bytearray()
        for i in range(self.row_count):
            rid = self.row_ids[i]
            off = len(data_block)
            if be:
                struct.pack_into(">ii", index_block, i * 8, rid, off)
            else:
                struct.pack_into("<ii", index_block, i * 8, rid, off)
            data_block.extend(self.get_row_by_index(i))

        return bytes(header) + bytes(index_block) + bytes(data_block)

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
    maker_id: int = 0
    brand: str = ""


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


# ---------------------------------------------------------------------------
# Fine-tune support (engine curve, chassis, suspension)
# ---------------------------------------------------------------------------

@dataclass
class FineTuneEngine:
    rpm: List[int] = field(default_factory=list)
    torque: List[float] = field(default_factory=list)
    peak_ps: Optional[float] = None
    peak_torque: Optional[float] = None
    rev_limit: Optional[int] = None
    idle_rpm: Optional[int] = None

@dataclass
class FineTuneChassis:
    mass: Optional[int] = None
    wheelbase: Optional[int] = None
    percentage_f: Optional[int] = None   # front weight %
    performance_f: Optional[int] = None  # front grip
    performance_r: Optional[int] = None  # rear grip
    yaw: Optional[int] = None

@dataclass
class FineTuneSuspension:
    """Best-effort suspension fields. Values are raw game units."""
    spring_rate_f: Optional[int] = None
    spring_rate_r: Optional[int] = None
    ride_height_f: Optional[int] = None
    ride_height_r: Optional[int] = None
    damper_f: Optional[int] = None
    damper_r: Optional[int] = None

@dataclass
class FineTuneDrivetrain:
    drive: Optional[int] = None  # 0=FR 1=FF 2=4WD 3=MR 4=RR
    gears: Optional[int] = None
    ratio_1: Optional[float] = None
    ratio_2: Optional[float] = None
    ratio_3: Optional[float] = None
    ratio_4: Optional[float] = None
    ratio_5: Optional[float] = None
    ratio_6: Optional[float] = None
    ratio_7: Optional[float] = None
    ratio_8: Optional[float] = None

@dataclass
class FineTuneInfo:
    price: Optional[int] = None
    year: Optional[int] = None

@dataclass
class FineTuneData:
    engine: Optional[FineTuneEngine] = None
    chassis: Optional[FineTuneChassis] = None
    suspension: Optional[FineTuneSuspension] = None
    drivetrain: Optional[FineTuneDrivetrain] = None
    info: Optional[FineTuneInfo] = None

def _pack_i16(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into("<h", buf, off, int(val))

def _pack_u16(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into("<H", buf, off, int(val) & 0xFFFF)

def read_engine_finetune_from_row(row: bytes) -> Optional[FineTuneEngine]:
    curve = engine_curve_from_row(row)
    if not curve:
        return None
    idle = row[88] if len(row) > 88 else 0  # empirical; may vary
    return FineTuneEngine(
        rpm=list(curve.rpm),
        torque=list(curve.torque),
        peak_ps=curve.peak_ps,
        peak_torque=curve.peak_torque,
        rev_limit=curve.rev_limit,
        idle_rpm=(idle * 100) if idle else None,
    )

def write_engine_finetune_to_row(row: bytes, ft: FineTuneEngine) -> bytes:
    buf = bytearray(row)
    if len(buf) < 110:
        return row
    # clear torque/rpm slots
    for i in range(24):
        _pack_i16(buf, 32 + 2 * i, 0)
        if 85 + i < len(buf):
            buf[85 + i] = 0
    n = min(24, len(ft.rpm), len(ft.torque))
    for i in range(n):
        rpm = int(ft.rpm[i])
        tq = float(ft.torque[i])
        if rpm <= 0 or tq <= 0:
            continue
        _pack_i16(buf, 32 + 2 * i, int(round(tq * 100)))
        if 85 + i < len(buf):
            buf[85 + i] = max(1, min(255, int(round(rpm / 100))))
    if ft.peak_ps is not None:
        _pack_i16(buf, 28, int(round(ft.peak_ps * 10)))
    if ft.peak_torque is not None:
        _pack_i16(buf, 30, int(round(ft.peak_torque * 100)))
    if ft.rev_limit is not None and len(buf) > 110:
        buf[110] = max(0, min(255, int(round(ft.rev_limit / 100))))
    if ft.idle_rpm is not None and len(buf) > 88:
        buf[88] = max(0, min(255, int(round(ft.idle_rpm / 100))))
    return bytes(buf)

# CHASSIS layout for GT4 Premium (37-byte data rows, little-endian):
# Empirical mapping against known spreadsheet values:
#   u16@0 length, u16@2 height, u16@4 wheelbase, u16@6 mass,
#   u16@8 dlength, u16@10 dheight, u16@12 dmass,
#   u8@14 performanceF, u8@15 performanceR,
#   ... percentageF around offset 26-28
# Confirmed from docs + sample rows.
CHASSIS_OFF = {
    "wheelbase": 4,   # u16
    "mass": 6,        # u16
    "performance_f": 14,  # u8
    "performance_r": 15,  # u8
    "percentage_f": 26,   # u8 (approx)
    "yaw": 28,            # u8 (approx)
}

def read_chassis_finetune_from_row(row: bytes) -> Optional[FineTuneChassis]:
    if not row or len(row) < 16:
        return None
    return FineTuneChassis(
        wheelbase=_u16(row, CHASSIS_OFF["wheelbase"], False) or None,
        mass=_u16(row, CHASSIS_OFF["mass"], False) or None,
        performance_f=row[CHASSIS_OFF["performance_f"]] if len(row) > 15 else None,
        performance_r=row[CHASSIS_OFF["performance_r"]] if len(row) > 15 else None,
        percentage_f=row[CHASSIS_OFF["percentage_f"]] if len(row) > 26 else None,
        yaw=row[CHASSIS_OFF["yaw"]] if len(row) > 28 else None,
    )

def write_chassis_finetune_to_row(row: bytes, ft: FineTuneChassis) -> bytes:
    buf = bytearray(row)
    if ft.wheelbase is not None and len(buf) > 6:
        _pack_u16(buf, CHASSIS_OFF["wheelbase"], ft.wheelbase)
    if ft.mass is not None and len(buf) > 8:
        _pack_u16(buf, CHASSIS_OFF["mass"], ft.mass)
    if ft.performance_f is not None and len(buf) > 15:
        buf[CHASSIS_OFF["performance_f"]] = ft.performance_f & 0xFF
    if ft.performance_r is not None and len(buf) > 15:
        buf[CHASSIS_OFF["performance_r"]] = ft.performance_r & 0xFF
    if ft.percentage_f is not None and len(buf) > 26:
        buf[CHASSIS_OFF["percentage_f"]] = ft.percentage_f & 0xFF
    if ft.yaw is not None and len(buf) > 28:
        buf[CHASSIS_OFF["yaw"]] = ft.yaw & 0xFF
    return bytes(buf)

# SUSPENSION: first 6 u16s often look like spring-related repeated values
SUSP_OFF = {
    "spring_rate_f": 0,   # u16
    "spring_rate_r": 2,   # u16
    "ride_height_f": 12,  # u16 (empirical)
    "ride_height_r": 14,  # u16
    "damper_f": 45,       # u8 cluster
    "damper_r": 46,       # u8
}

def read_suspension_finetune_from_row(row: bytes) -> Optional[FineTuneSuspension]:
    if not row or len(row) < 16:
        return None
    return FineTuneSuspension(
        spring_rate_f=_u16(row, SUSP_OFF["spring_rate_f"], False) or None,
        spring_rate_r=_u16(row, SUSP_OFF["spring_rate_r"], False) or None,
        ride_height_f=_u16(row, SUSP_OFF["ride_height_f"], False) if len(row) > 14 else None,
        ride_height_r=_u16(row, SUSP_OFF["ride_height_r"], False) if len(row) > 16 else None,
        damper_f=row[SUSP_OFF["damper_f"]] if len(row) > 46 else None,
        damper_r=row[SUSP_OFF["damper_r"]] if len(row) > 46 else None,
    )

def write_suspension_finetune_to_row(row: bytes, ft: FineTuneSuspension) -> bytes:
    buf = bytearray(row)
    if ft.spring_rate_f is not None:
        _pack_u16(buf, SUSP_OFF["spring_rate_f"], ft.spring_rate_f)
    if ft.spring_rate_r is not None:
        _pack_u16(buf, SUSP_OFF["spring_rate_r"], ft.spring_rate_r)
    if ft.ride_height_f is not None and len(buf) > 14:
        _pack_u16(buf, SUSP_OFF["ride_height_f"], ft.ride_height_f)
    if ft.ride_height_r is not None and len(buf) > 16:
        _pack_u16(buf, SUSP_OFF["ride_height_r"], ft.ride_height_r)
    if ft.damper_f is not None and len(buf) > 46:
        buf[SUSP_OFF["damper_f"]] = ft.damper_f & 0xFF
    if ft.damper_r is not None and len(buf) > 46:
        buf[SUSP_OFF["damper_r"]] = ft.damper_r & 0xFF
    return bytes(buf)

def apply_finetune_gt4(db: "SpecDB", car: CarInfo, ft: FineTuneData) -> List[str]:
    """Apply fine-tune to the part rows the car currently points at. Returns notes."""
    notes: List[str] = []
    if ft.engine and db.engine_table:
        eng = car.parts.get("Engine")
        if eng:
            row = db.engine_table.get_row_by_id(eng[0])
            if row:
                try:
                    idx = db.engine_table.row_ids.index(eng[0])
                    new_row = write_engine_finetune_to_row(row, ft.engine)
                    db.engine_table.set_row_by_index(idx, new_row)
                    notes.append("engine curve tuned")
                except ValueError:
                    notes.append("engine tune skipped (id not found)")
            else:
                notes.append("engine tune skipped (no row)")
        else:
            notes.append("engine tune skipped (no Engine part)")
    if ft.chassis:
        notes.extend(_apply_part_table_finetune(db, car, "Chassis", ft.chassis, read_chassis_finetune_from_row, write_chassis_finetune_to_row, "chassis"))
    if ft.suspension:
        notes.extend(_apply_part_table_finetune(db, car, "Suspension", ft.suspension, read_suspension_finetune_from_row, write_suspension_finetune_to_row, "suspension"))
    if ft.drivetrain:
        dt_key = car.parts.get("DriveTrain")
        gear_key = car.parts.get("Gear")
        dt_row = gear_row = None
        dt_table = gear_table = None
        if dt_key:
            dt_table = _get_part_table(db, "DriveTrain")
            if dt_table:
                dt_row = dt_table.get_row_by_id(dt_key[0])
        if gear_key:
            gear_table = _get_part_table(db, "Gear")
            if gear_table:
                gear_row = gear_table.get_row_by_id(gear_key[0])
        new_dt, new_gear = write_drivetrain_finetune_rows(dt_row, gear_row, ft.drivetrain)
        if new_dt is not None and dt_table is not None and dt_key and new_dt != dt_row:
            try:
                idx = dt_table.row_ids.index(dt_key[0])
                dt_table.set_row_by_index(idx, new_dt)
                notes.append("drivetrain tuned")
            except ValueError:
                notes.append("drivetrain tune skipped")
        if new_gear is not None and gear_table is not None and gear_key and new_gear != gear_row:
            try:
                idx = gear_table.row_ids.index(gear_key[0])
                gear_table.set_row_by_index(idx, new_gear)
                notes.append("gear ratios tuned")
            except ValueError:
                notes.append("gear tune skipped")
    if ft.info and db.generic_car is not None:
        try:
            idx = db.generic_car.row_ids.index(car.row_id)
            row = db.generic_car.get_row_by_index(idx)
            buf = bytearray(row)
            # GENERIC_CAR: DefaultParts key(8) + Price i32(4) + Year i16(2)
            if ft.info.price is not None and len(buf) >= 12:
                struct.pack_into("<i", buf, 8, int(ft.info.price))
            if ft.info.year is not None and len(buf) >= 14:
                struct.pack_into("<h", buf, 12, int(ft.info.year))
            db.generic_car.set_row_by_index(idx, bytes(buf))
            car.price = ft.info.price if ft.info.price is not None else car.price
            car.year = ft.info.year if ft.info.year is not None else car.year
            notes.append("car info tuned")
        except Exception as e:
            notes.append(f"car info tune skipped ({e})")
    return notes

def _apply_part_table_finetune(db, car, part_name, ft_obj, reader, writer, label):
    notes = []
    key = car.parts.get(part_name)
    if not key:
        notes.append(f"{label} tune skipped (no {part_name} part)")
        return notes
    table_path = db.folder / f"{part_name.upper()}.dbt"
    # Chassis/Suspension may already be loaded; load on demand into a cache on SpecDB
    cache_attr = f"_{part_name.lower()}_table"
    table = getattr(db, cache_attr, None)
    if table is None:
        if not table_path.is_file():
            notes.append(f"{label} tune skipped (no {table_path.name})")
            return notes
        try:
            table = DbtTable(table_path)
            setattr(db, cache_attr, table)
        except Exception as e:
            notes.append(f"{label} tune skipped ({e})")
            return notes
    row = table.get_row_by_id(key[0])
    if not row:
        notes.append(f"{label} tune skipped (no row)")
        return notes
    try:
        idx = table.row_ids.index(key[0])
        new_row = writer(row, ft_obj)
        table.set_row_by_index(idx, new_row)
        notes.append(f"{label} tuned")
    except ValueError:
        notes.append(f"{label} tune skipped (id not found)")
    return notes

def _get_part_table(db: "SpecDB", part_name: str) -> Optional[DbtTable]:
    cache_attr = f"_{part_name.lower()}_table"
    table = getattr(db, cache_attr, None)
    if table is not None:
        return table
    p = db.folder / f"{part_name.upper()}.dbt"
    if p.is_file():
        try:
            table = DbtTable(p)
            setattr(db, cache_attr, table)
            return table
        except Exception:
            return None
    return None

def read_drivetrain_finetune_from_rows(dt_row: Optional[bytes], gear_row: Optional[bytes]) -> FineTuneDrivetrain:
    out = FineTuneDrivetrain()
    if dt_row and len(dt_row) > 16:
        out.drive = int(dt_row[16])
    if gear_row and len(gear_row) >= 16:
        # first gear ratios as u16/1000
        for i in range(8):
            off = 2 * i
            if off + 2 > len(gear_row):
                break
            raw = _u16(gear_row, off, False)
            if raw == 0:
                setattr(out, f"ratio_{i+1}", None)
            else:
                setattr(out, f"ratio_{i+1}", raw / 1000.0)
        # gear count: count non-zero ratios
        count = sum(1 for i in range(8) if getattr(out, f"ratio_{i+1}") is not None)
        out.gears = count or None
    return out

def write_drivetrain_finetune_rows(dt_row: Optional[bytes], gear_row: Optional[bytes], ft: FineTuneDrivetrain):
    new_dt, new_gear = dt_row, gear_row
    if dt_row is not None and ft.drive is not None and len(dt_row) > 16:
        buf = bytearray(dt_row)
        buf[16] = int(ft.drive) & 0xFF
        new_dt = bytes(buf)
    if gear_row is not None:
        buf = bytearray(gear_row)
        for i in range(8):
            val = getattr(ft, f"ratio_{i+1}")
            if val is not None and 2 * i + 2 <= len(buf):
                raw = 0 if val <= 0 else int(round(val * 1000)) & 0xFFFF
                _pack_u16(buf, 2 * i, raw)
        new_gear = bytes(buf)
    return new_dt, new_gear

def read_finetune_for_car(db: "SpecDB", car: CarInfo) -> FineTuneData:
    data = FineTuneData()
    eng = car.parts.get("Engine")
    if eng and db.engine_table:
        row = db.engine_table.get_row_by_id(eng[0])
        if row:
            data.engine = read_engine_finetune_from_row(row)
    for part_name, attr, reader in [
        ("Chassis", "chassis", read_chassis_finetune_from_row),
        ("Suspension", "suspension", read_suspension_finetune_from_row),
    ]:
        key = car.parts.get(part_name)
        if not key:
            continue
        table = _get_part_table(db, part_name)
        if not table:
            continue
        row = table.get_row_by_id(key[0])
        if row:
            setattr(data, attr, reader(row))
    # Drivetrain + Gear
    dt_key = car.parts.get("DriveTrain")
    gear_key = car.parts.get("Gear")
    dt_row = gear_row = None
    if dt_key:
        t = _get_part_table(db, "DriveTrain")
        if t:
            dt_row = t.get_row_by_id(dt_key[0])
    if gear_key:
        t = _get_part_table(db, "Gear")
        if t:
            gear_row = t.get_row_by_id(gear_key[0])
    if dt_row or gear_row:
        data.drivetrain = read_drivetrain_finetune_from_rows(dt_row, gear_row)
    data.info = FineTuneInfo(price=car.price, year=car.year)
    return data


def _next_free_id(row_ids: List[int]) -> int:
    used = set(row_ids)
    candidate = (max(row_ids) + 1) if row_ids else 1
    while candidate in used:
        candidate += 1
    return candidate

def clone_car_gt4(
    db: "SpecDB",
    template: CarInfo,
    *,
    price: Optional[int] = None,
    year: Optional[int] = None,
    label: Optional[str] = None,
) -> CarInfo:
    """Create a new car by cloning template GENERIC_CAR + DEFAULT_PARTS rows.

    The new car shares the same part keys as the template (link-style).
    A new DEFAULT_PARTS row is allocated so later part swaps / fine-tune
    do not alter the template's DEFAULT_PARTS bundle.
    """
    if db.generic_car is None or db.default_parts is None:
        raise RuntimeError("SpecDB not fully loaded")
    # Locate template indices
    try:
        gc_idx = db.generic_car.row_ids.index(template.row_id)
    except ValueError as e:
        raise ValueError(f"template GENERIC_CAR id {template.row_id} not found") from e
    gc_row = bytearray(db.generic_car.get_row_by_index(gc_idx))
    # DefaultParts key at offset 0 (8 bytes)
    dp_id = template.parts.get("Brake")  # any part proves DP exists; better read from row
    # Parse DefaultParts key from GENERIC_CAR row
    from struct import unpack_from, pack_into
    # little-endian key: i32 id + i32 table
    if len(gc_row) < 8:
        raise ValueError("GENERIC_CAR row too short")
    old_dp_id = unpack_from("<i", gc_row, 0)[0]
    old_dp_table = unpack_from("<i", gc_row, 4)[0]
    dp_row = db.default_parts.get_row_by_id(old_dp_id)
    if not dp_row:
        raise ValueError(f"template DEFAULT_PARTS id {old_dp_id} not found")
    new_dp_id = _next_free_id(db.default_parts.row_ids)
    new_gc_id = _next_free_id(db.generic_car.row_ids)
    # Append DEFAULT_PARTS clone
    db.default_parts.append_row(new_dp_id, bytes(dp_row))
    # Patch GENERIC_CAR: new DefaultParts key, price, year
    pack_into("<i", gc_row, 0, new_dp_id)
    # keep table id
    if price is not None and len(gc_row) >= 12:
        pack_into("<i", gc_row, 8, int(price))
    if year is not None and len(gc_row) >= 14:
        pack_into("<h", gc_row, 12, int(year))
    db.generic_car.append_row(new_gc_id, bytes(gc_row))
    # Build CarInfo
    new_label = label or f"{template.label}_clone"
    if db.generic_car_idi is not None:
        db.generic_car_idi.labels[new_gc_id] = new_label
    parts = dict(template.parts)
    new_car = CarInfo(
        row_id=new_gc_id,
        label=new_label,
        name=(label or f"{template.name} (new)"),
        year=int(year if year is not None else template.year),
        price=int(price if price is not None else template.price),
        default_parts_id=new_dp_id,
        default_parts_table=old_dp_table,
        parts=parts,
        maker_id=template.maker_id,
        brand=getattr(template, "brand", "") or "",
    )
    db.cars.append(new_car)
    db.by_id[new_gc_id] = new_car
    return new_car

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
        maker_id = int(parsed.get("Maker") or 0)
        try:
            from ui.makers import maker_name as _maker_name
            brand = _maker_name(maker_id)
        except Exception:
            brand = str(maker_id) if maker_id else ""
        car = CarInfo(
            row_id=rid,
            label=label,
            name=display,
            year=int(parsed.get("Year") or 0),
            price=int(parsed.get("Price") or 0),
            default_parts_id=parts_id,
            default_parts_table=parts_table,
            parts=parts,
            maker_id=maker_id,
            brand=brand if brand != "—" else "",
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
    dp.set_row_by_index(idx, bytes(row))

    target.parts[part_name] = new_key



def _save_dirty_part_tables(db: SpecDB, backup: bool = True) -> List[Path]:
    """Write any part tables that have dirty rows (ENGINE / CHASSIS / SUSPENSION)."""
    written: List[Path] = []
    tables = []
    if db.engine_table is not None:
        tables.append(db.engine_table)
    if db.generic_car is not None:
        tables.append(db.generic_car)
    for attr in ("_chassis_table", "_suspension_table", "_drivetrain_table", "_gear_table"):
        t = getattr(db, attr, None)
        if t is not None:
            tables.append(t)
    for t in tables:
        if not t.dirty_rows:
            continue
        out = t.path
        if backup and out.is_file():
            bak = out.with_suffix(out.suffix + ".bak")
            if not bak.is_file():
                bak.write_bytes(out.read_bytes())
        data = t.to_uncompressed_bytes()
        out.write_bytes(data)
        written.append(out)
    return written

def save_default_parts(
    db: SpecDB,
    dest: Optional[Path] = None,
    backup: bool = True,
) -> Path:
    """Write DEFAULT_PARTS.dbt (uncompressed) with all hybrid edits applied.

    Parameters
    ----------
    db :
        Loaded SpecDB (must have dirty rows from apply_part_swap).
    dest :
        Output path. Defaults to the original DEFAULT_PARTS.dbt path.
    backup :
        If True and dest already exists, copy it to ``*.bak`` first
        (only when no backup is present yet).

    Returns
    -------
    Path
        The path written.
    """
    if db.default_parts is None:
        raise RuntimeError("SpecDB not loaded")
    dp = db.default_parts
    out = Path(dest) if dest is not None else dp.path
    out = out.resolve()

    if backup and out.is_file():
        bak = out.with_suffix(out.suffix + ".bak")
        if not bak.is_file():
            bak.write_bytes(out.read_bytes())

    data = dp.to_uncompressed_bytes()
    out.write_bytes(data)
    _save_dirty_part_tables(db, backup=backup)
    return out


def write_hybrids_summary(
    db: SpecDB,
    plans: List[dict],
    dest: Path,
) -> None:
    """Write a plain-text summary of applied hybrids next to the SpecDB."""
    lines = [
        "GT Hybrid Creator — GT4 hybrids",
        f"SpecDB: {db.folder}",
        f"DEFAULT_PARTS rows dirty: {len(db.default_parts.dirty_rows) if db.default_parts else 0}",
        "",
    ]
    for i, p in enumerate(plans, 1):
        lines.append(f"{i}. {p.get('target_name', '?')} (id {p.get('target_id')})")
        lines.append(f"   mode: {p.get('mode', 'link')}")
        lines.append(f"   {p.get('summary', '')}")
        lines.append("")
    dest.write_text("\n".join(lines), encoding="utf-8")


def backup_default_parts(db: SpecDB) -> Path:
    """Copy the original DEFAULT_PARTS.dbt to DEFAULT_PARTS.dbt.bak."""
    if db.default_parts is None:
        raise RuntimeError("SpecDB not loaded")
    src = db.default_parts.path
    if not src.is_file():
        raise FileNotFoundError(src)
    bak = src.with_suffix(src.suffix + ".bak")
    bak.write_bytes(src.read_bytes())
    return bak


def export_hybrids_zip(
    db: SpecDB,
    plans: List[dict],
    zip_path: Path,
) -> Path:
    """Export modified DEFAULT_PARTS.dbt + hybrids.txt into a ZIP (folder unchanged)."""
    if db.default_parts is None:
        raise RuntimeError("SpecDB not loaded")
    data = db.default_parts.to_uncompressed_bytes()
    summary_lines = [
        "GT Hybrid Creator — GT4 hybrids (ZIP export)",
        f"SpecDB: {db.folder}",
        f"DEFAULT_PARTS rows dirty: {len(db.default_parts.dirty_rows)}",
        "",
    ]
    for i, p in enumerate(plans, 1):
        summary_lines.append(f"{i}. {p.get('target_name', '?')} (id {p.get('target_id')})")
        summary_lines.append(f"   mode: {p.get('mode', 'link')}")
        summary_lines.append(f"   {p.get('summary', '')}")
        summary_lines.append("")
    summary = "\n".join(summary_lines)
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("DEFAULT_PARTS.dbt", data)
        zf.writestr("hybrids.txt", summary.encode("utf-8"))
        for attr in ("engine_table", "generic_car", "_chassis_table", "_suspension_table", "_drivetrain_table", "_gear_table"):
            t = getattr(db, attr, None)
            if t is not None and t.dirty_rows:
                zf.writestr(t.path.name, t.to_uncompressed_bytes())
    return zip_path
