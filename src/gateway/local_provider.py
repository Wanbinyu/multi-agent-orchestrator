"""本地 LLM Provider：Ollama 与 llama.cpp

- OllamaProvider：复用 OpenAI 兼容实现，指向 Ollama 的 /v1 端点，无需 API key。
- LocalLlamaCppProvider：进程内加载 GGUF 模型（可选依赖 llama-cpp-python），
  未安装时给出清晰错误，不影响其他 provider。

Transformer Decoder 关系说明：
  本地加载的模型（Llama/Qwen/GLM 开源版等）本身是 decoder-only Transformer，
  由 Ollama / llama.cpp 运行时承载推理。MAO 仅作为编排层调用它们，不实现 Transformer。
"""
from __future__ import annotations

from typing import Any

from src.gateway.provider import OpenAICompatibleProvider, _clean_text_for_api
from src.models.schemas import ChatMessage, ChatResponse, ModelConfig, ProviderConfig, StreamChunk


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama 本地模型接入。

    Ollama 暴露 OpenAI 兼容端点（默认 http://localhost:11434/v1），无需鉴权。
    当未配置 api_keys 时使用占位 key "ollama"。
    """

    def get_next_key(self) -> str:
        if not self.config.api_keys:
            return "ollama"
        return super().get_next_key()


class LocalLlamaCppProvider:
    """进程内 GGUF 模型接入（基于 llama-cpp-python）。

    `config.base_url` 用作 GGUF 模型文件路径；
    `config.extra` 可传 n_ctx / n_gpu_layers / n_threads 等参数。
    模型懒加载：首次调用时才载入显存/内存。
    """

    def __init__(self, name: str, config: ProviderConfig):
        self.name = name
        self.config = config
        self._llm: Any = None
        self._load_error: str | None = None

    # ---------- 与 BaseProvider 一致的接口 ----------

    def map_model_id(self, model_id: str) -> str:
        if not self.config.model_map:
            return model_id
        return self.config.model_map.get(model_id, model_id)

    def get_next_key(self) -> str:
        # llama.cpp 无需 API key
        return "local"

    def _ensure_loaded(self) -> None:
        if self._llm is not None or self._load_error:
            return
        model_path = self.config.base_url
        if not model_path:
            self._load_error = "llamacpp provider 未配置模型路径（base_url 字段应为 GGUF 文件路径）"
            return
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError:
            self._load_error = (
                "未安装 llama-cpp-python。请运行：pip install llama-cpp-python，"
                "并确保有可用的 GGUF 模型文件。"
            )
            return
        try:
            extra = self.config.extra or {}
            self._llm = Llama(
                model_path=model_path,
                n_ctx=extra.get("n_ctx", 4096),
                n_gpu_layers=extra.get("n_gpu_layers", 0),
                n_threads=extra.get("n_threads", 4),
                verbose=False,
            )
        except Exception as e:
            self._load_error = f"加载 GGUF 模型失败：{e}"

    def _raise_or_error(self) -> None:
        if self._load_error:
            raise RuntimeError(self._load_error)

    @staticmethod
    def _to_llama_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [
            {"role": m.role, "content": _clean_text_for_api(m.content)}
            for m in messages
        ]

    @staticmethod
    def _calc_cost(model_config: ModelConfig) -> float:
        # 本地模型无 API 计费
        return 0.0

    def chat(self, messages: list[ChatMessage], model_config: ModelConfig, **kwargs: Any) -> ChatResponse:
        self._ensure_loaded()
        self._raise_or_error()
        assert self._llm is not None

        response = self._llm.create_chat_completion(
            messages=self._to_llama_messages(messages),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.2),
            stream=False,
        )
        choice = response["choices"][0]
        content = choice.get("message", {}).get("content", "") or ""
        usage = response.get("usage", {}) or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        return ChatResponse(
            content=content,
            model=self.map_model_id(model_config.model_id),
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self._calc_cost(model_config),
        )

    def chat_stream(self, messages: list[ChatMessage], model_config: ModelConfig, **kwargs: Any):
        self._ensure_loaded()
        self._raise_or_error()
        assert self._llm is not None

        full_content = ""
        input_tokens = 0
        output_tokens = 0
        for chunk in self._llm.create_chat_completion(
            messages=self._to_llama_messages(messages),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.2),
            stream=True,
        ):
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if delta:
                full_content += delta
                yield StreamChunk(type="delta", content=delta)
            usage = chunk.get("usage")
            if usage:
                input_tokens = usage.get("prompt_tokens", input_tokens)
                output_tokens = usage.get("completion_tokens", output_tokens)

        # llama.cpp 流式通常不带 usage，做兜底估算
        if not output_tokens:
            output_tokens = max(1, len(full_content.encode("utf-8")) // 3)
        yield StreamChunk(
            type="usage",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self._calc_cost(model_config),
            usage_estimated=not input_tokens,
        )
