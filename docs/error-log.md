# 运行错误记录

> 记录项目运行过程中遇到的错误、原因和修复方案。

---

## 2026-07-11

### 错误 1：Worker 调用 kimi-for-coding 时 `'str' object has no attribute 'usage'`

**触发命令：**
```powershell
python run.py "帮我生成一个短篇小说，主题是吸血鬼虐恋的，西方世界背景"
```

**错误信息：**
```text
[❌] writer: 短篇小说正文创作
    错误: 模型 kimi-for-coding 请求失败（重试 2 次）: 'str' object has no attribute 'usage'
```

**原因：**
`config/providers.yaml` 中 `kimi-for-coding` 模型指向的 provider 是 `kimi1`，而 `kimi1` 的 `type` 是 `openai`：

```yaml
kimi1:
  name: Kimi 转发
  type: openai
  base_url: https://api.va11.icu/
```

但实际 `https://api.va11.icu/` 这个转发服务走的是 **Anthropic 协议**，不是 OpenAI 协议。用 OpenAI SDK 调用时，返回的是字符串而非 `ChatCompletion` 对象，代码访问 `response.usage` 时报错。

**修复：**
将 `kimi-for-coding` 的 provider 从 `kimi1` 改为 `kimi`（`type: anthropic`）：

```yaml
kimi-for-coding:
  provider: kimi
  model_id: kimi-for-coding
```

**验证：**
使用 `debug_provider.py` 测试后，`kimi`（anthropic）可正常返回，`kimi1`（openai）报错。修复后需重新运行任务验证。

---

### 错误 2：Orchestrator 无法解析 JSON 任务计划

**触发命令：**
```powershell
python run.py "帮我生成一个仙侠的短篇小说，6000字，"
```

**错误信息：**
```text
ValueError: 无法从模型输出中解析 JSON:
```

**原因：**
Orchestrator 使用的是 `glm-ark` 模型（`volcengineark` / `ark-code-latest`）。该模型在拆任务时没有稳定输出合法的 JSON，返回的内容无法被 `json.loads`、代码块提取或 `{}` 截取解析。

**修复：**
1. 在 `config/workers.yaml` 的 `orchestrator.system_prompt` 中更强制要求 JSON 输出，明确禁止 Markdown 代码块和额外解释。
2. 检测到小说类请求时，自动追加小说场景编排规则，引导模型生成合法任务计划。

修复后同一命令可正常拆分出 6 个子任务。

---

### 错误 3：后续章节收不到前置章节内容（占位符未替换）

**触发命令：**
```powershell
python run.py "帮我生成一个仙侠的短篇小说，6000字"
```

**现象：**
- 第二、三章输出为空
- 一致性检查和润色任务收到 `{{t1.output}}` 等占位符，而非实际内容
- Reviewer 报告：流程编排失败、虚假成功状态

**原因：**
Orchestrator 在任务 `input` 中使用了 `{{t1.output}}` 占位符表示依赖输出，但 `Worker.execute` 和 `Dispatcher` 没有将前置任务的实际内容注入到提示词中。

**修复：**
1. 在 `src/core/dispatcher.py` 中新增 `_build_context()`，收集每个任务的依赖任务输出。
2. 将 `context` 作为第三个参数传给 `Worker.execute`。
3. 在 `src/core/worker.py` 中新增 `_render_template()`，把 `{{task_id.output}}` 替换为实际内容，并在提示词中追加「前置任务输出」上下文。

**代码改动：**
- `src/core/dispatcher.py`：传递依赖上下文
- `src/core/worker.py`：占位符替换、上下文注入
- `tests/test_dispatcher.py`、`tests/test_dispatcher_edge_cases.py`、`tests/test_worker_e2e.py`：补充相关测试

---

### 改进：场景感知编排

**需求：**
- 小说类任务应顺序执行（第二章依赖第一章）
- 软件类任务应先出架构文档，再并行开发

**实现：**
1. 在 `src/core/orchestrator.py` 中新增 `_detect_scenario()` 和 `SCENARIO_INSTRUCTIONS`。
2. 根据用户请求关键词自动识别 `novel` 或 `software` 场景。
3. 将场景特定规则追加到 Orchestrator system_prompt 中。
4. 在 `config/workers.yaml` 中新增软件类 Worker：
   - `architect`：架构/接口设计
   - `frontend_dev`：前端开发
   - `backend_dev`：后端开发
   - `tester`：测试/集成

---

## 当前配置状态（2026-07-11 修复后）

- `kimi-for-coding` 已改回 `kimi` provider（anthropic 协议）
- `kimi1` provider（openai 协议）当前不可用，可考虑删除
- `main_model` 仍为 `glm-ark`
- 可用 orchestrator 候选：`glm-ark`、`glm-chat`、`kimi-for-coding`
- 已支持场景感知编排：`novel`、`software`
- 依赖任务输出会自动注入到下游 Worker 提示词中

---
