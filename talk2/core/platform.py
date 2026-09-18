from __future__ import annotations

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
