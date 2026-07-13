"""模型网关客户端"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any

import yaml

from src.gateway.provider import BaseProvider, create_provider
from src.gateway.router import ModelRouter
from src.models.schemas import ChatMessage, ChatResponse, ModelConfig, ProviderConfig, StreamChunk


class Billing:
    """简单计费统计"""

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.calls: list[dict[str, Any]] = []

    def record(self, response: ChatResponse, task_id: str = ""):
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens
        self.total_cost_usd += response.cost_usd
        self.calls.append({
            "task_id": task_id,
            "model": response.model,
            "provider": response.provider,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost_usd": response.cost_usd,
        })

    def record_stream(
        self,
        *,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        task_id: str = "",
    ):
        """记录流式调用的最终 usage"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost_usd
        self.calls.append({
            "task_id": task_id,
            "model": model,
            "provider": provider,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        })

    def summary(self) -> dict[str, Any]:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "calls": self.calls,
        }


class GatewayClient:
    """统一网关：加载配置、路由、重试、计费"""

    def __init__(self, config_path: str = "config/providers.yaml"):
        self.providers: dict[str, BaseProvider] = {}
        self.models: dict[str, ModelConfig] = {}
        self.router: ModelRouter | None = None
        self.billing = Billing()
        self.main_model: str | None = None
        self._load_config(config_path)

    def _load_config(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 加载 providers
        disabled_providers: set[str] = set()
        for name, cfg in data.get("providers", {}).items():
            config = ProviderConfig(**cfg)
            if not config.enabled:
                disabled_providers.add(name)
                continue
            # 展开环境变量
            config.api_keys = [os.path.expandvars(k) for k in config.api_keys]
            self.providers[name] = create_provider(name, config)

        # 加载 models，跳过已禁用 provider 所属的模型
        for name, cfg in data.get("models", {}).items():
            if cfg.get("provider") in disabled_providers:
                continue
            self.models[name] = ModelConfig(**cfg)

        # 主模型
        self.main_model = data.get("main_model")
        if self.main_model not in self.models:
            self.main_model = next(iter(self.models), None)

        # 默认路由
        default_routing = {
            "frontend": "claude-sonnet-5",
            "backend": "glm-ark",
            "test": "claude-haiku-4-5",
            "doc": "glm-4-flash",
        }
        self.router = ModelRouter(self.models, default_routing)

    def get_main_model(self) -> str | None:
        """获取主模型别名"""
        return self.main_model

    def resolve_model(self, preferred: str | None) -> str:
        """解析可用模型：优先使用指定别名，回退到主模型，再回退到第一个可用模型"""
        if preferred and preferred in self.models:
            return preferred
        if self.main_model and self.main_model in self.models:
            return self.main_model
        first = next(iter(self.models), None)
        if first:
            return first
        raise ValueError("没有可用的模型")

    def chat_with_main_model(
        self,
        messages: list[ChatMessage],
        task_id: str = "",
        max_retries: int = 2,
        **kwargs: Any,
    ) -> ChatResponse:
        """使用主模型对话"""
        if not self.main_model:
            raise ValueError("未配置主模型")
        return self.chat(messages, self.main_model, task_id=task_id, max_retries=max_retries, **kwargs)

    def chat(
        self,
        messages: list[ChatMessage],
        model_name: str,
        task_id: str = "",
        max_retries: int = 2,
        **kwargs: Any,
    ) -> ChatResponse:
        """统一对话入口"""
        model_config = self.models.get(model_name)
        if not model_config:
            raise ValueError(f"未知模型: {model_name}")

        provider = self.providers.get(model_config.provider)
        if not provider:
            raise ValueError(f"未知 provider: {model_config.provider}")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = provider.chat(messages, model_config, **kwargs)
                self.billing.record(response, task_id=task_id)
                return response
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = 2 ** attempt
                    time.sleep(wait)
                continue

        raise RuntimeError(f"模型 {model_name} 请求失败（重试 {max_retries} 次）: {last_error}")

    async def _asyncify_stream(self, sync_gen):
        """把同步生成器包装为异步生成器，避免阻塞事件循环"""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def _reader():
            try:
                for chunk in sync_gen:
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
            except Exception as exc:  # noqa: BLE001
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop)

        threading.Thread(target=_reader, daemon=True).start()
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model_name: str,
        task_id: str = "",
        max_retries: int = 2,
        **kwargs: Any,
    ):
        """统一流式对话入口"""
        model_config = self.models.get(model_name)
        if not model_config:
            raise ValueError(f"未知模型: {model_name}")

        provider = self.providers.get(model_config.provider)
        if not provider:
            raise ValueError(f"未知 provider: {model_config.provider}")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                stream = provider.chat_stream(messages, model_config, **kwargs)
                async for chunk in self._asyncify_stream(stream):
                    if chunk.type == "usage":
                        self.billing.record_stream(
                            model=model_config.model_id,
                            provider=provider.name,
                            input_tokens=chunk.input_tokens,
                            output_tokens=chunk.output_tokens,
                            cost_usd=chunk.cost_usd,
                            task_id=task_id,
                        )
                    yield chunk
                return
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                continue

        raise RuntimeError(f"模型 {model_name} 流式请求失败（重试 {max_retries} 次）: {last_error}")

    async def chat_with_main_model_stream(
        self,
        messages: list[ChatMessage],
        task_id: str = "",
        max_retries: int = 2,
        **kwargs: Any,
    ):
        """使用主模型流式对话"""
        if not self.main_model:
            raise ValueError("未配置主模型")
        async for chunk in self.chat_stream(
            messages,
            self.main_model,
            task_id=task_id,
            max_retries=max_retries,
            **kwargs,
        ):
            yield chunk

    def get_model_config(self, model_name: str) -> ModelConfig:
        return self.models[model_name]

    def get_router(self) -> ModelRouter:
        return self.router

    def print_billing(self):
        summary = self.billing.summary()
        print(f"\n[计费] 输入 token: {summary['total_input_tokens']}")
        print(f"[计费] 输出 token: {summary['total_output_tokens']}")
        print(f"[计费] 总成本: ${summary['total_cost_usd']}")
