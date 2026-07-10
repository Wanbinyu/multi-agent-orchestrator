"""模型路由"""
from src.models.schemas import ModelConfig, Task


class ModelRouter:
    """根据任务类型或手动指定选择模型"""

    def __init__(self, models: dict[str, ModelConfig], default_routing: dict[str, str]):
        self.models = models
        self.default_routing = default_routing

    def resolve_model(self, task: Task) -> ModelConfig:
        """解析任务应使用的模型"""
        model_name = task.assigned_model

        # 如果没有指定，按任务类型走默认路由
        if not model_name or model_name not in self.models:
            model_name = self.default_routing.get(task.type)

        if not model_name or model_name not in self.models:
            raise ValueError(
                f"无法为任务 {task.id}（类型 {task.type}）解析模型，"
                f"assigned_model={task.assigned_model}"
            )

        return self.models[model_name]

    def list_models(self) -> list[str]:
        return list(self.models.keys())
