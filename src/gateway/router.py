"""Deterministic, explainable model routing kept separate from runtime failover."""
from __future__ import annotations

from src.models.schemas import (
    CapabilityState,
    ExecutionDepth,
    ModelCandidateEvaluation,
    ModelConfig,
    ModelRoutingConstraints,
    ModelRoutingDecision,
    PriceComparison,
    Task,
)


_CODING_TASKS = {"diagnose", "change", "build", "review"}


class ModelRouter:
    """Resolve legacy Worker routes and bounded automatic main-model decisions."""

    def __init__(self, models: dict[str, ModelConfig], default_routing: dict[str, str]):
        self.models = models
        self.default_routing = default_routing

    def resolve_model(self, task: Task) -> ModelConfig:
        """Resolve the existing Worker assignment contract."""
        model_name = task.assigned_model
        if not model_name or model_name not in self.models:
            model_name = self.default_routing.get(task.type)
        if not model_name or model_name not in self.models:
            raise ValueError(
                f"无法为任务 {task.id}（类型 {task.type}）解析模型，"
                f"assigned_model={task.assigned_model}"
            )
        return self.models[model_name]

    def route(
        self,
        *,
        task_kind: str,
        execution_depth: ExecutionDepth,
        constraints: ModelRoutingConstraints,
        estimated_input_tokens: int,
        requested_output_tokens: int = 4096,
        unhealthy_models: set[str] | None = None,
        local_models: set[str] | None = None,
    ) -> ModelRoutingDecision:
        """Choose at most one automatic upgrade using only explicit local facts."""
        unhealthy = set(unhealthy_models or set())
        local = set(local_models or set())
        requested = constraints.requested_model
        if requested not in self.models:
            requested = next(iter(self.models), "")

        required = self.required_capabilities(task_kind, execution_depth)
        candidates = [
            self._evaluate(
                alias,
                config,
                required=required,
                execution_depth=execution_depth,
                constraints=constraints,
                estimated_input_tokens=estimated_input_tokens,
                requested_output_tokens=requested_output_tokens,
                healthy=alias not in unhealthy,
                local=alias in local,
            )
            for alias, config in self.models.items()
        ]
        requested_eval = next(
            (item for item in candidates if item.model == requested),
            None,
        )

        if constraints.mode == "fixed" and requested:
            return self._decision(
                task_kind=task_kind,
                execution_depth=execution_depth,
                constraints=constraints,
                requested=requested,
                selected=requested,
                source="user_fixed",
                reason="用户选择 fixed 路由；本轮只使用指定主模型，运行时故障仍由 failover 合同处理。",
                required=required,
                estimated_input_tokens=estimated_input_tokens,
                candidates=candidates,
            )

        eligible = [item for item in candidates if item.eligible]
        if requested_eval is not None:
            for item in eligible:
                comparison = self._price_comparison(item, requested_eval)
                if comparison == "cheaper":
                    item.score += {
                        "fast": 30.0,
                        "standard": 15.0,
                        "deep": 5.0,
                    }[execution_depth]
                elif comparison == "higher":
                    item.score -= 5.0
        eligible.sort(key=lambda item: (-item.score, item.model != requested, item.model))
        best = eligible[0] if eligible else None

        selected = requested
        source = "user_fallback"
        reason = (
            "没有候选模型在已验证能力、上下文、健康和价格条件上形成可证明优势；"
            "使用用户指定主模型。"
        )
        if best is not None and requested_eval is None:
            selected = best.model
            source = "automatic"
            reason = "指定模型不存在；选择满足当前约束的最高评分模型。"
        elif best is not None and requested_eval is not None:
            switch_reason = self._switch_reason(
                requested_eval,
                best,
                required,
                allow_optimization=task_kind != "unclassified",
            )
            if switch_reason:
                selected = best.model
                source = "automatic"
                reason = switch_reason
        elif requested:
            reason = (
                "没有其他模型满足已验证能力、上下文、健康和用户约束；"
                "保守回退到用户指定主模型。"
            )

        return self._decision(
            task_kind=task_kind,
            execution_depth=execution_depth,
            constraints=constraints,
            requested=requested,
            selected=selected,
            source=source,
            reason=reason,
            required=required,
            estimated_input_tokens=estimated_input_tokens,
            candidates=candidates,
        )

    @staticmethod
    def required_capabilities(
        task_kind: str, execution_depth: ExecutionDepth
    ) -> list[str]:
        required: list[str] = []
        if task_kind in {"answer", "explain", "monitor"}:
            required.append("chat")
        if task_kind in _CODING_TASKS:
            required.append("coding")
        if task_kind == "plan" or (
            execution_depth == "deep" and task_kind in _CODING_TASKS
        ):
            required.append("reasoning")
        return required

    def list_models(self) -> list[str]:
        return list(self.models.keys())

    def _evaluate(
        self,
        alias: str,
        config: ModelConfig,
        *,
        required: list[str],
        execution_depth: ExecutionDepth,
        constraints: ModelRoutingConstraints,
        estimated_input_tokens: int,
        requested_output_tokens: int,
        healthy: bool,
        local: bool,
    ) -> ModelCandidateEvaluation:
        states = {
            capability: self._routing_capability_state(config, capability)
            for capability in required
        }
        window = config.context_window_tokens or config.max_context_tokens or 32_000
        context_known = bool(
            config.max_context_tokens > 0
            or (
                config.context_window_tokens > 0
                and self._is_verified_source(config.context_window_source)
            )
        )
        safe_input = max(
            0,
            int(window * (1.0 - config.context_safety_ratio))
            - requested_output_tokens,
        )
        context_fits = estimated_input_tokens <= safe_input
        price_known = local or self._is_verified_source(config.metadata_source)
        estimated_cost = (
            0.0
            if local
            else (
                (
                    estimated_input_tokens * config.input_price_per_1m
                    + requested_output_tokens * config.output_price_per_1m
                )
                / 1_000_000
                if price_known
                else None
            )
        )

        reasons: list[str] = []
        eligible = True
        if constraints.allowed_models and alias not in constraints.allowed_models:
            eligible = False
            reasons.append("不在用户允许模型列表中")
        if constraints.require_local and not local:
            eligible = False
            reasons.append("用户要求本地模型")
        if not healthy:
            eligible = False
            reasons.append("模型处于健康冷却期")
        if not context_fits:
            eligible = False
            reasons.append(f"安全输入预算不足（{safe_input} tokens）")
        for capability, state in states.items():
            if state != "supported":
                eligible = False
                reasons.append(f"能力 {capability} 为 {state}，不能用于自动升级")
        if constraints.max_input_price_per_1m is not None:
            if not price_known:
                eligible = False
                reasons.append("价格未知，无法证明满足输入价格上限")
            elif config.input_price_per_1m > constraints.max_input_price_per_1m:
                eligible = False
                reasons.append("超过用户输入价格上限")
        if constraints.max_output_price_per_1m is not None:
            if not price_known:
                eligible = False
                reasons.append("价格未知，无法证明满足输出价格上限")
            elif config.output_price_per_1m > constraints.max_output_price_per_1m:
                eligible = False
                reasons.append("超过用户输出价格上限")

        score = float(sum(state == "supported" for state in states.values()) * 25)
        if context_known:
            score += 5.0
        if price_known:
            score += 5.0
        if local:
            score += {"fast": 25.0, "standard": 10.0, "deep": 0.0}[execution_depth]
        if not eligible:
            score -= 1000.0
        elif not reasons:
            reasons.append("满足本轮全部确定性约束")

        return ModelCandidateEvaluation(
            model=alias,
            provider=config.provider,
            eligible=eligible,
            healthy=healthy,
            local=local,
            capability_states=states,
            context_known=context_known,
            context_fits=context_fits,
            safe_input_tokens=safe_input,
            price_known=price_known,
            estimated_cost_usd=estimated_cost,
            score=score,
            reasons=reasons,
        )

    @classmethod
    def _routing_capability_state(
        cls, config: ModelConfig, capability: str
    ) -> CapabilityState:
        if capability in config.capability_status:
            return config.capability_status[capability]
        if (
            capability in config.capabilities
            and cls._is_verified_source(config.metadata_source)
        ):
            return "supported"
        return "unverified"

    @staticmethod
    def _is_verified_source(source: str) -> bool:
        normalized = source.strip().casefold()
        return bool(normalized) and "unverified" not in normalized and normalized != "unknown"

    @classmethod
    def _switch_reason(
        cls,
        requested: ModelCandidateEvaluation,
        best: ModelCandidateEvaluation,
        required: list[str],
        *,
        allow_optimization: bool,
    ) -> str:
        if best.model == requested.model:
            return ""
        if not requested.healthy:
            return f"用户指定模型处于健康冷却期；本轮选择健康模型 {best.model}。"
        if not requested.context_fits:
            return f"用户指定模型上下文预算不足；本轮选择可容纳输入的 {best.model}。"
        if not allow_optimization:
            return ""
        missing = [
            name
            for name in required
            if requested.capability_states.get(name) != "supported"
            and best.capability_states.get(name) == "supported"
        ]
        if missing:
            return f"{best.model} 具有已验证能力 {', '.join(missing)}；本轮自动选择该模型。"
        comparison = cls._price_comparison(best, requested)
        if comparison == "cheaper" and best.score >= requested.score + 5.0:
            return f"{best.model} 在满足相同约束时具有可验证的更低估算成本。"
        return ""

    @classmethod
    def _decision(
        cls,
        *,
        task_kind: str,
        execution_depth: ExecutionDepth,
        constraints: ModelRoutingConstraints,
        requested: str,
        selected: str,
        source: str,
        reason: str,
        required: list[str],
        estimated_input_tokens: int,
        candidates: list[ModelCandidateEvaluation],
    ) -> ModelRoutingDecision:
        requested_eval = next((item for item in candidates if item.model == requested), None)
        selected_eval = next((item for item in candidates if item.model == selected), None)
        comparison = cls._price_comparison(selected_eval, requested_eval)
        return ModelRoutingDecision(
            task_kind=task_kind,
            execution_depth=execution_depth,
            requested_model=requested,
            selected_model=selected,
            source=source,
            reason=reason,
            required_capabilities=required,
            context_tokens_required=estimated_input_tokens,
            price_comparison=comparison,
            savings_claim_allowed=comparison == "cheaper",
            upgrade_count=int(bool(selected and selected != requested)),
            constraints=constraints.model_copy(deep=True),
            candidates=candidates,
        )

    @staticmethod
    def _price_comparison(
        selected: ModelCandidateEvaluation | None,
        requested: ModelCandidateEvaluation | None,
    ) -> PriceComparison:
        if (
            selected is None
            or requested is None
            or not selected.price_known
            or not requested.price_known
            or selected.estimated_cost_usd is None
            or requested.estimated_cost_usd is None
        ):
            return "unknown"
        delta = selected.estimated_cost_usd - requested.estimated_cost_usd
        if abs(delta) < 1e-12:
            return "equal"
        return "cheaper" if delta < 0 else "higher"
