import re
import sys
from pathlib import Path

out_file, app_name = Path(sys.argv[1]), sys.argv[2]
text = (Path(__file__).resolve().parent / "version.py").read_text(encoding="utf-8")
m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
if not m:
    sys.exit("version.py: __version__ not found")
version = m.group(1)

nums = [int(p) for p in re.findall(r"\d+", version)[:4]]
nums += [0] * (4 - len(nums))
tup = tuple(nums)
dotted = ".".join(map(str, tup))

out_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tup}, prodvers={tup},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', '{app_name}'),
      StringStruct('FileVersion', '{dotted}'),
      StringStruct('InternalName', '{app_name}'),
      StringStruct('OriginalFilename', '{app_name}.exe'),
      StringStruct('ProductName', '{app_name}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print(f"Version {version}")