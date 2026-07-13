"""Provider 抽象与实现"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import anthropic
import openai

from src.models.schemas import ChatMessage, ChatResponse, ModelConfig, ProviderConfig, StreamChunk


def _clean_text_for_api(text: str) -> str:
    """移除无法被 UTF-8 编码的孤立代理字符（surrogate），避免 SDK 序列化失败"""
    return text.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")


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

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model_config: ModelConfig,
        **kwargs: Any,
    ):
        """同步流式对话：产生 StreamChunk（delta / usage）"""
        raise NotImplementedError(f"Provider {self.name} 尚未支持流式输出")


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API 实现"""

    def _make_client(self, api_key: str) -> anthropic.Anthropic:
        """构造 Anthropic 客户端。

        火山引擎 Coding Plan 端点（/api/coding）要求 Bearer 鉴权
        （Authorization: Bearer），用 auth_token；其它 Anthropic 兼容端点
        用默认的 x-api-key。

        对 Coding Plan 端点，优先使用环境变量 ANTHROPIC_AUTH_TOKEN（已验证
        可用的 Coding Plan Token），配置的 key 作为回退。
        """
        base_url = self.config.base_url or None
        is_coding_endpoint = bool(base_url) and "volces.com/api/coding" in base_url
        if is_coding_endpoint:
            token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or api_key
            return anthropic.Anthropic(
                auth_token=token,
                base_url=base_url,
                timeout=self.config.timeout,
            )
        return anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=self.config.timeout,
        )

    def chat(self, messages: list[ChatMessage], model_config: ModelConfig, **kwargs: Any) -> ChatResponse:
        api_key = self.get_next_key()
        # 支持从环境变量读取
        api_key = os.path.expandvars(api_key)

        client = self._make_client(api_key)

        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = _clean_text_for_api(m.content)
            else:
                chat_messages.append({"role": m.role, "content": _clean_text_for_api(m.content)})

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
            content=self._extract_content(response),
            model=upstream_model_id,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            raw_response=response,
        )

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model_config: ModelConfig,
        **kwargs: Any,
    ):
        api_key = self.get_next_key()
        api_key = os.path.expandvars(api_key)

        client = self._make_client(api_key)

        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = _clean_text_for_api(m.content)
            else:
                chat_messages.append({"role": m.role, "content": _clean_text_for_api(m.content)})

        upstream_model_id = self.map_model_id(model_config.model_id)
        with client.messages.stream(
            model=upstream_model_id,
            max_tokens=kwargs.get("max_tokens", 4096),
            system=system_msg or anthropic.NOT_GIVEN,
            messages=chat_messages,
            temperature=kwargs.get("temperature", 0.2),
        ) as stream:
            current_tool: dict[str, Any] | None = None
            real_usage = False
            full_content = ""
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    block_type = getattr(block, "type", None)
                    if block_type == "tool_use":
                        current_tool = {
                            "name": getattr(block, "name", ""),
                            "input": "",
                        }
                    else:
                        current_tool = None
                elif event.type == "content_block_delta":
                    delta = event.delta
                    delta_type = getattr(delta, "type", None)
                    if delta_type == "text_delta":
                        full_content += delta.text
                        yield StreamChunk(type="delta", content=delta.text)
                    elif delta_type == "input_json_delta" and current_tool is not None:
                        current_tool["input"] += getattr(delta, "partial_json", "")
                    # thinking_delta 不输出给用户，避免刷屏
                elif event.type == "content_block_stop" and current_tool is not None:
                    import json

                    try:
                        tool_input = json.loads(current_tool["input"])
                    except json.JSONDecodeError:
                        tool_input = {}
                    tool_name = current_tool["name"]
                    params = {
                        k: v
                        for k, v in tool_input.items()
                        if k in {"path", "content", "command"}
                    }
                    tool_md = f"```tool:{tool_name}\n{json.dumps(params, ensure_ascii=False)}\n```"
                    full_content += tool_md
                    yield StreamChunk(type="delta", content=tool_md)
                    current_tool = None
                elif (
                    event.type == "message_delta"
                    and event.usage
                    and (event.usage.input_tokens or event.usage.output_tokens)
                ):
                    real_usage = True
                    yield StreamChunk(
                        type="usage",
                        input_tokens=event.usage.input_tokens,
                        output_tokens=event.usage.output_tokens,
                        cost_usd=self._calc_cost(
                            event.usage.input_tokens,
                            event.usage.output_tokens,
                            model_config,
                        ),
                    )

            if not real_usage and full_content:
                output_tokens = max(1, len(full_content.encode("utf-8")) // 3)
                prompt_text = "\n".join(m.content for m in messages)
                input_tokens = max(1, len(prompt_text.encode("utf-8")) // 4)
                yield StreamChunk(
                    type="usage",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=self._calc_cost(input_tokens, output_tokens, model_config),
                )

    @staticmethod
    def _extract_content(response: Any) -> str:
        """把 Anthropic 返回的文本块和 tool_use 块统一转成 Markdown 工具块"""
        import json

        parts = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                parts.append(block.text)
            elif block_type == "tool_use":
                tool_input = getattr(block, "input", {}) or {}
                params = {
                    k: v for k, v in tool_input.items() if k in {"path", "content", "command"}
                }
                parts.append(
                    f"```tool:{getattr(block, 'name', '')}\n{json.dumps(params, ensure_ascii=False)}\n```"
                )
            # thinking 块不加入对话内容，避免刷屏和上下文膨胀
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
            messages=[{"role": m.role, "content": _clean_text_for_api(m.content)} for m in messages],
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.2),
        )

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        cost = self._calc_cost(input_tokens, output_tokens, model_config)

        content = response.choices[0].message.content or ""
        tool_calls = getattr(response.choices[0].message, "tool_calls", None) or []
        if tool_calls:
            content = self._join_tool_call_markdown(content, tool_calls)

        return ChatResponse(
            content=content,
            model=self.map_model_id(model_config.model_id),
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            raw_response=response,
        )

    def chat_stream(
        self,
        messages: list[ChatMessage],
        model_config: ModelConfig,
        **kwargs: Any,
    ):
        api_key = self.get_next_key()
        api_key = os.path.expandvars(api_key)

        client = openai.OpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )

        upstream_model_id = self.map_model_id(model_config.model_id)
        request_kwargs = {
            "model": upstream_model_id,
            "messages": [{"role": m.role, "content": _clean_text_for_api(m.content)} for m in messages],
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.2),
            "stream": True,
        }

        # 部分 OpenAI 兼容服务不支持 stream_options，捕获后降级
        try:
            response = client.chat.completions.create(
                **request_kwargs,
                stream_options={"include_usage": True},
            )
        except TypeError:
            response = client.chat.completions.create(**request_kwargs)

        full_content = ""
        real_usage = False
        pending_tool_calls: dict[int, dict[str, Any]] = {}

        def _flush_tool_calls() -> str:
            """把累积的 OpenAI tool_calls 转成 Markdown 工具块"""
            import json

            if not pending_tool_calls:
                return ""
            markdown = ""
            for idx in sorted(pending_tool_calls.keys()):
                tc = pending_tool_calls[idx]
                name = tc.get("name", "")
                args = tc.get("args", "")
                try:
                    params = json.loads(args)
                except json.JSONDecodeError:
                    params = {}
                params = {k: v for k, v in params.items() if k in {"path", "content", "command"}}
                markdown += f"```tool:{name}\n{json.dumps(params, ensure_ascii=False)}\n```\n"
            pending_tool_calls.clear()
            return markdown

        for chunk in response:
            delta = ""
            tool_calls_delta = []
            if chunk.choices:
                delta = chunk.choices[0].delta.content or ""
                tool_calls_delta = getattr(chunk.choices[0].delta, "tool_calls", None) or []

            if delta:
                full_content += delta
                yield StreamChunk(type="delta", content=delta)

            if tool_calls_delta:
                for tc in tool_calls_delta:
                    idx = getattr(tc, "index", 0)
                    entry = pending_tool_calls.setdefault(idx, {"name": "", "args": ""})
                    fn = getattr(tc, "function", None)
                    if fn:
                        if getattr(fn, "name", None):
                            entry["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            entry["args"] += fn.arguments

            if chunk.usage and (chunk.usage.prompt_tokens or chunk.usage.completion_tokens):
                real_usage = True
                tool_md = _flush_tool_calls()
                if tool_md:
                    full_content += tool_md
                    yield StreamChunk(type="delta", content=tool_md)
                yield StreamChunk(
                    type="usage",
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                    cost_usd=self._calc_cost(
                        chunk.usage.prompt_tokens,
                        chunk.usage.completion_tokens,
                        model_config,
                    ),
                )

        # 流结束但未出现 usage 时，也刷新 tool_calls
        final_tool_md = _flush_tool_calls()
        if final_tool_md:
            full_content += final_tool_md
            yield StreamChunk(type="delta", content=final_tool_md)

        if not real_usage and full_content:
            # 粗略估算：UTF-8 字节数 / 3 作为 token 上限近似
            output_tokens = max(1, len(full_content.encode("utf-8")) // 3)
            prompt_text = "\n".join(m.content for m in messages)
            input_tokens = max(1, len(prompt_text.encode("utf-8")) // 4)
            yield StreamChunk(
                type="usage",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._calc_cost(input_tokens, output_tokens, model_config),
            )

    @staticmethod
    def _join_tool_call_markdown(content: str, tool_calls: list[Any]) -> str:
        """把非流式 OpenAI tool_calls 追加到 Markdown 工具块"""
        import json

        parts = [content] if content else []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if not fn:
                continue
            name = getattr(fn, "name", "")
            try:
                params = json.loads(getattr(fn, "arguments", "") or "{}")
            except json.JSONDecodeError:
                params = {}
            params = {k: v for k, v in params.items() if k in {"path", "content", "command"}}
            parts.append(f"```tool:{name}\n{json.dumps(params, ensure_ascii=False)}\n```")
        return "\n".join(parts)

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
