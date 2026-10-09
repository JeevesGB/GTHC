from __future__ import annotations
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
TABLE_NAMES = [
    "BRAKE", "BRAKECONTROLLER", "STEER", "CHASSIS", "LIGHTWEIGHT", "RACINGMODIFY",
    "ENGINE", "PORTPOLISH", "ENGINEBALANCE", "DISPLACEMENT", "COMPUTER", "NATUNE",
    "TURBINEKIT", "DRIVETRAIN", "FLYWHEEL", "CLUTCH", "PROPELLERSHAFT", "GEAR",
    "SUSPENSION", "INTERCOOLER", "MUFFLER", "LSD", "TCSC", "ASCC", "WHEEL",
    "TIRESIZE", "TIREFORCEVOL", "TIRECOMPOUND", "FRONTTIRE", "REARTIRE", "CAR",
    "ENEMY_CARS", "EVENT", "REGULATIONS", "COURSE", "ARCADE_CAR",
]
T: Dict[str, int] = {n: i for i, n in enumerate(TABLE_NAMES)}
GTAR_MAGIC = 0x52415447  # 'GTAR'
GTDT_MAGIC = 0x54445447  # 'GTDT'
STDB_MAGIC = 0x42445453  # 'STDB'
IDDB_MAGIC = 0x42444449  # 'IDDB'
MASK64 = (1 << 64) - 1
CAR_OFF = {"price": 0xEC, "year": 0xEA, "type": 0xF1, "flags": 0xF0}
DRIVE_NAMES = ["FR", "FF", "4WD", "MR", "RR"]
CAR_TYPES = ["Road", "Race", "Rally"]

@dataclass
class PartDef:
    key: str
    group: str
    label: str
    car_off: int
    cat: int
    hint: str = ""
    tid: int = 0

PART_DEFS: List[PartDef] = [
    PartDef("ENGINE", "engine", "Engine", 0x38, 0, "Power and torque curve, rev limit, engine sound"),
    PartDef("TURBINEKIT", "engine", "Turbo / supercharger", 0x68, 1, "Stock forced induction"),
    PartDef("INTERCOOLER", "engine", "Intercooler", 0xA8, 1),
    PartDef("MUFFLER", "engine", "Exhaust", 0xB0, 1),
    PartDef("FLYWHEEL", "engine", "Flywheel", 0x78, 1),
    PartDef("PORTPOLISH", "engine", "Port polish", 0x40, 1),
    PartDef("ENGINEBALANCE", "engine", "Engine balancing", 0x48, 1),
    PartDef("DISPLACEMENT", "engine", "Displacement", 0x50, 1),
    PartDef("COMPUTER", "engine", "Computer", 0x58, 1),
    PartDef("NATUNE", "engine", "N/A tuning", 0x60, 1),
    PartDef("DRIVETRAIN", "drivetrain", "Drivetrain layout", 0x70, 1, "FR / FF / MR / RR / 4WD, rotating inertia"),
    PartDef("GEAR", "drivetrain", "Transmission", 0x98, 1, "Gear ratios, final drive, top speed"),
    PartDef("CLUTCH", "drivetrain", "Clutch", 0x80, 1),
    PartDef("LSD", "drivetrain", "Limited-slip diff", 0x90, 1),
    PartDef("PROPELLERSHAFT", "drivetrain", "Propeller shaft", 0x88, 1),
    PartDef("CHASSIS", "chassis", "Chassis", 0x20, 0, "Weight, dimensions, wheelbase, downforce balance"),
    PartDef("SUSPENSION", "chassis", "Suspension", 0xA0, 1),
    PartDef("BRAKE", "chassis", "Brakes", 0x08, 1),
    PartDef("BRAKECONTROLLER", "chassis", "Brake controller / ABS", 0x10, 1),
    PartDef("STEER", "chassis", "Steering", 0x18, 1),
    PartDef("LIGHTWEIGHT", "chassis", "Weight reduction", 0x28, 1),
    PartDef("ASCC", "chassis", "Stability control (ASC)", 0xC8, 1),
    PartDef("TCSC", "chassis", "Traction control (TCS)", 0xD0, 1),
    PartDef("FRONTTIRE", "tyres", "Front tyres", 0xB8, 4),
    PartDef("REARTIRE", "tyres", "Rear tyres", 0xC0, 4),
]
for d in PART_DEFS:
    d.tid = T[d.key]

@dataclass
class InfoDef:
    key: str
    label: str
    ranges: List[Tuple[int, int]]  # (offset, length)
    hint: str = ""

INFO_DEFS: List[InfoDef] = [
    InfoDef("PRICE", "Price", [(0xEC, 4)]),
    InfoDef("YEAR", "Model year", [(0xEA, 2)]),
    InfoDef("TYPE", "Class (road / race / rally)", [(0xF1, 1)]),
    InfoDef("FLAGS", "Buy / sell restrictions", [(0xF0, 1)]),
    InfoDef(
        "NAME",
        "Name and maker shown in game",
        [(0xE0, 8), (0xF2, 4), (0x100, 6)],
        "Reuses the donor's existing name text — it cannot invent new text",
    ),
]

