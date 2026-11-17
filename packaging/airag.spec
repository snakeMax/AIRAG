# PyInstaller spec for the Windows app (one folder, no console window).
# Built by tools/build.py; run from the repository root.
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "web"), "web"),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "airag", "data"), os.path.join("airag", "data")),
]
for pkg in ("trafilatura", "justext", "courlan", "htmldate", "dateparser", "certifi", "playwright", "webview"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

hiddenimports = (
    collect_submodules("airag")
    + collect_submodules("uvicorn")
    + collect_submodules("ddgs")
    + ["pystray._win32", "webview.platforms.edgechromium", "webview.platforms.winforms", "clr"]
)

a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["fontTools", "PyQt5", "PyQt6", "PySide2", "PySide6", "matplotlib", "numpy", "pandas", "scipy", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AIRAG",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="AIRAG")
