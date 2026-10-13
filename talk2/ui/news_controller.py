from __future__ import annotations

from PySide6.QtCore import QObject, QThread

from talk2.core.news_fetcher import DEFAULT_FEEDS
from talk2.core.scheduler import NewsScheduler
from talk2.core.storage import Storage
from talk2.ui.news_popup import NewsPopup
from talk2.ui.news_worker import NewsWorker


class NewsController(QObject):
    def __init__(self, storage: Storage, window, tray=None) -> None:
        super().__init__(window)
        self.storage = storage
        self.window = window
        self.tray = tray
        self._thread: QThread | None = None
        self._worker: NewsWorker | None = None
        self._popup: NewsPopup | None = None
        self._scheduled = False
        self._scheduler = NewsScheduler(storage)
        self._scheduler.due.connect(lambda: self.fetch(scheduled=True))
        window.news_requested.connect(lambda: self.fetch(scheduled=False))

    def fetch(self, scheduled: bool = False) -> None:
        if self._thread and self._thread.isRunning():
            self.window.set_news_status("新闻正在获取")
            return
        self._scheduled = scheduled
        feeds = self.storage.get_setting("news_feeds", "") or DEFAULT_FEEDS
        self._thread = QThread(self)
        self._worker = NewsWorker(self.storage, self.window.llm_config(), feeds)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self.window.set_news_status)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _on_finished(self, digest: object) -> None:
        if not isinstance(digest, dict):
            return
        activate = not self.window.is_busy()
        self._popup = NewsPopup(digest, on_open=self.window.show_and_raise)
        self._popup.present(activate=activate)
        note = str(digest.get("note") or "")
        if note and note != "未摘要":
            self.window.set_news_status(note)
        else:
            self.window.set_news_status("新闻简报已打开")
        if self.tray is not None and self._scheduled:
            self.tray.notify("今日新闻简报")

    def _cleanup(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
