from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from talk2.core.llm_client import LLMClient, LLMConfig, LLMError
from talk2.core.rag import Hit, build_context, search
from talk2.core.storage import Storage


class StreamWorker(QObject):
    chunk = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    status = Signal(str)
    citations = Signal(object)

    def __init__(
        self,
        config: LLMConfig,
        messages: list[dict[str, str]],
        storage: Storage | None = None,
        rag_query: str = "",
        rag_root: str = "",
    ) -> None:
        super().__init__()
        self._config = config
        self._messages = messages
        self._storage = storage
        self._rag_query = rag_query
        self._rag_root = rag_root
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:#运行流式工作器，首先检查是否需要检索知识库，如果需要则检索，然后生成文本，最后返回文本
        try:
            messages = list(self._messages)
            if self._rag_query and self._rag_root and self._storage is not None:
                self.status.emit("正在检索知识库…")
                hits = self._retrieve()
                self.citations.emit([_hit_dict(hit) for hit in hits])
                messages = [
                    {"role": "system", "content": build_context(hits)},
                    *messages,
                ]
            self.status.emit("正在生成…")
            text = LLMClient(self._config).stream_chat(
                messages,
                on_chunk=self.chunk.emit,
                should_stop=lambda: self._stop,
            )
            self.completed.emit(text)
        except LLMError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _retrieve(self) -> list[Hit]:
        embed_query = None
        if self._config.embedding_model.strip() and self._config.api_key.strip():
            client = LLMClient(self._config)

            def embed_query(text: str) -> list[float]:
                vectors = client.embed([text])
                return vectors[0] if vectors else []

        assert self._storage is not None
        return search(
            self._storage,
            Path(self._rag_root),
            self._rag_query,
            embed_query=embed_query,
        )


def _hit_dict(hit: Hit) -> dict[str, str]:
    return {
        "rel_path": hit.rel_path,
        "heading_path": hit.heading_path,
        "abs_path": hit.abs_path,
    }
