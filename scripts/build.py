"""Build a portable Talk2 directory with PyInstaller.

Run this on the operating system you want to ship: Windows produces
dist/Talk2/Talk2.exe, Linux produces dist/Talk2/Talk2.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HIDDEN_IMPORTS = [
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.null",
    "keyring.backends.fail",
    "feedparser",
    "feedparser_sgmllib",
]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "未安装 PyInstaller。请先执行：pip install -r requirements-build.txt",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "Talk2",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
        "--paths",
        str(ROOT),
        "--collect-submodules",
        "talk2",
        "--collect-all",
        "jieba",
        "--collect-submodules",
        "feedparser",
    ]
    for name in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", name])
    command.append(str(ROOT / "talk2" / "__main__.py"))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
