from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "Talk2"
APP_AUTHOR = "Talk2"


def data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "talk2.db"


def lock_path() -> Path:
    return data_dir() / "talk2.lock"


def apply_app_font(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase

    if sys.platform == "win32":
        candidates = ["Microsoft YaHei UI", "Segoe UI"]
    else:
        candidates = ["Noto Sans CJK SC", "Noto Sans CJK", "WenQuanYi Micro Hei"]

    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            app.setFont(QFont(name, 10))
            return
    app.setFont(QFont(app.font().family(), 10))


def app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_spec(frozen: bool | None = None) -> tuple[str, list[str], Path]:
    """Executable, arguments, and working directory for autostart."""
    if frozen is None:
        frozen = is_frozen()
    if frozen:
        exe = Path(sys.executable).resolve()
        return str(exe), [], exe.parent
    return str(_pythonw()), ["-m", "talk2"], app_root()


def autostart_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
        return base / "Microsoft/Windows/Start Menu/Programs/Startup/Talk2.lnk"
    return Path.home() / ".config/autostart/talk2.desktop"


def set_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        _set_windows_autostart(enabled)
    else:
        _set_linux_autostart(enabled)


def linux_desktop_text(
    executable: str,
    workdir: Path,
    args: list[str] | None = None,
) -> str:
    if args is None:
        args = ["-m", "talk2"]
    command = " ".join([_desktop_exec(executable), *(_desktop_exec(part) for part in args)])
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Talk2\n"
        f"Exec={command}\n"
        f"Path={workdir.as_posix()}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _desktop_exec(python: str) -> str:
    if any(ch in python for ch in ' "\''):
        return '"' + python.replace('"', '\\"') + '"'
    return python


def _pythonw() -> Path:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
    return exe


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _set_windows_autostart(enabled: bool) -> None:
    link = autostart_path()
    if not enabled:
        link.unlink(missing_ok=True)
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    executable, args, workdir = launch_spec()
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(link))})\n"
        f"$s.TargetPath = {_ps_quote(executable)}\n"
        f"$s.Arguments = {_ps_quote(subprocess.list2cmdline(args))}\n"
        f"$s.WorkingDirectory = {_ps_quote(str(workdir))}\n"
        "$s.WindowStyle = 7\n"
        "$s.Description = 'Talk2'\n"
        "$s.Save()\n"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )


def _set_linux_autostart(enabled: bool) -> None:
    path = autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    executable, args, workdir = launch_spec()
    path.write_text(linux_desktop_text(executable, workdir, args), encoding="utf-8")

