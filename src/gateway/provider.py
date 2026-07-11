"""Provider 抽象与实现"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import anthropic
import openai

from src.models.schemas import ChatMessage, ChatResponse, ModelConfig, ProviderConfig


class BaseProvider(ABC):
    """Provider 基类"""

    def __init__(self, name: str, config: ProviderConfig):
        self.name = name
        self.config = config
        self._key_index = 0

    def get_next_key(self) -> str:
        """轮询获取下一个 API key"""
        if not self.config.api_keys:
            raise ValueError(f"Provider {self.name} 没有配置 API key")
        key = self.config.api_keys[self._key_index]
        self._key_index = (self._key_index + 1) % len(self.config.api_keys)
        return key

    def map_model_id(self, model_id: str) -> str:
        """根据 Provider 的 model_map 把逻辑模型名映射为上游真实模型名"""
        if not self.config.model_map:
            return model_id
        mapped = self.config.model_map.get(model_id)
        if mapped:
            return mapped
        return model_id

    @abstractmethod
    def chat(self, messages: list[ChatMessage], model_config: ModelConfig, **kwargs: Any) -> ChatResponse:
        """发起对话请求"""
        pass


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API 实现"""

    def chat(self, messages: list[ChatMessage], model_config: ModelConfig, **kwargs: Any) -> ChatResponse:
        api_key = self.get_next_key()
        # 支持从环境变量读取
        api_key = os.path.expandvars(api_key)

        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=self.config.base_url or None,
            timeout=self.config.timeout,
        )

        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        upstream_model_id = self.map_model_id(model_config.model_id)
        response = client.messages.create(
            model=upstream_model_id,
            max_tokens=kwargs.get("max_tokens", 4096),
            system=system_msg or anthropic.NOT_GIVEN,
            messages=chat_messages,
            temperature=kwargs.get("temperature", 0.2),
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calc_cost(input_tokens, output_tokens, model_config)

        return ChatResponse(
            content=self._extract_text(response),
            model=upstream_model_id,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            raw_response=response,
        )

    def _extract_text(self, response: Any) -> str:
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)

    def _calc_cost(self, input_tokens: int, output_tokens: int, model_config: ModelConfig) -> float:
        return (
            input_tokens * model_config.input_price_per_1m / 1_000_000
            + output_tokens * model_config.output_price_per_1m / 1_000_000
        )


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI 兼容 API 实现（OpenAI、GLM、DeepSeek、Qwen 等）"""

    def chat(self, messages: list[ChatMessage], model_config: ModelConfig, **kwargs: Any) -> ChatResponse:
        api_key = self.get_next_key()
        api_key = os.path.expandvars(api_key)

        client = openai.OpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )

        response = client.chat.completions.create(
            model=self.map_model_id(model_config.model_id),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.2),
        )

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        cost = self._calc_cost(input_tokens, output_tokens, model_config)

        return ChatResponse(
            content=response.choices[0].message.content or "",
            model=self.map_model_id(model_config.model_id),
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            raw_response=response,
        )

    def _calc_cost(self, input_tokens: int, output_tokens: int, model_config: ModelConfig) -> float:
        return (
            input_tokens * model_config.input_price_per_1m / 1_000_000
            + output_tokens * model_config.output_price_per_1m / 1_000_000
        )


def create_provider(name: str, config: ProviderConfig) -> BaseProvider:
    """工厂函数"""
    if config.type == "anthropic":
        return AnthropicProvider(name, config)
    elif config.type == "openai":
        return OpenAICompatibleProvider(name, config)
    else:
        raise ValueError(f"不支持的 provider 类型: {config.type}")
