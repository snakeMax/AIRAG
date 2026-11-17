"""Build the Windows app, installer and portable zip.

    python tools/build.py                 # everything (needs Inno Setup 6 for the installer)
    python tools/build.py --no-installer  # only the PyInstaller app + portable zip

Output in dist/:
    AIRAG/                                  the app folder
    AIRAG-Setup-<version>.exe (+ .sha256)   installer
    AIRAG-<version>-portable-win64.zip      portable version (keeps data next to the exe)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT))


def version() -> str:
    from airag import __version__
    return __version__


def write_version_file(v: str) -> None:
    nums = [int(x) for x in (v.split("-")[0].split(".") + ["0", "0", "0"])[:4]]
    t = tuple(nums)
    BUILD.mkdir(exist_ok=True)
    (BUILD / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'snakeMax'),
      StringStruct('FileDescription', 'AIRAG - AI Research Article Generation'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'AIRAG'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'AIRAG.exe'),
      StringStruct('ProductName', 'AIRAG'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")


def run(cmd: list) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def sha256(path: Path) -> None:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{h}  {path.name}\n", encoding="utf-8")


def find_iscc() -> str | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            for sub in ("Inno Setup 6", os.path.join("Programs", "Inno Setup 6")):
                p = Path(base) / sub / "ISCC.exe"
                if p.exists():
                    return str(p)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-installer", action="store_true")
    args = ap.parse_args()
    v = version()
    print(f"Building AIRAG {v}")
    write_version_file(v)
    shutil.rmtree(DIST / "AIRAG", ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", "packaging/airag.spec", "--noconfirm", "--clean",
         "--distpath", DIST, "--workpath", BUILD / "pyinstaller"])

    # portable zip: same app plus a marker file that keeps data in <app>/data
    zpath = DIST / f"AIRAG-{v}-portable-win64.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in (DIST / "AIRAG").rglob("*"):
            if f.is_file():
                z.write(f, Path("AIRAG") / f.relative_to(DIST / "AIRAG"))
        z.writestr("AIRAG/portable.txt", "Keep this file to store settings and history in the 'data' folder next to AIRAG.exe.\n")
    sha256(zpath)
    print("portable:", zpath)

    if not args.no_installer:
        iscc = find_iscc()
        if not iscc:
            sys.exit("Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php or use --no-installer.")
        run([iscc, f"/DAppVersion={v}", "packaging/installer.iss"])
        setup = DIST / f"AIRAG-Setup-{v}.exe"
        sha256(setup)
        print("installer:", setup)


if __name__ == "__main__":
    main()
