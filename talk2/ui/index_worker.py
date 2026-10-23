from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from talk2.core.llm_client import LLMClient, LLMConfig
from talk2.core.rag import index_library
from talk2.core.storage import Storage


class IndexWorker(QObject):
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, storage: Storage, root: str, config: LLMConfig, force: bool) -> None:
        super().__init__()
        self._storage = storage
        self._root = root
        self._config = config
        self._force = force

    def run(self) -> None:#运行索引工作器，首先检查是否需要落库，如果需要则落库，然后返回报告
        try:
            embed_batch = None
            if self._config.embedding_model.strip() and self._config.api_key.strip():
                client = LLMClient(self._config)

                def embed_batch(texts: list[str]) -> list[list[float]]:
                    return client.embed(texts)

            report = index_library(#落库
                self._storage,
                Path(self._root),
                embed_batch=embed_batch,
                force=self._force,
                on_status=self.status.emit,
            )
            self.finished.emit(report.summary())
        except Exception as exc:
            self.failed.emit(str(exc))
        
