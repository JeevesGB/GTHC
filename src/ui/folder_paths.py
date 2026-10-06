from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional

_BASE = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
PATHS_FILE = _BASE / "folder_paths.json"


def _read() -> dict:
    try:
        data = json.loads(PATHS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_folder(key: str) -> Optional[Path]:
    val = _read().get(key)
    return Path(val) if isinstance(val, str) and val else None


def set_folder(key: str, folder: Path) -> None:
    data = _read()
    data[key] = str(folder)
    tmp = PATHS_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, PATHS_FILE)
    except OSError:
        pass 