GROUPS = [
    {"key": "engine", "label": "Engine & power"},
    {"key": "drivetrain", "label": "Drivetrain & gearing"},
    {"key": "chassis", "label": "Chassis, suspension & brakes"},
    {"key": "tyres", "label": "Tyres"},
    {"key": "info", "label": "Car info"},
]


def hash_label(s: str) -> int:
    total = 0
    for ch in s:
        total = (total + (ord(ch) & 255)) & 0xFFFF
    h = total
    for ch in s:
        h = ((h << 7) | (h >> 57)) & MASK64
        h = (h + (ord(ch) & 255)) & MASK64
    return h

def hex64(h: int) -> str:
    return f"{h & MASK64:016x}"

def unhex64(s: str) -> int:
    return int(s, 16) & MASK64

def u8(data: bytearray | memoryview, off: int) -> int:
    return data[off]

def u16(data: bytearray | memoryview, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]

def u32(data: bytearray | memoryview, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]

def u64(data: bytearray | memoryview, off: int) -> int:
    return struct.unpack_from("<Q", data, off)[0]

def set_u64(data: bytearray, off: int, val: int) -> None:
    struct.pack_into("<Q", data, off, val & MASK64)


@dataclass
class Block:
    version: int
    tid: int
    n: int
    es: int
    data: bytearray
    _idx: Optional[Dict[int, int]] = field(default=None, repr=False)

    def ensure_idx(self) -> None:
        if self._idx is None:
            self._idx = {}
            for i in range(self.n):
                self._idx[u64(self.data, i * self.es)] = i

@dataclass
class Archive:
    align_mask: int
    last_is_absolute: bool
    blocks: List[Block]

def read_gtar(raw: bytes) -> Archive:
    if len(raw) < 32:
        raise ValueError("File is too small to be a paramdb.")
    if u32(raw, 0) != GTAR_MAGIC:
        raise ValueError("Not a paramdb: missing GTAR header.")
    n = u32(raw, 4)
    index_size = u32(raw, 8)
    align_mask = u32(raw, 12)
    if n == 0 or n > 4096:
        raise ValueError(f"GTAR header claims {n} tables, which is not plausible.")
    if 16 + (n + 1) * 4 > len(raw):
        raise ValueError("GTAR index runs past the end of the file.")
    idx = [u32(raw, 16 + 4 * i) for i in range(n + 1)]
    last_is_absolute = idx[n] != len(raw) - index_size and idx[n] == len(raw)
    blocks: List[Block] = []
    for i in range(n):
        o = index_size + idx[i]
        if o + 16 > len(raw):
            raise ValueError(f"Table {i} starts past the end of the file.")
        if u32(raw, o) != GTDT_MAGIC:
            raise ValueError(f"Table {i} has no GTDT header.")
        size = u32(raw, o + 12)
        version = u16(raw, o + 4)
        tid = struct.unpack_from("<h", raw, o + 6)[0]
        count = u16(raw, o + 8)
        es = u16(raw, o + 10)
        if size < 16 or o + size > len(raw):
            raise ValueError(f"Table {i} has an impossible size.")
        data = bytearray(raw[o + 16 : o + size])
        if len(data) < count * es:
            raise ValueError(f"Table {i} is shorter than its header says.")
        blocks.append(Block(version=version, tid=tid, n=count, es=es, data=data))
    return Archive(align_mask=align_mask, last_is_absolute=last_is_absolute, blocks=blocks)

