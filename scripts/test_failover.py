"""真实接口验证脚本；必须显式传 --live，避免误消耗模型额度。"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage


async def stream_failover_demo():
    gateway = GatewayClient("config/providers.yaml")
    print(f"主模型: {gateway.main_model}")
    print(f"可用模型: {list(gateway.models.keys())}")
    print(f"故障切换链: {gateway._get_failover_chain(gateway.main_model)}")
    print("\n--- 开始流式请求 ---\n")

    messages = [
        ChatMessage(role="user", content="请用一句话介绍一下 Transformer Decoder")
    ]

    chunks = []
    try:
        async for chunk in gateway.chat_with_main_model_stream(
            messages=messages,
            task_id="failover-test",
            max_tokens=2000,
            temperature=0.2,
        ):
            chunks.append(chunk)
            print(f"[{chunk.type}]", end=" ", flush=True)
            if chunk.type == "failover":
                print(f"from={chunk.from_model} to={chunk.to_model} reason={chunk.reason}")
            elif chunk.type == "delta":
                print(repr(chunk.content), flush=True)
            elif chunk.type == "usage":
                print(f"in={chunk.input_tokens} out={chunk.output_tokens} cost=${chunk.cost_usd:.6f}", flush=True)
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        return

    print("\n\n--- 完成 ---")
    print(f"总 chunk 数: {len(chunks)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="使用真实模型验证故障切换")
    parser.add_argument(
        "--live",
        action="store_true",
        help="确认调用 config/providers.yaml 中的真实接口并消耗额度",
    )
    args = parser.parse_args()
    if not args.live:
        print("未执行：真实接口验证必须显式传入 --live。离线验证请运行 demo_failover.py。")
    else:
        asyncio.run(stream_failover_demo())
