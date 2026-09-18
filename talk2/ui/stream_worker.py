from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from talk2.core.llm_client import LLMClient, LLMConfig, LLMError


class StreamWorker(QObject):
    chunk = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, config: LLMConfig, messages: list[dict[str, str]]) -> None:
        super().__init__()
        self._config = config
        self._messages = messages
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            text = LLMClient(self._config).stream_chat(
                self._messages,
                on_chunk=self.chunk.emit,
                should_stop=lambda: self._stop,
            )
            self.completed.emit(text)
        except LLMError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
