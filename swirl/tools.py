"""Locating the external programs some conversions rely on."""

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

# Hide the console window that would flash up for each subprocess on Windows.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_WINDOWS_HINTS = {
    "soffice": [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ],
    "ffmpeg": [r"C:\ffmpeg\bin\ffmpeg.exe"],
    "pandoc": [r"C:\Program Files\Pandoc\pandoc.exe"],
}


@lru_cache(maxsize=None)
def find(name: str) -> str | None:
    """Path of an external program, or None when it is not installed.

    A copy bundled next to the app (vendor/<name>) wins over the system one, so
    packaged builds can ship their own FFmpeg.
    """
    exe = name + (".exe" if sys.platform == "win32" else "")
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "vendor" / exe
    if bundled.exists():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32":
        for hint in _WINDOWS_HINTS.get(name, []):
            if os.path.exists(hint):
                return hint
    return None


class ToolError(RuntimeError):
    pass


def child_env() -> dict[str, str]:
    """Environment for programs Swirl starts (LibreOffice, FFmpeg, file openers).

    A packaged Swirl (PyInstaller) puts its own bundled libraries first on
    LD_LIBRARY_PATH. Programs it launches must not inherit that, or they load
    Swirl's copies (e.g. libssl) instead of the system's and crash.
    """
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            original = env.pop(var + "_ORIG", None)
            if original:
                env[var] = original
            else:
                env.pop(var, None)
        # Qt plugin paths of the bundle would confuse a system Qt app too.
        env.pop("QT_PLUGIN_PATH", None)
        env.pop("QML2_IMPORT_PATH", None)
    return env


def restore_system_environment() -> None:
    """Make child processes started by Qt itself (e.g. opening a result file)
    use the system libraries. Safe for Swirl: the loader read its own library
    path at startup."""
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        clean = child_env()
        for key in list(os.environ):
            if key not in clean:
                del os.environ[key]
        os.environ.update(clean)


def run(args: list[str], timeout: int = 900) -> None:
    """Run an external program; raise ToolError with its last output on failure."""
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW, env=child_env()
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise ToolError(f"{Path(args[0]).name} failed: {' '.join(tail) or 'unknown error'}")


def available_summary() -> dict[str, bool]:
    """Which optional engines are installed (shown by `swirl --check`)."""
    return {name: bool(find(name)) for name in ("ffmpeg", "soffice", "pandoc", "tesseract")}
