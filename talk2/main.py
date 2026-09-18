from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from talk2.core.platform import apply_app_font, db_path, lock_path
from talk2.core.storage import Storage
from talk2.ui.chat_window import ChatWindow
from talk2.ui.styles import APP_QSS


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Talk2")
    app.setOrganizationName("Talk2")
    apply_app_font(app)
    app.setStyleSheet(APP_QSS)

    lock = QLockFile(str(lock_path()))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        QMessageBox.information(None, "Talk2", "Talk2 已经在运行。")
        return 0

    window = ChatWindow(Storage(db_path()))
    window.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
