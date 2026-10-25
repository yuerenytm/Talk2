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
        """保存本次请求所需的一切（配置、消息、存储、RAG 参数）。
        """
        super().__init__()
        self._config = config
        self._messages = messages
        self._storage = storage
        self._rag_query = rag_query
        self._rag_root = rag_root
        self._stop = False

    def stop(self) -> None:
        """置停止标志；run 的循环与 LLMClient 会检查它。
        """
        self._stop = True

    def run(self) -> None:
        """工作线程主函数：可选检索 → 拼上下文 → 流式生成 → 广播结果。

        检索命中时把 build_context 的结果作为一条 system 消息插在最前，
        再交给 LLMClient；异常统一转成 failed 信号。
        """
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
        """执行知识库检索。

        配了 embedding 模型时先向量化查询，否则退回纯关键词检索。
        """
        embed_query = None
        if self._config.embedding_model.strip() and self._config.api_key.strip():
            client = LLMClient(self._config)

            def embed_query(text: str) -> list[float]:
                """把查询文本转成向量（调用一次 embedding 接口）。
                """
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
    """把检索命中转成可序列化的字典，供 UI 渲染引用。
    """
    return {
        "rel_path": hit.rel_path,
        "heading_path": hit.heading_path,
        "abs_path": hit.abs_path,
    }
