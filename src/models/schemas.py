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
    type: Literal["anthropic", "openai"]
    base_url: str
    api_keys: list[str]
    timeout: int = 120
    rpm_limit: int = 60
    model_map: dict[str, str] = Field(default_factory=dict, description="逻辑模型名 -> 上游真实模型名映射")


class ModelConfig(BaseModel):
    """模型配置"""
    provider: str
    model_id: str
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    capabilities: list[str] = Field(default_factory=list, description="模型能力标签，如 tool_use/coding/reasoning/vision")


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


class ChatResponse(BaseModel):
    """统一响应格式"""
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw_response: Any = None


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
