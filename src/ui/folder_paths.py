from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

_BASE = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
PATHS_FILE = _BASE / "folder_paths.json"
_MAX_RECENT = 5


def _read() -> dict:
    try:
        data = json.loads(PATHS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    tmp = PATHS_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, PATHS_FILE)
    except OSError:
        pass


def get_folder(key: str) -> Optional[Path]:
    val = _read().get(key)
    return Path(val) if isinstance(val, str) and val else None


def set_folder(key: str, folder: Path) -> None:
    data = _read()
    data[key] = str(folder)
    # Keep a short recent list per key
    recent_key = f"{key}_recent"
    recent: List[str] = list(data.get(recent_key) or [])
    s = str(folder)
    if s in recent:
        recent.remove(s)
    recent.insert(0, s)
    data[recent_key] = recent[:_MAX_RECENT]
    _write(data)


def get_recent(key: str) -> List[Path]:
    recent = _read().get(f"{key}_recent") or []
    out: List[Path] = []
    for s in recent:
        if isinstance(s, str) and s:
            p = Path(s)
            if p.is_dir():
                out.append(p)
    return out


def get_last_game() -> Optional[str]:
    val = _read().get("last_game")
    return val if isinstance(val, str) else None


def set_last_game(game: str) -> None:
    data = _read()
    data["last_game"] = game
    _write(data)
