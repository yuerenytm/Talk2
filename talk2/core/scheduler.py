from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from talk2.core.storage import Storage


def should_fire(enabled: bool, news_time: str, last_date: str, now: datetime) -> bool:
    if not enabled:
        return False
    parts = (news_time or "").split(":")
    if len(parts) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return False
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return False
    if last_date == now.date().isoformat():
        return False
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= scheduled


class NewsScheduler(QObject):
    due = Signal()

    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self.check)
        self._timer.start()
        QTimer.singleShot(2_000, self.check)

    def check(self) -> None:
        now = datetime.now()
        enabled = self.storage.get_setting("news_enabled", "0") == "1"
        if not should_fire(
            enabled,
            self.storage.get_setting("news_time", "08:00"),
            self.storage.get_setting("news_last_date", ""),
            now,
        ):
            return
        self.storage.set_setting("news_last_date", now.date().isoformat())
        self.due.emit()
