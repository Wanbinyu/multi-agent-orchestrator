"""Pydantic 数据模型"""
from typing import Any, Literal
from pydantic import BaseModel, Field


class Task(BaseModel):
    """由 Orchestrator 拆分的子任务"""
    id: str = Field(..., description="任务唯一标识")
    type: str = Field(..., description="任务类型，如 frontend/backend/test/doc")
    title: str = Field(..., description="任务标题")
    input: str = Field(..., description="完整任务输入")
    output_format: str = Field(default="", description="输出格式要求")
    acceptance: str = Field(default="", description="验收标准")
    assigned_model: str = Field(..., description="分配的模型名")
    depends_on: list[str] = Field(default_factory=list, description="依赖的任务 id 列表")


class TaskPlan(BaseModel):
    """Orchestrator 输出的任务计划"""
    summary: str = Field(default="", description="任务总览")
    tasks: list[Task] = Field(default_factory=list, description="子任务列表")


class ProviderConfig(BaseModel):
    """Provider 配置"""
    name: str
    type: Literal["anthropic", "openai", "ollama", "llamacpp"]
    base_url: str
    api_keys: list[str]
    timeout: int = 120
    rpm_limit: int = 60
    enabled: bool = True
    model_map: dict[str, str] = Field(default_factory=dict, description="逻辑模型名 -> 上游真实模型名映射")
    extra: dict[str, Any] = Field(default_factory=dict, description="Provider 专属参数，如 llamacpp 的 n_gpu_layers/n_ctx")


class ModelConfig(BaseModel):
    """模型配置"""
    provider: str
    model_id: str
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    capabilities: list[str] = Field(default_factory=list, description="模型能力标签，如 tool_use/coding/reasoning/vision")
    max_context_tokens: int = Field(default=0, description="上下文窗口大小；0 表示使用默认值")
    native_tools: bool | None = Field(default=None, description="是否启用原生 tool_use；None=按 capabilities 自动判断")
    fallback_models: list[str] = Field(default_factory=list, description="主模型失败后的回退模型链")
    failover_enabled: bool = Field(default=True, description="是否允许自动故障切换")
    failover_cooldown_seconds: int = Field(default=60, description="模型标记为不健康后的冷却时间（秒）")


class WorkerConfig(BaseModel):
    """Worker 角色配置"""
    name: str
    default_model: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    """统一消息格式"""
    role: Literal["system", "user", "assistant"]
    content: str


ApprovalMode = Literal["auto", "approve", "readonly"]


class PermissionRequest(BaseModel):
    """权限确认请求"""

    request_id: str
    tool: str
    params: dict[str, Any]
    message: str


class ChatResponse(BaseModel):
    """统一响应格式"""
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw_response: Any = None


class StreamChunk(BaseModel):
    """流式输出内部块（Provider -> Gateway -> Agent）"""

    type: Literal["delta", "usage", "failover"]
    content: str | None = None  # delta 文本
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # 故障切换信息
    from_model: str | None = None
    to_model: str | None = None
    reason: str | None = None


class ChatStreamEvent(BaseModel):
    """SSE 事件消息体（Agent -> Web/CLI）"""

    type: Literal[
        "delta",
        "usage",
        "done",
        "error",
        "plan",
        "task_start",
        "task_complete",
        "review_complete",
        "permission_request",
        "model_failover",
        "tool_start",
        "tool_complete",
    ]
    delta: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    assistant_message: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)
    error: str = ""

    # 多模型协作相关 payload
    plan: dict[str, Any] = Field(default_factory=dict)
    task: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)

    # 权限确认请求 payload
    permission_request: dict[str, Any] = Field(default_factory=dict)

    # 模型故障切换 payload
    failover: dict[str, Any] = Field(default_factory=dict)

    # 单次工具执行进度 payload
    tool_call: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Worker 执行结果"""
    task: Task
    success: bool
    content: str
    response: ChatResponse | None = None
    error: str = ""
    files_written: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    """Reviewer 验收结果"""
    passed: bool
    issues: list[str]
    final_output: str
