"""Refresh the client package folder and its zip from this project.

Run:  .venv\\Scripts\\python.exe build_package.py
Copies app.py, db.py, requirements.txt, templates/ and static/ into
..\\Amazing-Assistant-Online\\ (keeping its run.bat, run.command, README.txt
and bundled python/ folder), then rebuilds ..\\Amazing-Assistant-Online.zip.
"""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT.parent / "Amazing-Assistant-Online"
ZIP = PKG.with_suffix(".zip")


def sync():
    for name in ("app.py", "db.py", "requirements.txt"):
        shutil.copy2(ROOT / name, PKG / name)
    for folder in ("templates", "static"):
        shutil.rmtree(PKG / folder, ignore_errors=True)
        shutil.copytree(ROOT / folder, PKG / folder)
    for leftover in ("data", "__pycache__", ".venv"):
        shutil.rmtree(PKG / leftover, ignore_errors=True)


def build_zip():
    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(PKG.rglob("*")):
            rel = path.relative_to(PKG)
            if "__pycache__" in rel.parts:
                continue
            name = f"{PKG.name}/{rel.as_posix()}"
            if path.is_dir():
                info = zipfile.ZipInfo(name + "/")
                info.external_attr = (0o40755 << 16) | 0x10
            else:
                info = zipfile.ZipInfo.from_file(path, name)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if path.name == "run.command" else 0o644
                info.external_attr = (0o100000 | mode) << 16
            info.create_system = 3
            z.writestr(info, b"" if path.is_dir() else path.read_bytes())
    with zipfile.ZipFile(ZIP) as z:
        bad = z.testzip()
        print(f"{ZIP} — {len(z.namelist())} entries, {ZIP.stat().st_size / 1048576:.1f} MB, {'OK' if bad is None else 'BAD: ' + bad}")


if __name__ == "__main__":
    sync()
    build_zip()