def write_gtar(arc: Archive) -> bytes:
    align = arc.align_mask + 1

    def pad(x: int) -> int:
        return ((x + align - 1) // align) * align if align > 1 else x

    n = len(arc.blocks)
    index_size = pad(16 + (n + 1) * 4)
    total = index_size
    offs: List[int] = []
    for b in arc.blocks:
        offs.append(total - index_size)
        total = pad(total + 16 + b.n * b.es)
    out = bytearray(total)
    struct.pack_into("<IIII", out, 0, GTAR_MAGIC, n, index_size, arc.align_mask)
    for i in range(n):
        struct.pack_into("<I", out, 16 + 4 * i, offs[i])
    struct.pack_into("<I", out, 16 + 4 * n, total if arc.last_is_absolute else total - index_size)
    for i, b in enumerate(arc.blocks):
        o = index_size + offs[i]
        length = b.n * b.es
        struct.pack_into("<IHhHHI", out, o, GTDT_MAGIC, b.version, b.tid, b.n, b.es, 16 + length)
        out[o + 16 : o + 16 + length] = b.data[:length]
    return bytes(out)

@dataclass
class Db:
    arc: Archive
    by_tid: Dict[int, Block]
    car: Block

def open_db(raw: bytes) -> Db:
    arc = read_gtar(raw)
    by_tid = {b.tid: b for b in arc.blocks}
    car = by_tid.get(T["CAR"])
    eng = by_tid.get(T["ENGINE"])
    cha = by_tid.get(T["CHASSIS"])
    drv = by_tid.get(T["DRIVETRAIN"])
    if (
        not car
        or car.es != 0x108
        or not eng
        or eng.es != 0x58
        or not cha
        or cha.es != 0x20
        or not drv
        or drv.es != 0x28
    ):
        raise ValueError(
            "This does not look like a Gran Turismo 3 paramdb "
            "(the CAR/ENGINE/CHASSIS tables are not the expected size). "
            "GT Concept files are not supported."
        )
    return Db(arc=arc, by_tid=by_tid, car=car)

def clone_db(db: Db) -> Db:
    blocks = [
        Block(version=b.version, tid=b.tid, n=b.n, es=b.es, data=bytearray(b.data))
        for b in db.arc.blocks
    ]
    arc = Archive(
        align_mask=db.arc.align_mask,
        last_is_absolute=db.arc.last_is_absolute,
        blocks=blocks,
    )
    by_tid = {b.tid: b for b in blocks}
    return Db(arc=arc, by_tid=by_tid, car=by_tid[T["CAR"]])

def find_row(block: Block, hash_val: int) -> int:
    block.ensure_idx()
    assert block._idx is not None
    return block._idx.get(hash_val, -1)

def car_count(db: Db) -> int:
    return db.car.n

def car_hash(db: Db, i: int) -> int:
    return u64(db.car.data, i * db.car.es)

def find_car(db: Db, hash_val: int) -> int:
    return find_row(db.car, hash_val)

def pointer(db: Db, ci: int, defn: PartDef) -> int:
    return u64(db.car.data, ci * db.car.es + defn.car_off)

def part_row(db: Db, defn: PartDef, ptr: int) -> Optional[Tuple[Block, int]]:
    if not ptr:
        return None
    b = db.by_tid.get(defn.tid)
    if not b:
        return None
    r = find_row(b, ptr)
    return (b, r) if r >= 0 else None

@dataclass
class CarStats:
    price: int = 0
    year: int = 0
    type: int = 0
    flags: int = 0
    ps: Optional[int] = None
    torque: Optional[float] = None
    rev_limit: Optional[int] = None
    mass: Optional[int] = None
    wheelbase: Optional[int] = None
    drive: Optional[int] = None
    gears: Optional[int] = None
    pw: Optional[float] = None

def car_stats(db: Db, ci: int) -> CarStats:
    out = CarStats(
        price=u32(db.car.data, ci * db.car.es + CAR_OFF["price"]),
        year=u16(db.car.data, ci * db.car.es + CAR_OFF["year"]),
        type=u8(db.car.data, ci * db.car.es + CAR_OFF["type"]),
        flags=u8(db.car.data, ci * db.car.es + CAR_OFF["flags"]),
    )
    def get(key: str):
        d = next(x for x in PART_DEFS if x.key == key)
        return part_row(db, d, pointer(db, ci, d))

    e = get("ENGINE")
    if e:
        b, r = e
        ps = u16(b.data, r * b.es + 0x3A)
        tq = u16(b.data, r * b.es + 0x3E)
        rev = u8(b.data, r * b.es + 0x45)
        out.ps = ps or None
        out.torque = (tq / 100.0) if tq else None
        out.rev_limit = (rev * 100) if rev else None
    c = get("CHASSIS")
    if c:
        b, r = c
        out.mass = u16(b.data, r * b.es + 0x1A) or None
        out.wheelbase = u16(b.data, r * b.es + 0x18) or None
    d = get("DRIVETRAIN")
    if d:
        b, r = d
        out.drive = u8(b.data, r * b.es + 0x14)
    g = get("GEAR")
    if g:
        b, r = g
        out.gears = u8(b.data, r * b.es + 0x11) or None
    if out.ps and out.mass:
        out.pw = out.mass / out.ps
    return out

@dataclass
class ReportEntry:
    key: str
    label: str
    how: str  # copied | linked | same | skipped
    note: str = ""

@dataclass
class ApplyResult:
    ok: bool
    reason: str = ""
    report: List[ReportEntry] = field(default_factory=list)

_TORQUE_UNUSED = 0xFF9D

@dataclass
class EngineCurve:
    rpm: List[int]          # RPM points
    torque: List[float]     # kgf·m
    power: List[float]      # PS (metric)
    peak_ps: Optional[int] = None
    peak_torque: Optional[float] = None  # kgf·m
    rev_limit: Optional[int] = None
    idle_rpm: Optional[int] = None

def engine_curve(db: Db, car_index: int) -> Optional[EngineCurve]:
    defn = next((d for d in PART_DEFS if d.key == "ENGINE"), None)
    if not defn:
        return None
    ptr = pointer(db, car_index, defn)
    row = part_row(db, defn, ptr)
    if not row:
        return None
    block, r = row
    base = r * block.es
    # torqueA..P at +0x1A (16 x ushort), values are kgf·m * 100; 0xFF9D = unused
    # rpmA..P at +0x47 (16 x byte), values are RPM / 100
    # psvalue +0x3A, torquevalue +0x3E, idlerpm +0x44, revlimit +0x45
    rpms: List[int] = []
    tqs: List[float] = []
    for i in range(16):
        t_raw = u16(block.data, base + 0x1A + 2 * i)
        r_raw = u8(block.data, base + 0x47 + i)
        if t_raw == _TORQUE_UNUSED or r_raw == 0:
            continue
        rpm = r_raw * 100
        tq = t_raw / 100.0
        rpms.append(rpm)
        tqs.append(tq)
    if not rpms:
        return None
    # PS = (kgf·m * rpm) / 716.2
    powers = [(tq * rpm) / 716.2 for tq, rpm in zip(tqs, rpms)]
    ps_val = u16(block.data, base + 0x3A) or None
    tq_val = u16(block.data, base + 0x3E)
    peak_tq = (tq_val / 100.0) if tq_val else (max(tqs) if tqs else None)
    idle = u8(block.data, base + 0x44)
    rev = u8(block.data, base + 0x45)
    return EngineCurve(
        rpm=rpms,
        torque=tqs,
        power=powers,
        peak_ps=ps_val,
        peak_torque=peak_tq,
        rev_limit=(rev * 100) if rev else None,
        idle_rpm=(idle * 10) if idle else None,  # stored as rpm/10? car dump showed 80 for idle -> 800
    )


def set_u8(data: bytearray, off: int, val: int) -> None:
    data[off] = val & 0xFF

def set_u16(data: bytearray, off: int, val: int) -> None:
    struct.pack_into("<H", data, off, val & 0xFFFF)

@dataclass
class FineTuneEngine:
    rpm: List[int] = field(default_factory=list)          # up to 16 RPM points
    torque: List[float] = field(default_factory=list)     # kgf·m matching rpm
    peak_ps: Optional[int] = None
    peak_torque: Optional[float] = None                   # kgf·m
    rev_limit: Optional[int] = None                       # rpm
    idle_rpm: Optional[int] = None                        # rpm

@dataclass
class FineTuneChassis:
    mass: Optional[int] = None          # kg
    wheelbase: Optional[int] = None     # mm

@dataclass
class FineTuneSuspension:

    category: Optional[int] = None       # 0=stock .. 3=full custom
    spring_f: Optional[int] = None       # +0x1F
    spring_r: Optional[int] = None       # +0x24 (rear cluster start)
    ride_height_f: Optional[int] = None  # +0x13
    ride_height_r: Optional[int] = None  # +0x16
    stabilizer_f: Optional[int] = None   # +0x17 (128 = neutral)
    stabilizer_r: Optional[int] = None   # +0x18
    damper_f: Optional[int] = None       # +0x21
    damper_r: Optional[int] = None       # +0x25
    camber_f: Optional[int] = None       # +0x27
    camber_r: Optional[int] = None       # +0x28

@dataclass
class FineTuneDrivetrain:
    drive: Optional[int] = None          # 0=FR 1=FF 2=4WD 3=MR 4=RR
    gears: Optional[int] = None          # number of forward gears
    # Gear ratios as floats (e.g. 3.28); stored as u16 * 1000, 0xFC19 = unused
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
    car_type: Optional[int] = None   # 0=Road 1=Race 2=Rally
    flags: Optional[int] = None

@dataclass
class FineTuneData:
    engine: Optional[FineTuneEngine] = None
    chassis: Optional[FineTuneChassis] = None
    suspension: Optional[FineTuneSuspension] = None
    drivetrain: Optional[FineTuneDrivetrain] = None
    info: Optional[FineTuneInfo] = None

def read_engine_finetune(db: Db, car_index: int) -> Optional[FineTuneEngine]:
    curve = engine_curve(db, car_index)
    if not curve:
        return None
    return FineTuneEngine(
        rpm=list(curve.rpm),
        torque=list(curve.torque),
        peak_ps=curve.peak_ps,
        peak_torque=curve.peak_torque,
        rev_limit=curve.rev_limit,
        idle_rpm=curve.idle_rpm,
    )

def read_chassis_finetune(db: Db, car_index: int) -> Optional[FineTuneChassis]:
    defn = next((d for d in PART_DEFS if d.key == "CHASSIS"), None)
    if not defn:
        return None
    ptr = pointer(db, car_index, defn)
    row = part_row(db, defn, ptr)
    if not row:
        return None
    block, r = row
    base = r * block.es
    return FineTuneChassis(
        mass=u16(block.data, base + 0x1A) or None,
        wheelbase=u16(block.data, base + 0x18) or None,
    )

def write_engine_finetune(db: Db, car_index: int, ft: FineTuneEngine) -> bool:
    defn = next((d for d in PART_DEFS if d.key == "ENGINE"), None)
    if not defn:
        return False
    ptr = pointer(db, car_index, defn)
    row = part_row(db, defn, ptr)
    if not row:
        return False
    block, r = row
    base = r * block.es
    data = block.data  # bytearray

    # Clear all 16 torque/rpm slots first
    for i in range(16):
        set_u16(data, base + 0x1A + 2 * i, _TORQUE_UNUSED)
        set_u8(data, base + 0x47 + i, 0)

    n = min(16, len(ft.rpm), len(ft.torque))
    for i in range(n):
        rpm = int(ft.rpm[i])
        tq = float(ft.torque[i])
        if rpm <= 0 or tq <= 0:
            continue
        set_u16(data, base + 0x1A + 2 * i, int(round(tq * 100)))
        set_u8(data, base + 0x47 + i, max(1, min(255, int(round(rpm / 100)))))

    if ft.peak_ps is not None:
        set_u16(data, base + 0x3A, int(ft.peak_ps) & 0xFFFF)
    if ft.peak_torque is not None:
        set_u16(data, base + 0x3E, int(round(ft.peak_torque * 100)) & 0xFFFF)
    if ft.idle_rpm is not None:
        # stored as rpm/10 in existing data (80 -> 800)
        set_u8(data, base + 0x44, max(0, min(255, int(round(ft.idle_rpm / 10)))))
    if ft.rev_limit is not None:
        set_u8(data, base + 0x45, max(0, min(255, int(round(ft.rev_limit / 100)))))
    return True

def write_chassis_finetune(db: Db, car_index: int, ft: FineTuneChassis) -> bool:
    defn = next((d for d in PART_DEFS if d.key == "CHASSIS"), None)
    if not defn:
        return False
    ptr = pointer(db, car_index, defn)
    row = part_row(db, defn, ptr)
    if not row:
        return False
    block, r = row
    base = r * block.es
    data = block.data
    if ft.wheelbase is not None:
        set_u16(data, base + 0x18, int(ft.wheelbase) & 0xFFFF)
    if ft.mass is not None:
        set_u16(data, base + 0x1A, int(ft.mass) & 0xFFFF)
    return True

# SUSPENSION absolute offsets within part row
_SUSP = {
    "category": 0x10,
    "ride_height_f": 0x13,
    "ride_height_r": 0x16,
    "stabilizer_f": 0x17,
    "stabilizer_r": 0x18,
    "spring_f": 0x1F,
    "damper_f": 0x21,
    "spring_r": 0x24,
    "damper_r": 0x25,
    "camber_f": 0x27,
    "camber_r": 0x28,
}

def read_suspension_finetune(db: Db, car_index: int) -> Optional[FineTuneSuspension]:
    defn = next((d for d in PART_DEFS if d.key == "SUSPENSION"), None)
    if not defn:
        return None
    ptr = pointer(db, car_index, defn)
    row = part_row(db, defn, ptr)
    if not row:
        return None
    block, r = row
    base = r * block.es
    data = block.data
    if base + 0x29 > len(data):
        return None
    def g(name: str) -> int:
        return int(data[base + _SUSP[name]])
    return FineTuneSuspension(
        category=g("category"),
        spring_f=g("spring_f"),
        spring_r=g("spring_r"),
        ride_height_f=g("ride_height_f"),
        ride_height_r=g("ride_height_r"),
        stabilizer_f=g("stabilizer_f"),
        stabilizer_r=g("stabilizer_r"),
        damper_f=g("damper_f"),
        damper_r=g("damper_r"),
        camber_f=g("camber_f"),
        camber_r=g("camber_r"),
    )

def write_suspension_finetune(db: Db, car_index: int, ft: FineTuneSuspension) -> bool:
    defn = next((d for d in PART_DEFS if d.key == "SUSPENSION"), None)
    if not defn:
        return False
    ptr = pointer(db, car_index, defn)
    row = part_row(db, defn, ptr)
    if not row:
        return False
    block, r = row
    base = r * block.es
    data = block.data
    if base + 0x29 > len(data):
        return False
    def s(name: str, val: Optional[int]) -> None:
        if val is not None:
            data[base + _SUSP[name]] = int(val) & 0xFF
            # mirror duplicated spring_f pair
            if name == "spring_f":
                data[base + 0x20] = int(val) & 0xFF
    s("category", ft.category)
    s("spring_f", ft.spring_f)
    s("spring_r", ft.spring_r)
    s("ride_height_f", ft.ride_height_f)
    s("ride_height_r", ft.ride_height_r)
    s("stabilizer_f", ft.stabilizer_f)
    s("stabilizer_r", ft.stabilizer_r)
    s("damper_f", ft.damper_f)
    s("damper_r", ft.damper_r)
    s("camber_f", ft.camber_f)
    s("camber_r", ft.camber_r)
    return True


_GEAR_UNUSED = 0xFC19

def read_drivetrain_finetune(db: Db, car_index: int) -> Optional[FineTuneDrivetrain]:
    out = FineTuneDrivetrain()
    ddef = next((d for d in PART_DEFS if d.key == "DRIVETRAIN"), None)
    if ddef:
        ptr = pointer(db, car_index, ddef)
        row = part_row(db, ddef, ptr)
        if row:
            block, r = row
            base = r * block.es
            if base + 0x15 <= len(block.data):
                out.drive = int(block.data[base + 0x14])
    gdef = next((d for d in PART_DEFS if d.key == "GEAR"), None)
    if gdef:
        ptr = pointer(db, car_index, gdef)
        row = part_row(db, gdef, ptr)
        if row:
            block, r = row
            base = r * block.es
            data = block.data
            if base + 0x22 <= len(data):
                out.gears = int(data[base + 0x11]) or None
                for i in range(8):
                    raw = u16(data, base + 0x12 + 2 * i)
                    val = None if raw == _GEAR_UNUSED or raw == 0 else raw / 1000.0
                    setattr(out, f"ratio_{i+1}", val)
    return out

def write_drivetrain_finetune(db: Db, car_index: int, ft: FineTuneDrivetrain) -> List[str]:
    notes = []
    if ft.drive is not None:
        ddef = next((d for d in PART_DEFS if d.key == "DRIVETRAIN"), None)
        if ddef:
            ptr = pointer(db, car_index, ddef)
            row = part_row(db, ddef, ptr)
            if row:
                block, r = row
                block.data[r * block.es + 0x14] = int(ft.drive) & 0xFF
                notes.append("drivetrain layout")
    gdef = next((d for d in PART_DEFS if d.key == "GEAR"), None)
    if gdef and (ft.gears is not None or any(getattr(ft, f"ratio_{i}") is not None for i in range(1, 9))):
        ptr = pointer(db, car_index, gdef)
        row = part_row(db, gdef, ptr)
        if row:
            block, r = row
            base = r * block.es
            data = block.data
            if ft.gears is not None:
                data[base + 0x11] = int(ft.gears) & 0xFF
            for i in range(8):
                val = getattr(ft, f"ratio_{i+1}")
                if val is not None:
                    if val <= 0:
                        set_u16(data, base + 0x12 + 2 * i, _GEAR_UNUSED)
                    else:
                        set_u16(data, base + 0x12 + 2 * i, int(round(val * 1000)) & 0xFFFF)
            notes.append("gear ratios")
    return notes

def read_info_finetune(db: Db, car_index: int) -> Optional[FineTuneInfo]:
    base = car_index * db.car.es
    return FineTuneInfo(
        price=u32(db.car.data, base + CAR_OFF["price"]),
        year=u16(db.car.data, base + CAR_OFF["year"]),
        car_type=u8(db.car.data, base + CAR_OFF["type"]),
        flags=u8(db.car.data, base + CAR_OFF["flags"]),
    )

def write_info_finetune(db: Db, car_index: int, ft: FineTuneInfo) -> bool:
    base = car_index * db.car.es
    data = db.car.data
    if ft.price is not None:
        struct.pack_into("<I", data, base + CAR_OFF["price"], int(ft.price) & 0xFFFFFFFF)
    if ft.year is not None:
        set_u16(data, base + CAR_OFF["year"], int(ft.year) & 0xFFFF)
    if ft.car_type is not None:
        data[base + CAR_OFF["type"]] = int(ft.car_type) & 0xFF
    if ft.flags is not None:
        data[base + CAR_OFF["flags"]] = int(ft.flags) & 0xFF
    return True

def apply_finetune(db: Db, car_index: int, ft: FineTuneData) -> List[str]:
    notes: List[str] = []
    if ft.engine:
        if write_engine_finetune(db, car_index, ft.engine):
            notes.append("engine curve tuned")
        else:
            notes.append("engine tune skipped (no ENGINE row)")
    if ft.chassis:
        if write_chassis_finetune(db, car_index, ft.chassis):
            notes.append("chassis tuned")
        else:
            notes.append("chassis tune skipped (no CHASSIS row)")
    if ft.suspension:
        if write_suspension_finetune(db, car_index, ft.suspension):
            notes.append("suspension tuned")
        else:
            notes.append("suspension tune skipped (no SUSPENSION row)")
    if ft.drivetrain:
        sub = write_drivetrain_finetune(db, car_index, ft.drivetrain)
        if sub:
            notes.append("drivetrain tuned (" + ", ".join(sub) + ")")
        else:
            notes.append("drivetrain tune skipped")
    if ft.info:
        if write_info_finetune(db, car_index, ft.info):
            notes.append("car info tuned")
        else:
            notes.append("car info tune skipped")
    return notes


def clone_car_gt3(
    db: Db,
    template_index: int,
    *,
    price: Optional[int] = None,
    year: Optional[int] = None,
    car_type: Optional[int] = None,
    flags: Optional[int] = None,
) -> int:
    if template_index < 0 or template_index >= db.car.n:
        raise IndexError(f"template index {template_index} out of range")
    es = db.car.es
    src = bytes(db.car.data[template_index * es : (template_index + 1) * es])
    new_row = bytearray(src)
    # New unique-ish hash: XOR high bits with (n+1) so index lookup stays unique
    old_hash = u64(new_row, 0)
    new_hash = (old_hash ^ ((db.car.n + 1) << 32) ^ 0xC4A15EED) & 0xFFFFFFFFFFFFFFFF
    if new_hash == 0:
        new_hash = 0x1
    struct.pack_into("<Q", new_row, 0, new_hash)
    if price is not None:
        struct.pack_into("<I", new_row, CAR_OFF["price"], int(price) & 0xFFFFFFFF)
    if year is not None:
        set_u16(new_row, CAR_OFF["year"], int(year) & 0xFFFF)
    if car_type is not None:
        new_row[CAR_OFF["type"]] = int(car_type) & 0xFF
    if flags is not None:
        new_row[CAR_OFF["flags"]] = int(flags) & 0xFF
    # Extend block
    db.car.data.extend(new_row)
    db.car.n += 1
    db.car._idx = None  # invalidate hash index
    return db.car.n - 1

def apply_plan(db: Db, plan: Dict[str, Any]) -> ApplyResult:
    report: List[ReportEntry] = []
    ti = find_car(db, unhex64(plan["target"]))
    if ti < 0:
        return ApplyResult(ok=False, reason="target car is not in this paramdb", report=report)
    target_hash = unhex64(plan["target"])

    def donor_index(hx: str) -> int:
        return find_car(db, unhex64(hx))

    for defn in PART_DEFS:
        dhex = (plan.get("picks") or {}).get(defn.key)
        if not dhex:
            continue
        di = donor_index(dhex)
        if di < 0:
            report.append(ReportEntry(defn.key, defn.label, "skipped", "donor car is not in this paramdb"))
            continue
        if di == ti:
            continue
        tp = pointer(db, ti, defn)
        dp = pointer(db, di, defn)
        if tp == dp:
            report.append(ReportEntry(defn.key, defn.label, "same"))
            continue
        t_row = part_row(db, defn, tp)
        d_row = part_row(db, defn, dp)
        owned = (
            t_row is not None
            and d_row is not None
            and u64(t_row[0].data, t_row[1] * t_row[0].es + 8) == target_hash
        )
        if plan.get("mode") != "link" and owned:
            from_off = 0x10 + defn.cat
            es = t_row[0].es
            src = d_row[0].data
            dst = t_row[0].data
            sr = d_row[1]
            tr = t_row[1]
            dst[tr * es + from_off : tr * es + es] = src[sr * es + from_off : sr * es + es]
            report.append(ReportEntry(defn.key, defn.label, "copied"))
        else:
            set_u64(db.car.data, ti * db.car.es + defn.car_off, dp)
            note = ""
            if plan.get("mode") != "link":
                if not t_row:
                    note = "the target has no stock part to overwrite"
                elif not d_row:
                    note = "the donor has no stock part"
                else:
                    note = "the target's part row is shared with other cars"
            report.append(ReportEntry(defn.key, defn.label, "linked", note))

    for defn in INFO_DEFS:
        dhex = (plan.get("info") or {}).get(defn.key)
        if not dhex:
            continue
        di = donor_index(dhex)
        if di < 0:
            report.append(ReportEntry(defn.key, defn.label, "skipped", "donor car is not in this paramdb"))
            continue
        if di == ti:
            continue
        for off, length in defn.ranges:
            src_start = di * db.car.es + off
            dst_start = ti * db.car.es + off
            db.car.data[dst_start : dst_start + length] = db.car.data[src_start : src_start + length]
        report.append(ReportEntry(defn.key, defn.label, "copied"))

    # Fine-tune numeric overrides (applied after part swaps so they hit the final rows)
    ft = plan.get("finetune")
    if ft and isinstance(ft, FineTuneData):
        for note in apply_finetune(db, ti, ft):
            report.append(ReportEntry("finetune", "Fine-tune", "tuned", note))
    elif ft and isinstance(ft, dict):
        # allow plain-dict plans (e.g. after serialisation)
        data = FineTuneData()
        eng = ft.get("engine")
        if eng:
            data.engine = FineTuneEngine(
                rpm=list(eng.get("rpm") or []),
                torque=list(eng.get("torque") or []),
                peak_ps=eng.get("peak_ps"),
                peak_torque=eng.get("peak_torque"),
                rev_limit=eng.get("rev_limit"),
                idle_rpm=eng.get("idle_rpm"),
            )
        ch = ft.get("chassis")
        if ch:
            data.chassis = FineTuneChassis(
                mass=ch.get("mass"),
                wheelbase=ch.get("wheelbase"),
            )
        su = ft.get("suspension")
        if su:
            data.suspension = FineTuneSuspension(
                category=su.get("category"),
                spring_f=su.get("spring_f"),
                spring_r=su.get("spring_r"),
                ride_height_f=su.get("ride_height_f"),
                ride_height_r=su.get("ride_height_r"),
                stabilizer_f=su.get("stabilizer_f"),
                stabilizer_r=su.get("stabilizer_r"),
                damper_f=su.get("damper_f"),
                damper_r=su.get("damper_r"),
                camber_f=su.get("camber_f"),
                camber_r=su.get("camber_r"),
            )
        dt = ft.get("drivetrain")
        if dt:
            data.drivetrain = FineTuneDrivetrain(
                drive=dt.get("drive"),
                gears=dt.get("gears"),
                **{f"ratio_{i}": dt.get(f"ratio_{i}") for i in range(1, 9)},
            )
        inf = ft.get("info")
        if inf:
            data.info = FineTuneInfo(
                price=inf.get("price"),
                year=inf.get("year"),
                car_type=inf.get("car_type"),
                flags=inf.get("flags"),
            )
        for note in apply_finetune(db, ti, data):
            report.append(ReportEntry("finetune", "Fine-tune", "tuned", note))

    return ApplyResult(ok=True, report=report)

def preview_plan(db: Db, plan: Dict[str, Any]) -> Tuple[Db, int, List[ReportEntry], Optional[CarStats]]:
    copy = clone_db(db)
    res = apply_plan(copy, plan)
    ti = find_car(copy, unhex64(plan["target"]))
    stats = car_stats(copy, ti) if ti >= 0 else None
    return copy, ti, res.report, stats

@dataclass
class StringTable:
    bpc: int  
    strings: List[str]

def parse_stdb(raw: bytes) -> StringTable:
    if len(raw) < 16:
        raise ValueError("String file is too small.")
    if u32(raw, 0) != STDB_MAGIC:
        raise ValueError("Not an STDB string file.")
    count = u32(raw, 4)
    bpc = struct.unpack_from("<h", raw, 8)[0]
    strings: List[str] = []
    for i in range(count):
        pos = u32(raw, 16 + 4 * i)
        if pos + 2 > len(raw):
            strings.append("")
            continue
        length = u16(raw, pos)
        data = raw[pos + 2 : min(len(raw), pos + 2 + length)]
        if bpc == 2:
            s = data.decode("utf-16-le", errors="replace")
        elif bpc == -1:
            try:
                s = data.decode("euc-jp", errors="replace")
            except LookupError:
                s = data.decode("latin-1", errors="replace")
        else:
            s = "".join(chr(b) for b in data)
        strings.append(s.rstrip("\0"))
    return StringTable(bpc=bpc, strings=strings)

def parse_id_index(raw: bytes) -> Dict[int, int]:
    if len(raw) < 8 or u32(raw, 0) != IDDB_MAGIC:
        raise ValueError("Not an ID index file.")
    count = u32(raw, 4)
    mapping: Dict[int, int] = {}
    for i in range(count):
        base = 8 + 16 * i
        if base + 16 > len(raw):
            break
        h = u64(raw, base)
        # signed 64-bit index in the string table
        si = struct.unpack_from("<q", raw, base + 8)[0]
        mapping[h] = si
    return mapping

import re

# Matches both plain names (paramdb_us.db) and leading-dot id tables (.id_db_idx_eu.db).
# Does NOT match carcolor.db / carcolor.sdb / racedetail.db etc.
_FILE_RE = re.compile(
    r"(?:^|\.)(paramdb|paramunistr|paramstr|id_db_idx|id_db_str)(?:_([A-Za-z0-9]+))?\.db$",
    re.IGNORECASE,
)

def classify_file(name: str, raw: bytes) -> Optional[Dict[str, str]]:
    m = _FILE_RE.search(name)
    if not m:
        return None
    magic = u32(raw, 0) if len(raw) >= 4 else 0
    key = m.group(1).lower()
    kind: Optional[str] = None
    if key == "paramdb" and magic == GTAR_MAGIC:
        kind = "paramdb"
    elif key == "id_db_idx" and magic == IDDB_MAGIC:
        kind = "idx"
    elif key in ("paramstr", "paramunistr", "id_db_str") and magic == STDB_MAGIC:
        if key == "paramunistr":
            kind = "unistr"
        elif key == "id_db_str":
            kind = "idstr"
        else:
            kind = "str"
    if not kind:
        return None
    suffix = m.group(2).lower() if m.group(2) else ""
    return {"kind": kind, "suffix": suffix}

@dataclass
class CarName:
    name: str
    code: str
    maker: str = ""

def car_names(
    db: Db,
    ci: int,
    uni: Optional[StringTable] = None,
    str_tbl: Optional[StringTable] = None,
    id_map: Optional[Dict[int, int]] = None,
    id_str: Optional[StringTable] = None,
) -> CarName:
    def us(off: int) -> str:
        if not uni:
            return ""
        idx = u16(db.car.data, ci * db.car.es + off)
        if 0 <= idx < len(uni.strings):
            return uni.strings[idx]
        return ""

    first = us(0xE4) or us(0x100) or us(0xF2)
    second = us(0xE6) or us(0x102) or us(0xF4)
    maker = us(0x104)
    name = (first + " " + second).strip()
    if name and maker and maker.lower() not in name.lower():
        name = maker + " " + name
    code = ""
    if str_tbl:
        idx = u16(db.car.data, ci * db.car.es + 0xE8)
        if 0 <= idx < len(str_tbl.strings):
            code = str_tbl.strings[idx]
    if not code and id_map and id_str:
        si = id_map.get(car_hash(db, ci))
        if si is not None and 0 <= si < len(id_str.strings):
            code = id_str.strings[si]
    return CarName(name=name, code=code, maker=maker or "")

def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF

def make_zip(files: List[Tuple[str, bytes]]) -> bytes:
    parts: List[bytes] = []
    central: List[bytes] = []
    offset = 0
    for name, data in files:
        name_b = name.encode("utf-8")
        crc = _crc32(data)
        # local header
        lh = struct.pack(
            "<IHHHHIIIIHH",
            0x04034B50,  # sig
            20,  # version needed
            0,  # flags
            0,  # compression = store
            0,  # mod time
            0,  # mod date
            crc,
            len(data),
            len(data),
            len(name_b),
            0,  # extra len
        ) + name_b
        parts.append(lh)
        parts.append(data)
        # central directory header
        ch = struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,  # version made by
            20,  # version needed
            0,  # flags
            0,  # method
            0,  # time
            0,  # date
            crc,
            len(data),
            len(data),
            len(name_b),
            0,  # extra
            0,  # comment
            0,  # disk
            0,  # int attr
            0,  # ext attr
            offset,
        ) + name_b
        central.append(ch)
        offset += len(lh) + len(data)
    cd_size = sum(len(c) for c in central)
    end = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,  # disk
        0,  # disk with cd
        len(files),
        len(files),
        cd_size,
        offset,
        0,  # comment len
    )
    return b"".join(parts) + b"".join(central) + end
