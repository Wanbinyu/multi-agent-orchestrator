"""Pydantic 数据模型"""
from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


TaskExecutionMode = Literal["read", "write", "verify"]
CapabilityState = Literal["supported", "unsupported", "unverified"]


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
    execution_mode: TaskExecutionMode = Field(
        default="write", description="只读调查、文件写入或验证任务"
    )
    owned_paths: list[str] = Field(
        default_factory=list,
        description="允许写入的共享绝对路径；相对写入始终隔离在任务目录",
    )
    parallel_safe: bool = Field(default=True, description="是否允许与同层任务并行")
    max_retries: int = Field(default=1, ge=0, le=3, description="瞬时失败定向重试次数")

    @field_validator("depends_on", "owned_paths")
    @classmethod
    def deduplicate_list(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


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
    capability_status: dict[str, CapabilityState] = Field(
        default_factory=dict,
        description="显式能力真值；存在时优先于兼容用 capabilities 列表",
    )
    metadata_source: str = Field(
        default="unverified",
        min_length=1,
        description="模型 ID、能力、价格和限制信息的来源",
    )
    metadata_verified_at: str = Field(
        default="",
        description="模型元数据最近验证日期，ISO 8601 日期",
    )
    max_context_tokens: int = Field(
        default=0,
        ge=0,
        description="兼容旧配置的 MAO 安全预算；新配置优先使用 context_window_tokens",
    )
    context_window_tokens: int = Field(
        default=0,
        ge=0,
        le=2_000_000,
        description="上游声明的硬上下文窗口；0 表示未知",
    )
    max_output_tokens: int = Field(
        default=4096,
        ge=1,
        le=262_144,
        description="单次请求最大输出与默认输出预留",
    )
    context_safety_ratio: float = Field(
        default=0.08,
        ge=0.0,
        le=0.5,
        description="为计数误差和 Provider 波动预留的硬窗口比例",
    )
    compaction_threshold: float = Field(
        default=0.75,
        ge=0.25,
        le=0.95,
        description="达到安全输入预算的该比例时开始压缩",
    )
    context_window_source: str = Field(
        default="unverified",
        description="窗口信息来源；unknown/unverified 不视为官方上限",
    )
    context_window_verified_at: str = Field(
        default="",
        description="窗口信息最近验证日期，ISO 8601 日期",
    )
    dynamic_model_alias: bool = Field(
        default=False,
        description="上游 ID 是否为可能动态路由的模型别名",
    )
    native_tools: bool | None = Field(default=None, description="是否启用原生 tool_use；None=按 capabilities 自动判断")
    fallback_models: list[str] = Field(default_factory=list, description="主模型失败后的回退模型链")
    failover_enabled: bool = Field(default=True, description="是否允许自动故障切换")
    failover_cooldown_seconds: int = Field(default=60, description="模型标记为不健康后的冷却时间（秒）")

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("capability_status")
    @classmethod
    def validate_capability_names(
        cls, values: dict[str, CapabilityState]
    ) -> dict[str, CapabilityState]:
        normalized: dict[str, CapabilityState] = {}
        for name, state in values.items():
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("capability_status 不允许空能力名")
            normalized[clean_name] = state
        return normalized

    @field_validator("metadata_verified_at")
    @classmethod
    def validate_metadata_date(cls, value: str) -> str:
        if value:
            date.fromisoformat(value)
        return value

    def get_capability_state(self, capability: str) -> CapabilityState:
        """返回能力真值；没有新字段的旧配置保持原有行为。"""
        if capability in self.capability_status:
            return self.capability_status[capability]
        if not self.capability_status and capability in self.capabilities:
            return "supported"
        return "unverified"

    def supports_capability(self, capability: str) -> bool:
        return self.get_capability_state(capability) == "supported"


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
        "task_retry",
        "task_complete",
        "review_complete",
        "permission_request",
        "model_failover",
        "tool_start",
        "tool_complete",
        "engineering_start",
        "engineering_update",
        "engineering_complete",
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

    # Phase 7 工程运行记录摘要
    engineering: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Worker 执行结果"""
    task: Task
    success: bool
    content: str
    response: ChatResponse | None = None
    error: str = ""
    files_written: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=1)
    retry_errors: list[str] = Field(default_factory=list)
    acceptance_evidence: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    """Reviewer 验收结果"""
    passed: bool
    issues: list[str]
    final_output: str
