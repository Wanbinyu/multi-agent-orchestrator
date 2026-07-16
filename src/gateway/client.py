"""模型网关客户端"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from typing import Any

import yaml

from src.core.config_paths import resolve_providers_config_path
from src.core.context_budget import ContextBudget, ContextBudgetManager
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
        self.default_failover_chain: list[str] = []
        # 模型健康状态：model_name -> 预计恢复健康的时间戳
        self._unhealthy_models: dict[str, float] = {}
        # 最近一次非流式调用发生的故障切换信息
        self.last_failover: dict[str, str] | None = None
        self.context_budget_manager = ContextBudgetManager()
        self.last_context_budget: ContextBudget | None = None
        self._load_config(config_path)

    def get_context_budget(
        self,
        model_name: str,
        messages: list[ChatMessage],
        *,
        max_tokens: int = 4096,
        tools: Any = None,
    ) -> ContextBudget:
        config = self.get_model_config(model_name)
        manager = getattr(self, "context_budget_manager", None)
        if manager is None:
            manager = ContextBudgetManager()
            self.context_budget_manager = manager
        return manager.calculate(
            model_name,
            config,
            messages,
            requested_output_tokens=max_tokens,
            tools=tools,
        )

    def _validate_context_request(
        self,
        model_name: str,
        messages: list[ChatMessage],
        kwargs: dict[str, Any],
    ) -> ContextBudget:
        budget = self.get_context_budget(
            model_name,
            messages,
            max_tokens=kwargs.get("max_tokens", 4096),
            tools=kwargs.get("tools"),
        )
        self.last_context_budget = budget
        self.context_budget_manager.ensure_fits(budget)
        return budget

    def _load_config(self, config_path: str):
        resolved = resolve_providers_config_path(config_path)
        with resolved.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

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

        # 全局默认故障切换链
        self.default_failover_chain = data.get("default_failover_chain", [])

        # 默认路由
        default_routing = {
            "frontend": "claude-sonnet-5",
            "backend": "glm-ark",
            "test": "claude-haiku-4-5",
            "doc": "glm-4-flash",
        }
        self.router = ModelRouter(self.models, default_routing)

    def _get_failover_chain(self, model_name: str) -> list[str]:
        """递归构建故障切换链，并跳过仍在冷却期的模型。"""
        model_config = self.models.get(model_name)
        if not model_config or not model_config.failover_enabled:
            return [model_name]

        chain = [model_name]
        cursor = 0
        while cursor < len(chain):
            current = chain[cursor]
            cursor += 1
            current_config = self.models.get(current)
            if not current_config or not current_config.failover_enabled:
                continue
            fallbacks = current_config.fallback_models or self.default_failover_chain
            for fallback in fallbacks:
                if fallback in self.models and fallback not in chain:
                    chain.append(fallback)

        now = time.time()
        healthy = [m for m in chain if self._unhealthy_models.get(m, 0) <= now]
        # 全部不健康时至少保留主模型，避免无模型可用
        return healthy if healthy else chain[:1]

    def _mark_unhealthy(self, model_name: str, exc: Exception):
        """根据错误类型把模型标记为不健康一段时间"""
        model_config = self.models.get(model_name)
        cooldown = model_config.failover_cooldown_seconds if model_config else 60
        if self._is_quota_error(exc):
            cooldown = max(cooldown, self._quota_cooldown_seconds(exc))
        self._unhealthy_models[model_name] = time.time() + cooldown

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        """从常见 SDK 异常中提取 HTTP 状态码。"""
        for candidate in (exc, getattr(exc, "response", None)):
            value = getattr(candidate, "status_code", None)
            if isinstance(value, int):
                return value
        match = re.search(r"(?:error\s+code|status(?:\s+code)?)\s*[:=]?\s*(\d{3})", str(exc), re.I)
        return int(match.group(1)) if match else None

    @classmethod
    def _quota_cooldown_seconds(cls, exc: Exception) -> int:
        """优先采用 Retry-After，否则从错误文本解析时间窗口。"""
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
        if retry_after:
            try:
                return max(300, int(float(retry_after)))
            except (TypeError, ValueError):
                pass

        message = str(exc).lower()
        patterns = (
            (r"(\d+(?:\.\d+)?)\s*[- ]?hours?", 3600),
            (r"(\d+(?:\.\d+)?)\s*[- ]?minutes?", 60),
            (r"(\d+(?:\.\d+)?)\s*[- ]?seconds?", 1),
        )
        for pattern, multiplier in patterns:
            match = re.search(pattern, message)
            if match:
                return max(300, int(float(match.group(1)) * multiplier))
        return 300

    @staticmethod
    def _is_fatal_error(exc: Exception) -> bool:
        """认证失败等 Provider 级致命错误：不重试、不切换"""
        msg = str(exc).lower()
        return GatewayClient._status_code(exc) == 401 or any(k in msg for k in (
            "authentication", "api key", "unauthorized", "401",
        ))

    @staticmethod
    def _is_model_unavailable(exc: Exception) -> bool:
        """模型不存在/不支持：跳过当前模型，继续尝试下一个"""
        msg = str(exc).lower()
        if GatewayClient._status_code(exc) == 404:
            return True
        return any(k in msg for k in (
            "model_not_found", "model not found", "model does not exist",
            "unsupportedmodel", "unsupported model", "model is not supported",
            "invalidendpointormodel", "invalid endpoint or model",
        ))

    @staticmethod
    def _is_request_error(exc: Exception) -> bool:
        """请求体或参数错误不能靠切换模型修复，应立即暴露给调用方。"""
        if GatewayClient._is_model_unavailable(exc) or GatewayClient._is_quota_error(exc):
            return False
        status = GatewayClient._status_code(exc)
        msg = str(exc).lower()
        return status in (400, 422) or any(k in msg for k in (
            "badrequest", "bad request", "invalid_request", "invalid request",
            "invalid max_tokens", "invalid parameter", "validation error",
        ))

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        """配额/限流错误：当前模型不再重试，直接切换到下一个"""
        msg = str(exc).lower()
        return GatewayClient._status_code(exc) == 429 or any(k in msg for k in (
            "429", "quota", "rate limit", "too many requests",
            "accountquotaexceeded",
        ))

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        """连接/超时类错误：允许重试，然后切换"""
        msg = str(exc).lower()
        return any(k in msg for k in (
            "connection", "timeout", "unreachable", "network",
            "api connection", "service unavailable", "503",
        ))

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
        """统一对话入口，支持故障切换链"""
        model_config = self.models.get(model_name)
        if not model_config:
            raise ValueError(f"未知模型: {model_name}")
        provider = self.providers.get(model_config.provider)
        if not provider:
            raise ValueError(f"未知 provider: {model_config.provider}")

        self.last_failover = None
        last_error = None
        chain = self._get_failover_chain(model_name)
        tried_models = 0
        if chain and chain[0] != model_name:
            self.last_failover = {
                "from_model": model_name,
                "to_model": chain[0],
                "reason": "原模型仍处于健康冷却期",
            }

        for idx, current_model in enumerate(chain):
            model_config = self.models.get(current_model)
            if not model_config:
                continue
            provider = self.providers.get(model_config.provider)
            if not provider:
                continue

            self._validate_context_request(current_model, messages, kwargs)

            tried_models += 1
            for attempt in range(max_retries + 1):
                try:
                    response = provider.chat(messages, model_config, **kwargs)
                    self.billing.record(response, task_id=task_id)
                    return response
                except Exception as e:
                    last_error = e
                    if self._is_fatal_error(e):
                        raise RuntimeError(
                            f"模型 {current_model} 请求失败: {last_error}"
                        ) from e
                    if self._is_request_error(e):
                        raise RuntimeError(
                            f"模型 {current_model} 请求参数错误: {last_error}"
                        ) from e
                    if self._is_quota_error(e) or self._is_model_unavailable(e):
                        break
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    break

            self._mark_unhealthy(current_model, last_error)
            if idx + 1 < len(chain):
                next_model = chain[idx + 1]
                self.last_failover = {
                    "from_model": current_model,
                    "to_model": next_model,
                    "reason": str(last_error),
                }
                continue

        if tried_models == 1:
            raise RuntimeError(
                f"模型 {model_name} 请求失败（重试 {max_retries} 次）: {last_error}"
            )
        raise RuntimeError(f"所有模型请求失败: {last_error}")

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
        """统一流式对话入口，支持故障切换链；已开始输出后不再重试/切换"""
        model_config = self.models.get(model_name)
        if not model_config:
            raise ValueError(f"未知模型: {model_name}")
        provider = self.providers.get(model_config.provider)
        if not provider:
            raise ValueError(f"未知 provider: {model_config.provider}")

        last_error = None
        chain = self._get_failover_chain(model_name)
        tried_models = 0

        if chain and chain[0] != model_name:
            yield StreamChunk(
                type="failover",
                from_model=model_name,
                to_model=chain[0],
                reason="原模型仍处于健康冷却期",
            )

        for idx, current_model in enumerate(chain):
            model_config = self.models.get(current_model)
            if not model_config:
                continue
            provider = self.providers.get(model_config.provider)
            if not provider:
                continue

            self._validate_context_request(current_model, messages, kwargs)

            tried_models += 1
            chunks_yielded = 0
            for attempt in range(max_retries + 1):
                try:
                    stream = provider.chat_stream(messages, model_config, **kwargs)
                    async for chunk in self._asyncify_stream(stream):
                        chunks_yielded += 1
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
                    # 已经向用户输出过内容，重试会造成重复/重叠，直接报错
                    if chunks_yielded > 0:
                        raise RuntimeError(
                            f"模型 {current_model} 流式请求中断: {last_error}"
                        ) from e
                    if self._is_fatal_error(e):
                        raise RuntimeError(
                            f"模型 {current_model} 请求失败: {last_error}"
                        ) from e
                    if self._is_request_error(e):
                        raise RuntimeError(
                            f"模型 {current_model} 请求参数错误: {last_error}"
                        ) from e
                    if self._is_quota_error(e) or self._is_model_unavailable(e):
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    break

            self._mark_unhealthy(current_model, last_error)
            if idx + 1 < len(chain):
                next_model = chain[idx + 1]
                yield StreamChunk(
                    type="failover",
                    from_model=current_model,
                    to_model=next_model,
                    reason=str(last_error),
                )
                continue

        if tried_models == 1:
            raise RuntimeError(
                f"模型 {model_name} 流式请求失败（重试 {max_retries} 次）: {last_error}"
            )
        raise RuntimeError(f"所有模型流式请求失败: {last_error}")

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

    def test_model(self, model_name: str) -> dict[str, Any]:
        """通过 Provider 的正式调用路径发送最小请求并同步健康状态。"""
        model_config = self.models.get(model_name)
        if not model_config:
            return {"success": False, "error": f"未知模型: {model_name}"}
        provider = self.providers.get(model_config.provider)
        if not provider:
            return {"success": False, "error": f"未知 provider: {model_config.provider}"}

        started = time.perf_counter()
        try:
            response = provider.chat(
                [ChatMessage(role="user", content="hi")],
                model_config,
                max_tokens=1,
                temperature=0,
            )
        except Exception as exc:
            self._mark_unhealthy(model_name, exc)
            return {
                "success": False,
                "provider": provider.name,
                "base_url": provider.config.base_url,
                "response_time_ms": (time.perf_counter() - started) * 1000,
                "error": str(exc),
                "consumes_quota": True,
            }

        self._unhealthy_models.pop(model_name, None)
        return {
            "success": True,
            "provider": response.provider or provider.name,
            "base_url": provider.config.base_url,
            "response_time_ms": (time.perf_counter() - started) * 1000,
            "error": "",
            "consumes_quota": True,
        }

    def get_model_config(self, model_name: str) -> ModelConfig:
        return self.models[model_name]

    def get_router(self) -> ModelRouter:
        return self.router

    def print_billing(self):
        summary = self.billing.summary()
        print(f"\n[计费] 输入 token: {summary['total_input_tokens']}")
        print(f"[计费] 输出 token: {summary['total_output_tokens']}")
        print(f"[计费] 总成本: ${summary['total_cost_usd']}")
