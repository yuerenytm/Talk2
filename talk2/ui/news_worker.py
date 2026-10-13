from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal

from talk2.core.llm_client import LLMClient, LLMConfig
from talk2.core.news_fetcher import build_digest
from talk2.core.storage import Storage


class NewsWorker(QObject):
    finished = Signal(object)
    status = Signal(str)

    def __init__(self, storage: Storage, config: LLMConfig, feeds: str) -> None:
        super().__init__()
        self._storage = storage
        self._config = config
        self._feeds = feeds

    def run(self) -> None:
        self.status.emit("正在获取新闻…")
        complete = None
        if self._config.api_key.strip() and self._config.model.strip() and self._config.base_url.strip():
            client = LLMClient(self._config)

            def complete(messages: list[dict[str, str]]) -> str:
                return client.complete(messages, temperature=0.3)

        try:
            digest = build_digest(self._feeds, complete, self._config.model.strip())
        except Exception as exc:
            from talk2.core.news_fetcher import Digest

            digest = Digest([], False, 0, self._config.model.strip(), f"这次没有取到新闻：{exc}")
        if digest.items:
            try:
                self._storage.add_news_digest(
                    json.dumps([item.__dict__ for item in digest.items], ensure_ascii=False),
                    digest.raw_source_count,
                    digest.model,
                    digest.summarized,
                )
            except Exception:
                pass
        self.finished.emit(digest.as_dict())
