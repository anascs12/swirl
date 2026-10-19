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


def run(args: list[str], timeout: int = 900) -> None:
    """Run an external program; raise ToolError with its last output on failure."""
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise ToolError(f"{Path(args[0]).name} failed: {' '.join(tail) or 'unknown error'}")


def available_summary() -> dict[str, bool]:
    """Which optional engines are installed (shown by `swirl --check`)."""
    return {name: bool(find(name)) for name in ("ffmpeg", "soffice", "pandoc")}
