"""Add or remove "Convert with Swirl" in the file manager. Per user, no admin rights."""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

LABEL = "Convert with Swirl"
ICON = Path(__file__).parent / "assets" / "swirl-256.png"


def launch_command() -> list[str]:
    """How to start this copy of Swirl."""
    if getattr(sys, "frozen", False):          # PyInstaller build
        return [sys.executable]
    return [sys.executable, "-m", "swirl"]


# ── Linux ─────────────────────────────────────────────────────

def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def _linux_files() -> dict[Path, tuple[str, bool]]:
    cmd = " ".join(shlex.quote(c) for c in launch_command())
    data = _data_home()
    return {
        # Nautilus (Ubuntu's Files): scripts receive the selected files as arguments
        data / "nautilus/scripts" / LABEL: (f'#!/bin/sh\nexec {cmd} "$@"\n', True),
        # Nemo (Linux Mint)
        data / "nemo/actions/swirl.nemo_action": (
            f"[Nemo Action]\nName={LABEL}\nComment=Convert, compress or merge files\n"
            f"Exec={cmd} %F\nIcon-Name={ICON}\nSelection=notnone\nExtensions=any;\n", False),
        # Dolphin (KDE)
        data / "kio/servicemenus/swirl.desktop": (
            "[Desktop Entry]\nType=Service\nMimeType=application/octet-stream;all/allfiles;\n"
            "Actions=swirl;\nX-KDE-Priority=TopLevel\n\n"
            f"[Desktop Action swirl]\nName={LABEL}\nIcon={ICON}\nExec={cmd} %F\n", True),
        # App launcher entry for the drop bubble
        data / "applications/swirl-bubble.desktop": (
            "[Desktop Entry]\nType=Application\nName=Swirl Bubble\n"
            "Comment=Drop files on the bubble to convert them\n"
            f"Exec={cmd} --bubble\nIcon={ICON}\nCategories=Utility;\nTerminal=false\n", False),
    }


def _install_linux() -> list[str]:
    done = []
    for path, (content, executable) in _linux_files().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if executable:
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        done.append(f"added {path}")
    done.append("Right-click files → Scripts → Convert with Swirl (Nautilus), or the top level in Nemo and Dolphin.")
    return done


def _uninstall_linux() -> list[str]:
    done = []
    for path in _linux_files():
        if path.exists():
            path.unlink()
            done.append(f"removed {path}")
    return done or ["nothing to remove"]


# ── Windows ───────────────────────────────────────────────────

_WIN_KEY = r"Software\Classes\*\shell\Swirl"


def _sendto_link() -> Path:
    return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\SendTo" / f"{LABEL}.lnk"


def _install_windows() -> list[str]:
    import winreg
    exe, *rest = launch_command()
    command = subprocess.list2cmdline([exe, *rest]) + ' "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN_KEY) as key:
        winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, LABEL)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, exe)
        # Invoke once per selected file; the running instance gathers them into one wheel.
        winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN_KEY + r"\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

    # "Send to" passes every selected file in one launch.
    link = _sendto_link()
    args = subprocess.list2cmdline(rest)
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
          f"$s.TargetPath='{exe}';$s.Arguments='{args}';$s.IconLocation='{exe}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False,
                   creationflags=0x08000000)
    return ["added right-click entry: Convert with Swirl",
            f"added {link}",
            "On Windows 11, the entry is under 'Show more options' (or Shift+right-click)."]


def _uninstall_windows() -> list[str]:
    import winreg
    done = []
    for sub in (_WIN_KEY + r"\command", _WIN_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            done.append(f"removed HKCU\\{sub}")
        except FileNotFoundError:
            pass
    link = _sendto_link()
    if link.exists():
        link.unlink()
        done.append(f"removed {link}")
    return done or ["nothing to remove"]


def install() -> list[str]:
    return _install_windows() if sys.platform == "win32" else _install_linux()


def uninstall() -> list[str]:
    return _uninstall_windows() if sys.platform == "win32" else _uninstall_linux()
