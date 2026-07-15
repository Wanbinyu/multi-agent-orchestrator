"""演示脚本：模拟 glm-ark 429 配额耗尽，验证自动故障切换与通知"""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.agent import Agent
from src.core.session import Session
from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, ChatResponse, StreamChunk


def _make_mock_gateway():
    """构造一个 glm-ark 会 429、glm-chat 正常的 mock gateway"""
    gw = GatewayClient.__new__(GatewayClient)
    from src.gateway.client import Billing
    from src.gateway.router import ModelRouter
    from src.models.schemas import ModelConfig, ProviderConfig

    gw.models = {
        "glm-ark": ModelConfig(
            provider="ark",
            model_id="ark-code-latest",
            fallback_models=["glm-chat"],
            failover_enabled=True,
        ),
        "glm-chat": ModelConfig(
            provider="ark",
            model_id="ark-chat-latest",
            fallback_models=[],
            failover_enabled=True,
        ),
    }
    gw.main_model = "glm-ark"
    gw.default_failover_chain = []
    gw.billing = Billing()
    gw.router = ModelRouter(gw.models, {})
    gw._unhealthy_models = {}
    gw.last_failover = None

    provider = MagicMock()
    provider.name = "ark"
    provider.config = ProviderConfig(
        name="ark",
        type="anthropic",
        base_url="https://example.com",
        api_keys=["key"],
    )

    def _chat_stream(messages, model_config, **kwargs):
        if model_config.model_id == "ark-code-latest":
            raise RuntimeError(
                "Error code: 429 - {'error': {'code': 'AccountQuotaExceeded', "
                "'message': 'You have exceeded the 5-hour usage quota.'}}"
            )
        # glm-chat 正常返回
        yield StreamChunk(type="delta", content="Transformer Decoder 是 Transformer 架构的解码器部分，")
        yield StreamChunk(type="delta", content="常用于文本生成、对话系统等自回归任务。")
        yield StreamChunk(
            type="usage",
            input_tokens=20,
            output_tokens=30,
            cost_usd=0.00005,
        )

    provider.chat_stream.side_effect = _chat_stream
    gw.providers = {"ark": provider}
    return gw


async def main():
    gateway = _make_mock_gateway()
    with tempfile.TemporaryDirectory(prefix="mao-failover-demo-") as output_dir:
        session = Session(
            id="demo",
            title="failover demo",
            created_at="2026-07-14T00:00:00+00:00",
            updated_at="2026-07-14T00:00:00+00:00",
            output_dir=output_dir,
        )
        agent = Agent(gateway, session, approval_mode="auto")

        print(">>> 模拟主模型 glm-ark 429 配额耗尽")
        print(">>> 预期：自动切换到 glm-chat，并显示故障切换通知\n")

        async for event in agent.run_turn_stream("什么是 Transformer Decoder？常用在什么地方？"):
            if event.type == "model_failover":
                delta = event.delta.replace("⚠", "[!]")
                print(f"\n[NOTIFY] {delta}")
                print(f"         reason: {event.failover.get('reason', '')}\n")
            elif event.type == "delta":
                print(event.delta, end="", flush=True)
            elif event.type == "done":
                print(f"\n\n[done] model={gateway.main_model}, files={event.files_written}")

    print("\n>>> 演示结束")


if __name__ == "__main__":
    asyncio.run(main())
