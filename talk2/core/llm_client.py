from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from openai import APIError, OpenAI


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    temperature: float = 0.7
    max_tokens: int | None = None
    system_prompt: str = ""
    embedding_model: str = ""


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        """保存配置；每次调用时再创建 OpenAI 客户端。
        """
        self.config = config

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: Callable[[str], None],
        should_stop: Callable[[], bool] | None = None,
    ) -> str:
        """流式对话：逐段回调 on_chunk，返回拼接后的完整文本。

        要点：
            - 三个必填项（key/model/base_url）缺失时抛 LLMError，提示去设置页；
            - 全局 system_prompt 会插在最前面；
            - should_stop 只在两个片段之间检查，无法中断已阻塞的网络请求。

        Returns:
            模型输出的完整字符串（停止时返回已生成部分）。
        """
        cfg = self.config
        if not cfg.api_key.strip():
            raise LLMError("还没有填写 API Key，请先打开设置。")
        if not cfg.model.strip():
            raise LLMError("还没有填写模型名，请先打开设置。")
        if not cfg.base_url.strip():
            raise LLMError("还没有填写 API 地址，请先打开设置。")

        payload = list(messages)
        if cfg.system_prompt.strip():
            payload = [{"role": "system", "content": cfg.system_prompt.strip()}, *payload]

        client = self._client()
        kwargs: dict = {#构建请求参数
            "model": cfg.model.strip(),
            "messages": payload,
            "stream": True,
            "temperature": cfg.temperature,
        }
        if cfg.max_tokens:
            kwargs["max_tokens"] = cfg.max_tokens

        pieces: list[str] = []
        try:
            stream = client.chat.completions.create(**kwargs)
            for event in stream:
                if should_stop and should_stop():
                    break
                if not event.choices:
                    continue
                delta = event.choices[0].delta.content
                if delta:
                    pieces.append(delta)
                    on_chunk(delta)
        except APIError as exc:
            raise LLMError(str(exc)) from exc
        except Exception as exc:  # network / timeout
            raise LLMError(str(exc)) from exc
        return "".join(pieces)

    def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        """非流式对话：一次性返回完整文本。
        """
        cfg = self.config
        if not cfg.api_key.strip():
            raise LLMError("还没有填写 API Key，请先打开设置。")
        if not cfg.model.strip():
            raise LLMError("还没有填写模型名，请先打开设置。")
        if not cfg.base_url.strip():
            raise LLMError("还没有填写 API 地址，请先打开设置。")
        try:
            response = self._client().chat.completions.create(
                model=cfg.model.strip(),
                messages=messages,
                temperature=cfg.temperature if temperature is None else temperature,
            )
            if not response.choices:
                return ""
            return response.choices[0].message.content or ""
        except APIError as exc:
            raise LLMError(str(exc)) from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化（调用 /embeddings，按 index 排序后返回）。
        """
        cfg = self.config
        model = cfg.embedding_model.strip()
        if not model:
            raise LLMError("还没有填写 embedding 模型。")
        if not texts:
            return []
        try:
            response = self._client().embeddings.create(model=model, input=texts)
            ordered = sorted(response.data, key=lambda item: item.index)
            return [list(item.embedding) for item in ordered]
        except APIError as exc:
            raise LLMError(str(exc)) from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

    def _client(self) -> OpenAI:
        """构造 OpenAI 兼容客户端（自动去掉 base_url 末尾斜杠）。
        """
        cfg = self.config
        return OpenAI(
            api_key=cfg.api_key.strip(),
            base_url=cfg.base_url.strip().rstrip("/"),
            timeout=cfg.timeout,
        )
