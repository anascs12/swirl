# PyInstaller build: pyinstaller packaging/swirl.spec
# Produces dist/swirl/ (a folder app; starts faster than a single-file exe).
import sys

block_cipher = None
excluded_qt = ["QtWebEngineCore", "QtWebEngineWidgets", "QtQml", "QtQuick", "Qt3DCore",
               "QtMultimedia", "QtCharts", "QtDataVisualization", "QtPdf", "QtSql", "QtTest"]

a = Analysis(
    ["launcher.py"],
    pathex=[".."],
    datas=[("../swirl/assets", "swirl/assets")],
    hiddenimports=["swirl.wheel", "swirl.bubble", "swirl.integrate", "pypdfium2_raw"],
    excludes=["tkinter", "numpy", *[f"PySide6.{m}" for m in excluded_qt]],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="swirl",
    console=False,          # no terminal window when started from the file manager
    icon="windows/swirl.ico" if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="swirl", strip=False, upx=False)
