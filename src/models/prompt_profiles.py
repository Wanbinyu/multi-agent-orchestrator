"""Optional model behavior profiles for MAO.

Profiles are deliberately short, MAO-specific adaptations. They are not
copies of provider web-client system prompts and must not override MAO's
tool, permission, or verification policy.
"""
from __future__ import annotations


GLOBAL_MAO_PROFILE = """MAO 全局行为配置

你正在 Multi-Agent Orchestrator 中运行，而不是任何模型供应商的网页或移动端产品。不要声称拥有网页端专属功能、工具、记忆、产品信息或内部知识；只使用当前请求实际提供的工具和上下文。

默认积极帮助用户完成任务，但必须遵守 MAO 的权限、工具协议、项目规则和安全约束。不能把推测、自述或计划当作已经执行的工具结果；涉及文件、命令、测试或外部状态时，必须先执行可用工具并依据结果说明。

回答应直接、结构清晰，并匹配用户语言。遇到不确定信息要明确标记假设或待确认项；任务完成前检查验收标准和失败证据。不要重复已经完成的步骤，不要伪造测试、文件、调用、来源或成功状态。
""".strip()


PROMPT_PROFILES: dict[str, str] = {
    # Reserved for future provider/model-specific extensions. The current
    # behavior is global so it applies consistently across all model roles.
}


def normalize_prompt_profile_name(name: str) -> str:
    """Return a registered profile name or reject a configuration typo early."""
    normalized = (name or "").strip()
    if normalized and normalized not in PROMPT_PROFILES:
        available = ", ".join(sorted(PROMPT_PROFILES)) or "无（目前仅使用全局配置）"
        raise ValueError(
            f"未知 prompt_profile: {normalized!r}；可用值：{available}"
        )
    return normalized


def get_prompt_profile(name: str) -> str:
    """Return a registered profile, or an empty string when model profiles are disabled."""
    return PROMPT_PROFILES.get(normalize_prompt_profile_name(name), "")


def get_global_prompt_profile() -> str:
    """Return the behavior layer shared by every MAO gateway conversation."""
    return GLOBAL_MAO_PROFILE
