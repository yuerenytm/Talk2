"""对话流式编排：把 QThread + StreamWorker 的生命周期收在一处。

窗口只负责接信号更新界面，不直接管理线程。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from talk2.core.llm_client import LLMConfig
from talk2.core.storage import Storage
from talk2.ui.stream_worker import StreamWorker


class ChatController(QObject):
    """一次问答的流式执行器：同一时刻只允许一个请求在跑。"""

    chunk = Signal(str)
    citations = Signal(object)
    completed = Signal(str)
    failed = Signal(str)
    status = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        """初始化控制器；同一时刻只持有一个线程与工作器。
        """
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: StreamWorker | None = None

    def is_busy(self) -> bool:
        """是否有请求在跑（有线程即视为忙）。
        """
        return self._thread is not None

    def send(
        self,
        config: LLMConfig,
        messages: list[dict[str, str]],
        storage: Storage,
        rag_query: str = "",
        rag_root: str = "",
    ) -> bool:
        """启动一次流式请求。

        把 StreamWorker moveToThread 到新 QThread，连接五个信号，
        完成后由线程的 finished 触发 _cleanup 回收对象。

        Returns:
            是否成功启动；已有请求在跑时返回 False。
        """
        if self.is_busy():
            return False

        self._thread = QThread(self)
        self._worker = StreamWorker(config, messages, storage, rag_query, rag_root)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self.chunk)
        self._worker.status.connect(self.status)
        self._worker.citations.connect(self.citations)
        self._worker.completed.connect(self.completed)
        self._worker.failed.connect(self.failed)
        self._worker.completed.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self.busy_changed.emit(True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """请求停止（仅置标志位，工作器的循环会在下一个片段前退出）。
        """
        if self._worker is not None:
            self._worker.stop()

    def dispose(self) -> None:
        """窗口关闭时调用：请求停止并等待线程退出。"""
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1500)

    def _cleanup(self) -> None:
        """线程结束后回收 worker 与 thread，并广播 busy=False。
        """
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        self.busy_changed.emit(False)
