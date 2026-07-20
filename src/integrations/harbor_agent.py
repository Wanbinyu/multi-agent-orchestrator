"""Harbor installed-agent adapter for controlled MAO evaluations.

Harbor is an optional dependency. Import this module only from a Harbor-enabled
environment, for example with ``--agent src.integrations.harbor_agent:MaoHarborAgent``.
"""
from __future__ import annotations

import json
import shlex

from harbor.agents.installed.base import BaseInstalledAgent, CliFlag, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class MaoHarborAgent(BaseInstalledAgent):
    """Install MAO in a task container and run its headless benchmark entry point."""

    _RESULT_FILE = "mao-result.json"
    _CONSOLE_FILE = "mao-console.txt"
    CLI_FLAGS = [
        CliFlag(
            "strategy",
            cli="--strategy",
            type="enum",
            choices=["fixed-single", "auto-route", "multi-model"],
            default="auto-route",
        ),
        CliFlag(
            "execution_depth",
            cli="--execution-depth",
            type="enum",
            choices=["auto", "fast", "standard", "deep"],
            default="standard",
        ),
        CliFlag("main_model", cli="--main-model", type="str"),
        CliFlag("allowed_models", cli="--allowed-models", type="str"),
    ]

    @staticmethod
    def name() -> str:
        return "mao"

    def get_version_command(self) -> str | None:
        return '"$HOME/.local/share/mao-venv/bin/mao" --version'

    async def install(self, environment: BaseEnvironment) -> None:
        install_spec = self._get_env("MAO_INSTALL_SPEC")
        providers_config = self._get_env("MAO_PROVIDERS_CONFIG_B64")
        if not install_spec:
            raise ValueError(
                "MAO_INSTALL_SPEC is required and should pin a wheel or Git commit"
            )
        if not providers_config:
            raise ValueError(
                "MAO_PROVIDERS_CONFIG_B64 is required; encode only a template that "
                "references API-key environment variables"
            )
        await self.exec_as_root(
            environment,
            command=(
                "apt-get update && "
                "DEBIAN_FRONTEND=noninteractive apt-get install -y "
                "ca-certificates git python3 python3-venv"
            ),
        )
        await self.exec_as_agent(
            environment,
            command=(
                "mkdir -p \"$HOME/.local/share\" && "
                "python3 -m venv \"$HOME/.local/share/mao-venv\" && "
                "\"$HOME/.local/share/mao-venv/bin/python\" -m pip install "
                f"{shlex.quote(install_spec)}"
            ),
        )
        await self.exec_as_agent(
            environment,
            command=(
                "mkdir -p \"$HOME/.config/mao-benchmark\" && "
                "printf '%s' \"$MAO_PROVIDERS_CONFIG_B64\" | "
                "base64 --decode > \"$HOME/.config/mao-benchmark/providers.yaml\" && "
                "chmod 600 \"$HOME/.config/mao-benchmark/providers.yaml\""
            ),
            env={"MAO_PROVIDERS_CONFIG_B64": providers_config},
        )

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        flags = self.build_cli_flags()
        await self.exec_as_agent(
            environment,
            command=(
                "mkdir -p /logs/agent/mao-state && "
                "\"$HOME/.local/share/mao-venv/bin/mao\" benchmark-agent "
                f"--instruction {shlex.quote(instruction)} "
                "--project-root . "
                "--config \"$HOME/.config/mao-benchmark\" "
                "--state-dir /logs/agent/mao-state "
                f"--result /logs/agent/{self._RESULT_FILE} "
                f"{flags} "
                f"2>&1 | tee /logs/agent/{self._CONSOLE_FILE}"
            ),
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        result_path = self.logs_dir / self._RESULT_FILE
        if not result_path.is_file():
            return
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        context.n_input_tokens = int(payload.get("input_tokens") or 0)
        context.n_output_tokens = int(payload.get("output_tokens") or 0)
        cost = float(payload.get("cost_usd") or 0.0)
        context.cost_usd = cost if cost > 0 else None
        engineering = payload.get("engineering") or {}
        context.metadata = {
            "mao_schema_version": payload.get("schema_version"),
            "session_id": payload.get("session_id"),
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "policy": payload.get("policy") or {},
            "provider_calls": payload.get("provider_calls", 0),
            "actual_models": payload.get("actual_models") or [],
            "upstream_model_ids": payload.get("upstream_model_ids") or [],
            "tool_calls": payload.get("tool_calls", 0),
            "files_written": payload.get("files_written") or [],
            "trajectory": payload.get("trajectory") or [],
            "final_response": str(payload.get("response") or "")[:8000],
            "engineering": {
                key: engineering.get(key)
                for key in ("status", "intent", "execution_depth", "model_routing", "audit")
                if key in engineering
            },
        }
