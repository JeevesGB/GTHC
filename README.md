# GT Hybrid Creator (GTHC)

Desktop tool for building **hybrid cars** in **Gran Turismo 3** and **Gran Turismo 4**.

Pick a target car, pull engine / drivetrain / chassis / tyre (and other) parts from donors, preview power curves on a dyno graph, then write the result back to the game database.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt](https://img.shields.io/badge/UI-PyQt6-41CD52.svg)](https://www.riverbankcomputing.com/software/pyqt/)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
[![GitHub release](https://img.shields.io/github/v/release/JeevesGB/GTHC)](https://github.com/JeevesGB/GTHC/releases)

---

## Features

- **GT3** — multi-region paramdb (JP / EU / US), overwrite or link modes, backups, ZIP export  
- **GT4** — SpecDB load (including Huffman-compressed tables), hybrid part swaps, save to `DEFAULT_PARTS.dbt`, backup & ZIP  
- **Car picker** — search, year filters, sort by name / year / power / **brand**, manufacturer logos  
- **Spec sheet** — Stock / Hybrid / Δ  
- **Dyno graph** — torque & power vs RPM (stock vs hybrid)  
- **Hybrid list** — edit, duplicate, remove; save count on the button  
- Drag-and-drop folder open, recent folders, unsaved-changes warning  
- Launcher with GT3 / GT4 branding; runs **without a console window**

---

## Requirements

- **Windows** (`run.bat` is Windows-oriented; the app is Python + Qt)
- [Python](https://www.python.org/downloads/) **3.10+** (developed on 3.12). Tick **Add python.exe to PATH** in the installer.
- Extracted game database / SpecDB files from **your own** copy of the game (see [Game files](#game-files))

---

## Setup

### 1. Get the project

```bash
git clone https://github.com/JeevesGB/GTHC.git
cd GTHC
```

Or download the ZIP from GitHub and extract it.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Installs **PyQt6** (UI) and **matplotlib** (dyno graph).

Optional virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run

Double-click **`run.bat`**, or:

```bash
pythonw src\launcher.py
```

`run.bat` uses `pythonw` so **no console window** appears. It does not install packages — complete step 2 first.

---

## Game files

The tool edits **extracted** database files, not the disc image or console. Always keep a backup of the originals.

| Game | Folder to select | Must contain |
|------|------------------|--------------|
| **Gran Turismo 3** | Extracted `database` folder | `paramdb*.db`, plus matching `paramstr` / `paramunistr` / `id_db_*` files so names resolve |
| **Gran Turismo 4** | SpecDB folder (e.g. `GT4_PREMIUM_US2560`) | `GENERIC_CAR.dbt`, `DEFAULT_PARTS.dbt` (and related `.idi` files) |

---

## Quick start

1. Launch the app → choose **Gran Turismo 3** or **Gran Turismo 4**.
2. Select (or drag in) your database / SpecDB folder. The path is remembered.
3. **Target** — car to change (keeps body / 3D model).
4. **Donors** — set group donors or use **Part by part**; or **Copy all parts from one car…**.
5. Check the **spec sheet** and **dyno**, then **Add to list**.
6. **Save hybrids…** — write into the folder, or export a **ZIP** that leaves the folder unchanged.

### GT3 notes

- Hybrids apply to **every loaded region** (JP / EU / US). Missing cars in a region are skipped.
- **Overwrite** (recommended): copies donor part data into the car; shop upgrades stay with that car.  
- **Link**: only pointers change; the car shares the donor’s part rows.
- **Backup now…** and first in-folder save create `*.bak` copies.

### GT4 notes

- Save updates **`DEFAULT_PARTS.dbt` only** (link-style part keys). Body/model stay with the target.
- Output is **uncompressed** SpecDB; the game accepts both compressed and uncompressed tables.
- First save creates `DEFAULT_PARTS.dbt.bak`. **Ctrl+S** save, **Ctrl+B** backup.

---

## Layout

| Area | Contents |
|------|----------|
| **Left** | Target car, part groups, **hybrid list** (edit / duplicate / remove / save) |
| **Right** | Spec sheet (Stock / Hybrid / Δ) and dyno graph |

Car picker supports brand filter/sort and logo badges (`src/ui/brands/`).

---

## Build a Windows binary (optional)

With [PyInstaller](https://pyinstaller.org/) available:

```bash
build.bat
```

This packages the launcher, game modules, icons, and brand logos into a distributable folder/exe.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `'python' is not recognized` | Reinstall Python with **Add to PATH**, or use `py -3 src\launcher.py`. |
| `No module named 'PyQt6'` | `pip install -r requirements.txt` (in your venv if you use one). |
| No dyno graph | Install matplotlib via the same requirements file. |
| `No paramdb*.db found` | Select the folder that **directly** contains the `.db` files. |
| SpecDB load failed | Confirm `GENERIC_CAR.dbt` and `DEFAULT_PARTS.dbt` are present. |
| Folder prompt every launch | Saved path missing, or project folder is read-only (`folder_paths.json`). |
| Console window appears | Use `run.bat` / `pythonw`, not plain `python`. |

---

## Disclaimer

This project is for **personal / educational** use with game files you legally own. Always back up databases before saving. Gran Turismo is a trademark of Sony Interactive Entertainment / Polyphony Digital; this tool is unofficial and unaffiliated.

---

## License

[MIT](LICENSE) © 2026 JeevesGB
