"""知识库索引与目录监听。

窗口只调用 arm()/start()，不关心线程与防抖细节。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, Signal

from talk2.core.llm_client import LLMConfig
from talk2.core.rag import watch_directories
from talk2.core.storage import Storage
from talk2.ui.index_worker import IndexWorker


class LibrarySync(QObject):
    """维护 RAG 索引：目录监听、防抖、后台重建。"""

    status = Signal(str)

    def __init__(self, storage: Storage, config_provider, parent=None) -> None:
        super().__init__(parent)
        self._storage = storage
        self._config_provider = config_provider
        self._thread: QThread | None = None
        self._worker: IndexWorker | None = None
        self._pending_force: bool | None = None

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_changed)
        self._watcher.fileChanged.connect(self._on_changed)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(lambda: self.start(False))

    # ---------- 对外 ----------

    def arm(self) -> None:
        """按当前设置重新挂载监听路径。"""
        current = self._watcher.directories() + self._watcher.files()
        if current:
            self._watcher.removePaths(current)
        if self._storage.get_setting("rag_enabled", "0") != "1":
            return
        root = self._storage.get_setting("rag_path", "").strip()
        if not root or not Path(root).is_dir():
            return
        paths = watch_directories(Path(root))
        if paths:
            self._watcher.addPaths(paths)

    def start(self, force: bool) -> None:
        """建立/刷新索引；正在跑时记录待执行请求。"""
        root = self._storage.get_setting("rag_path", "").strip()
        if not root or not Path(root).is_dir():
            return
        if self._thread is not None and self._thread.isRunning():
            pending = self._pending_force
            self._pending_force = force if pending is None else pending or force
            return

        self._thread = QThread(self)
        self._worker = IndexWorker(self._storage, root, self._config_provider(), force)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self.status)
        self._worker.finished.connect(self.status)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()
        self.status.emit("正在建立索引…")

    def dispose(self) -> None:
        """窗口关闭时调用：丢弃待执行请求并等待线程退出。"""
        self._pending_force = None
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1500)

    # ---------- 内部 ----------

    def _on_changed(self, _path: str) -> None:
        if self._storage.get_setting("rag_enabled", "0") == "1":
            self._timer.start()

    def _on_failed(self, text: str) -> None:
        self.status.emit(f"索引失败：{text}")

    def _cleanup(self) -> None:
        pending = self._pending_force
        self._pending_force = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        if pending is not None:
            QTimer.singleShot(0, lambda: self.start(pending))
