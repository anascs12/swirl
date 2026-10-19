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
    hiddenimports=["swirl.wheel", "swirl.bubble", "swirl.integrate", "swirl.studio", "swirl.editor", "swirl.pdftools", "swirl.pdfedit", "pypdfium2_raw"],
    excludes=["tkinter", "numpy", *[f"PySide6.{m}" for m in excluded_qt]],
    noarchive=False,
)
# Drop Qt modules Swirl never loads (QML, Quick, WebEngine, virtual keyboard…): ~60 MB smaller.
_UNUSED = ("Qt6Qml", "Qt6Quick", "Qt6VirtualKeyboard", "Qt6WebEngine", "Qt6Pdf", "Qt63D", "Qt6Multimedia",
           "Qt6Charts", "Qt6DataVisualization", "Qt6ShaderTools", "Qt6Designer", "qml", "QtQuick", "virtualkeyboard",
           "Qt6Sql", "Qt6Test", "Qt6OpenGLWidgets", "libqgtk3", "libgtk-3", "libgdk-3")
a.binaries = [b for b in a.binaries if not any(u in b[0] for u in _UNUSED)]
a.datas = [d for d in a.datas if not any(u in d[0].replace("\\", "/") for u in ("qml", "Qt/translations", "Qt6Quick"))]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="swirl",
    console=False,          # no terminal window when started from the file manager
    icon="windows/swirl.ico" if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="swirl", strip=False, upx=False)
