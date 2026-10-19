"""Command line entry point.

    swirl                  open Swirl Studio (all PDF tools)
    swirl --studio [--tool ID] FILE...   open Studio with files loaded
    swirl FILE...          open the wheel at the pointer for these files
    swirl --bubble         run the floating drop bubble
    swirl --install        add "Convert with Swirl" to the file manager
    swirl --uninstall      remove it again
    swirl --check          show which conversion engines are installed
    swirl --run TOOL FILE... [--set key=value]   run a Studio tool without a window
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

from . import __version__


def _restore_env_for_children():
    from .tools import restore_system_environment
    restore_system_environment()


def _prefer_xwayland():
    _restore_env_for_children()
    # Native Wayland does not let apps place a window at the pointer, so run
    # through XWayland when it is available (the user can still override this).
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        if os.environ.get("DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"


BUBBLE_CMD = "::swirl-show-bubble::"  # sent instead of file paths to ask the running Swirl for a bubble


def _start_crash_log() -> Path | None:
    """Record crashes (including native ones inside Qt or PDFium) in
    ~/.cache/swirl/swirl.log (Windows: %LOCALAPPDATA%\\Swirl), so problems on users' machines
    can be diagnosed."""
    import faulthandler
    import platform
    import time
    import traceback
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Swirl" if sys.platform == "win32" \
        else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "swirl"
    try:
        base.mkdir(parents=True, exist_ok=True)
        log = base / "swirl.log"
        if log.exists() and log.stat().st_size > 512_000:
            log.replace(base / "swirl.old.log")
        fh = open(log, "a", buffering=1, encoding="utf-8")
    except OSError:
        return None
    fh.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} swirl {__version__} · {platform.platform()} · "
             f"session={os.environ.get('XDG_SESSION_TYPE', '?')} · args={sys.argv[1:]}\n")
    faulthandler.enable(fh, all_threads=True)

    def excepthook(kind, value, tb):
        fh.write("".join(traceback.format_exception(kind, value, tb)))
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = excepthook
    _start_crash_log.file = fh
    return log


def _exec(app) -> int:
    """Run the event loop, then close windows before Python tears Qt down
    (otherwise Qt can crash on exit)."""
    import gc
    code = app.exec()
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    app.processEvents()
    gc.collect()
    return code


def _natural_key(path: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swirl", description="Convert files from a wheel at your cursor.")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--bubble", action="store_true", help="run the floating drop bubble")
    parser.add_argument("--studio", action="store_true", help="open Swirl Studio, the full PDF toolkit")
    parser.add_argument("--tool", help="open this Studio tool directly, e.g. merge, compress, split")
    parser.add_argument("--install", action="store_true", help="add Swirl to the file manager's right-click menu")
    parser.add_argument("--uninstall", action="store_true", help="remove Swirl from the right-click menu")
    parser.add_argument("--check", action="store_true", help="show which conversion engines are installed")
    parser.add_argument("--run", metavar="TOOL", help="run a PDF tool from the command line (see --list)")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="an option for --run")
    parser.add_argument("--list", action="store_true", help="list the PDF tools and their options")
    parser.add_argument("--version", action="version", version=f"swirl {__version__}")
    args = parser.parse_args(argv)
    _start_crash_log()

    if args.install or args.uninstall:
        from . import integrate
        for line in (integrate.install() if args.install else integrate.uninstall()):
            print(line)
        return 0
    if args.check:
        from .tools import available_summary
        names = {"ffmpeg": "FFmpeg (video, audio)", "soffice": "LibreOffice (Office ↔ PDF, PDF/A)",
                 "pandoc": "Pandoc (Markdown, HTML)", "tesseract": "Tesseract (OCR)"}
        for key, ok in available_summary().items():
            print(f"{'✓' if ok else '✗'} {names[key]}")
        print("✓ Images and PDFs (built in)")
        return 0

    if args.list or args.run:
        return _run_cli(args)

    files = [f.resolve() for f in args.files if f.exists() and f.is_file()]
    if args.tool or (not files and not args.bubble):
        args.studio = True
    if args.studio:
        return _run_studio(files, args.tool)

    _prefer_xwayland()
    import tempfile
    import time
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    server_name = f"swirl-{getpass.getuser()}"

    def hand_over() -> bool:
        sock = QLocalSocket()
        sock.connectToServer(server_name)
        if not sock.waitForConnected(150):
            return False
        lines = [*map(str, files), *([BUBBLE_CMD] if args.bubble else [])]
        sock.write("\n".join(lines).encode("utf-8"))
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True

    # Exactly one Swirl owns the lock and shows the wheel; copies started at the
    # same moment (one per selected file on Windows) send it their files.
    lock = QLockFile(str(Path(tempfile.gettempdir()) / f"{server_name}.lock"))
    lock.setStaleLockTime(0)  # a lock left by a crashed process is detected by its PID
    if not lock.tryLock(0):
        if files or args.bubble:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if hand_over():
                    return 0
                time.sleep(0.05)
        if not lock.tryLock(3000):
            print("Swirl is already running.", file=sys.stderr)
            return 1

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Swirl")
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "swirl-256.png")))
    app.setQuitOnLastWindowClosed(False)

    QLocalServer.removeServer(server_name)  # safe: we hold the lock, so any socket is stale
    server = QLocalServer()
    server.listen(server_name)

    pending: list[Path] = list(files)
    open_wheels: list = []
    gather = QTimer(singleShot=True, interval=250)

    def show_wheel():
        from .wheel import Wheel
        # Launches arrive in random order, so sort by name ("page 2" before "page 10").
        batch = sorted(dict.fromkeys(pending), key=_natural_key)
        pending.clear()
        if not batch:
            return
        wheel = Wheel(batch)
        open_wheels.append(wheel)

        def closed():
            open_wheels.remove(wheel)
            if not args.bubble and not open_wheels and not pending:
                app.quit()
        wheel.finished.connect(closed)
        wheel.show()
        wheel.raise_()
        wheel.activateWindow()

    def on_connection():
        sock = server.nextPendingConnection()

        def read():
            lines = [p for p in bytes(sock.readAll()).decode("utf-8").splitlines() if p.strip()]
            if BUBBLE_CMD in lines:
                show_bubble()
                lines.remove(BUBBLE_CMD)
            pending.extend(Path(p) for p in lines)
            if pending:
                gather.start()  # wait briefly for files from other launches
        sock.readyRead.connect(read)

    server.newConnection.connect(on_connection)
    gather.timeout.connect(show_wheel)

    bubbles: list = []

    def show_bubble():
        # The bubble keeps this Swirl running after wheels close.
        args.bubble = True
        if bubbles:
            bubbles[0].show(); bubbles[0].raise_()
            return
        from .bubble import Bubble
        bubble = Bubble()
        bubble.files_dropped.connect(lambda fs: (pending.extend(fs), gather.start(0)))
        bubble.show()
        bubbles.append(bubble)

    if args.bubble:
        show_bubble()
    if files:
        gather.start()

    return _exec(app)


def _run_cli(args) -> int:
    from . import pdftools
    if args.list:
        for t in pdftools.TOOLS:
            opts = ", ".join(f"{o.key}={o.default}" for o in t.options)
            print(f"{t.id:<11} {t.title:<20} {opts}")
        return 0
    tool = pdftools.TOOL_BY_ID.get(args.run)
    if tool is None or tool.page:
        print(f"Unknown or visual-only tool '{args.run}'. See swirl --list.", file=sys.stderr)
        return 2
    opts = {}
    for item in args.set:
        key, _, value = item.partition("=")
        opt = next((o for o in tool.options if o.key == key), None)
        if opt is None:
            print(f"{tool.id} has no option '{key}'", file=sys.stderr)
            return 2
        opts[key] = (value.lower() in ("1", "true", "yes")) if opt.type == "bool" else \
            int(value) if opt.type == "int" else float(value) if opt.type == "float" else value
    try:
        for out in pdftools.run_tool(tool, [f.resolve() for f in args.files], opts):
            print(out)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _run_studio(files: list[Path], tool_id: str | None) -> int:
    _prefer_xwayland()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from . import pdftools
    from .studio import Studio

    if tool_id and tool_id not in pdftools.TOOL_BY_ID:
        print(f"Unknown tool '{tool_id}'. Tools: {', '.join(pdftools.TOOL_BY_ID)}", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Swirl Studio")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "swirl-256.png")))
    window = Studio(files, tool_id)
    window.show()
    return _exec(app)


if __name__ == "__main__":
    sys.exit(main())
