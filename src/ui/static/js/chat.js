(function () {
  "use strict";

  const state = {
    sessions: [],
    currentSessionId: null,
    isLoading: false,
    rightbarOpen: false,
    rightbarTab: "context",
    projectTreeLoaded: false,
    turnLog: { toolCalls: [], filesWritten: [], engineering: [] },
    runDetails: {},
    planMode: "inactive",
    planArtifact: null,
    recovery: null,
    reportScope: "session",
  };

  const els = {
    sessionList: document.getElementById("session-list"),
    chatMessages: document.getElementById("chat-messages"),
    chatInput: document.getElementById("chat-input"),
    btnSend: document.getElementById("btn-send"),
    btnNewSession: document.getElementById("btn-new-session"),
    newSessionDialog: document.getElementById("new-session-dialog"),
    newSessionForm: document.getElementById("new-session-form"),
    newSessionTitle: document.getElementById("new-session-title"),
    btnCancelSession: document.getElementById("btn-cancel-session"),
    btnCancelSessionSecondary: document.getElementById("btn-cancel-session-secondary"),
    chatStatus: document.getElementById("chat-status"),
    modeIndicator: document.getElementById("mode-indicator"),
    btnPlanMode: document.getElementById("btn-plan-mode"),
    planModePanel: document.getElementById("plan-mode-panel"),
    planModeState: document.getElementById("plan-mode-state"),
    planModeContent: document.getElementById("plan-mode-content"),
    planRevisionControls: document.getElementById("plan-revision-controls"),
    planRevisionInput: document.getElementById("plan-revision-input"),
    btnPlanRevise: document.getElementById("btn-plan-revise"),
    btnPlanApprove: document.getElementById("btn-plan-approve"),
    btnPlanCancel: document.getElementById("btn-plan-cancel"),
    recoveryBanner: document.getElementById("recovery-banner"),
    recoverySummary: document.getElementById("recovery-summary"),
    recoverySteps: document.getElementById("recovery-steps"),
    btnRecoveryContinue: document.getElementById("btn-recovery-continue"),
    btnRecoveryAbandon: document.getElementById("btn-recovery-abandon"),
    chatRightbar: document.getElementById("chat-rightbar"),
    btnToggleRightbar: document.getElementById("btn-toggle-rightbar"),
    btnCloseRightbar: document.getElementById("btn-close-rightbar"),
    chatBackdrop: document.getElementById("chat-backdrop"),
    ctxSessionId: document.getElementById("ctx-session-id"),
    ctxSessionMode: document.getElementById("ctx-session-mode"),
    ctxSessionCreated: document.getElementById("ctx-session-created"),
    ctxSessionUpdated: document.getElementById("ctx-session-updated"),
    ctxBudgetUsage: document.getElementById("ctx-budget-usage"),
    ctxBudgetBar: document.getElementById("ctx-budget-bar"),
    ctxBudgetWindow: document.getElementById("ctx-budget-window"),
    ctxBudgetInput: document.getElementById("ctx-budget-input"),
    ctxBudgetRemaining: document.getElementById("ctx-budget-remaining"),
    ctxBudgetOutput: document.getElementById("ctx-budget-output"),
    ctxBudgetSource: document.getElementById("ctx-budget-source"),
    ctxCompactionRow: document.getElementById("ctx-compaction-row"),
    ctxCompaction: document.getElementById("ctx-compaction"),
    ctxEstimateRow: document.getElementById("ctx-estimate-row"),
    ctxEstimate: document.getElementById("ctx-estimate"),
    ctxBudgetWarning: document.getElementById("ctx-budget-warning"),
    btnSummarizeSession: document.getElementById("btn-summarize-session"),
    ctxSummarizeStatus: document.getElementById("ctx-summarize-status"),
    memoryList: document.getElementById("memory-list"),
    formAddMemory: document.getElementById("form-add-memory"),
    memoryCategory: document.getElementById("memory-category"),
    memoryContent: document.getElementById("memory-content"),
    memorySearch: document.getElementById("memory-search"),
    btnRefreshMemories: document.getElementById("btn-refresh-memories"),
    ctxIndexBadge: document.getElementById("ctx-index-badge"),
    ctxIndexMeta: document.getElementById("ctx-index-meta"),
    btnRebuildIndex: document.getElementById("btn-rebuild-index"),
    ctxIndexMsg: document.getElementById("ctx-index-msg"),
    turnLog: document.getElementById("turn-log"),
    deliveryReport: document.getElementById("delivery-report"),
    btnReportSession: document.getElementById("btn-report-session"),
    btnReportToday: document.getElementById("btn-report-today"),
    tabContext: document.getElementById("tab-context"),
    tabFiles: document.getElementById("tab-files"),
    rightbarContextPanel: document.getElementById("rightbar-context-panel"),
    rightbarFilesPanel: document.getElementById("rightbar-files-panel"),
    projectRootInput: document.getElementById("project-root-input"),
    projectIncludeHidden: document.getElementById("project-include-hidden"),
    btnRefreshTree: document.getElementById("btn-refresh-tree"),
    projectTreeStatus: document.getElementById("project-tree-status"),
    projectTree: document.getElementById("project-tree"),
    filePreview: document.getElementById("file-preview"),
    filePreviewName: document.getElementById("file-preview-name"),
    filePreviewMeta: document.getElementById("file-preview-meta"),
    filePreviewPath: document.getElementById("file-preview-path"),
    filePreviewContent: document.getElementById("file-preview-content"),
    btnClosePreview: document.getElementById("btn-close-preview"),
  };

  const MODES = ["auto", "approve", "readonly"];
  let currentMode = "approve";

  function updateModeIndicator() {
    if (!els.modeIndicator) return;
    els.modeIndicator.textContent = currentMode;
    els.modeIndicator.classList.remove("auto", "approve", "readonly");
    els.modeIndicator.classList.add(currentMode);
  }

  async function setMode(mode) {
    if (!MODES.includes(mode)) return;
    const previousMode = currentMode;
    currentMode = mode;
    updateModeIndicator();
    if (!state.currentSessionId) return;
    try {
      await api(`/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/mode`, {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
    } catch (err) {
      currentMode = previousMode;
      updateModeIndicator();
      console.error("切换模式失败", err);
      showStatus(err.message, true);
    }
  }

  function renderPlanState(stateName, artifact) {
    state.planMode = stateName || "inactive";
    state.planArtifact = artifact || null;
    const active = state.planMode !== "inactive";
    els.btnPlanMode?.classList.toggle("active", active);
    els.btnPlanMode?.setAttribute("aria-pressed", active ? "true" : "false");
    els.planModePanel?.classList.toggle("hidden", !active);
    if (!active) return;
    const revision = artifact?.revision ? ` · revision ${artifact.revision}` : "";
    if (els.planModeState) els.planModeState.textContent = `Plan · ${state.planMode}${revision}`;
    if (els.planModeContent) {
      els.planModeContent.innerHTML = artifact?.content
        ? renderMarkdown(artifact.content)
        : "发送需求后将生成只读方案。";
    }
    const awaiting = state.planMode === "awaiting_approval";
    els.planRevisionControls?.classList.toggle("hidden", !awaiting);
  }

  function renderRecoveryState(recovery) {
    state.recovery = recovery || null;
    const required = Boolean(recovery?.required);
    els.recoveryBanner?.classList.toggle("hidden", !required);
    if (els.chatInput) els.chatInput.disabled = required;
    if (els.btnSend) els.btnSend.disabled = required;
    if (!required) return;
    if (els.recoverySummary) {
      els.recoverySummary.textContent = `${recovery.run_status} · ${recovery.reason}`;
    }
    if (els.recoverySteps) {
      const count = recovery.unfinished_step_count || 0;
      const titles = (recovery.unfinished_steps || []).map((item) => item.title).join("、");
      els.recoverySteps.textContent = titles
        ? `未完成 ${count} 项：${titles}`
        : "上次运行没有结构化步骤，仍需确认是否继续。";
    }
  }

  async function decideRecovery(action) {
    if (!state.currentSessionId || !state.recovery?.required) return;
    els.btnRecoveryContinue.disabled = true;
    els.btnRecoveryAbandon.disabled = true;
    try {
      await api(`/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/recovery`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      await loadSession(state.currentSessionId);
      showStatus(
        action === "continue"
          ? "已确认继续；下一条消息只携带未完成步骤检查点。"
          : "已放弃中断任务；没有回滚或重放既有文件。"
      );
    } catch (err) {
      showStatus(err.message, true);
    } finally {
      els.btnRecoveryContinue.disabled = false;
      els.btnRecoveryAbandon.disabled = false;
    }
  }

  async function updatePlanState(action, payload = {}) {
    if (!state.currentSessionId || state.isLoading) return null;
    const data = await api(
      `/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/plan`,
      {
        method: "POST",
        body: JSON.stringify({ action, ...payload }),
      }
    );
    renderPlanState(data.state, data.artifact);
    return data;
  }

  async function refreshPlanState() {
    if (!state.currentSessionId) return;
    const data = await api(
      `/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/plan`
    );
    renderPlanState(data.state, data.artifact);
  }

  async function togglePlanMode() {
    try {
      await updatePlanState(state.planMode === "inactive" ? "enter" : "cancel");
      if (state.planMode !== "inactive") els.chatInput?.focus();
    } catch (err) {
      showStatus(err.message, true);
    }
  }

  async function approvePlanAndImplement() {
    try {
      const data = await updatePlanState("approve");
      if (data?.implementation_request) {
        els.chatInput.value = data.implementation_request;
        await sendMessage();
      }
    } catch (err) {
      showStatus(err.message, true);
    }
  }

  async function revisePlan() {
    const feedback = els.planRevisionInput?.value.trim();
    if (!feedback) return;
    try {
      await updatePlanState("revise", { feedback });
      els.planRevisionInput.value = "";
      els.chatInput.value = "请根据已记录的修订意见重新生成方案。";
      await sendMessage();
    } catch (err) {
      showStatus(err.message, true);
    }
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `请求失败: ${res.status}`);
    }
    return data;
  }

  function escapeHtml(text) {
    if (text == null) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? "" : d.toLocaleString("zh-CN", { hour12: false });
  }

  function sessionDisplayTitle(session) {
    const title = String(session.title || "").trim();
    return title && title !== session.id ? title : "未命名会话";
  }

  function renderMarkdown(text) {
    const codeBlocks = [];
    const source = String(text || "").replace(
      /```([^\n]*)\n([\s\S]*?)```/g,
      (_, language, code) => {
        const index = codeBlocks.length;
        const safeLanguage = String(language || "")
          .trim()
          .replace(/[^a-zA-Z0-9_-]/g, "");
        codeBlocks.push(
          `<pre class="code-block"><code class="language-${safeLanguage}">${escapeHtml(code)}</code></pre>`
        );
        return `@@MAO_CODE_BLOCK_${index}@@`;
      }
    );
    const lines = escapeHtml(source).split("\n");
    const output = [];

    const renderInline = (value) =>
      value
        .replace(/`([^`\n]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
    const splitTableRow = (line) =>
      line
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim());
    const isTableDivider = (line) => {
      const cells = splitTableRow(line);
      return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
    };

    for (let i = 0; i < lines.length; ) {
      const line = lines[i];
      const codeMatch = line.match(/^@@MAO_CODE_BLOCK_(\d+)@@$/);
      if (codeMatch) {
        output.push(codeBlocks[Number(codeMatch[1])] || "");
        i += 1;
        continue;
      }
      if (!line.trim()) {
        i += 1;
        continue;
      }
      if (/^\s*---+\s*$/.test(line)) {
        output.push("<hr>");
        i += 1;
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        const level = heading[1].length;
        output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        i += 1;
        continue;
      }
      if (i + 1 < lines.length && line.includes("|") && isTableDivider(lines[i + 1])) {
        const headers = splitTableRow(line);
        const rows = [];
        i += 2;
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
          rows.push(splitTableRow(lines[i]));
          i += 1;
        }
        output.push(
          `<table><thead><tr>${headers
            .map((cell) => `<th>${renderInline(cell)}</th>`)
            .join("")}</tr></thead><tbody>${rows
            .map(
              (row) =>
                `<tr>${headers
                  .map((_, index) => `<td>${renderInline(row[index] || "")}</td>`)
                  .join("")}</tr>`
            )
            .join("")}</tbody></table>`
        );
        continue;
      }
      if (/^\s*-\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*-\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*-\s+/, ""));
          i += 1;
        }
        output.push(`<ul>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`);
        continue;
      }
      if (/^\s*\d+\.\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
          i += 1;
        }
        output.push(`<ol>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ol>`);
        continue;
      }

      const paragraph = [line];
      i += 1;
      while (
        i < lines.length &&
        lines[i].trim() &&
        !/^(@@MAO_CODE_BLOCK_\d+@@|#{1,6}\s+|\s*---+\s*$|\s*-\s+|\s*\d+\.\s+)/.test(lines[i]) &&
        !(i + 1 < lines.length && lines[i].includes("|") && isTableDivider(lines[i + 1]))
      ) {
        paragraph.push(lines[i]);
        i += 1;
      }
      output.push(`<p>${paragraph.map(renderInline).join("<br>")}</p>`);
    }
    return output.join("");
  }

  function showStatus(message, isError = false) {
    els.chatStatus.textContent = message;
    els.chatStatus.classList.remove("hidden", "success", "error");
    els.chatStatus.classList.add(isError ? "error" : "success");
  }

  function hideStatus() {
    els.chatStatus.classList.add("hidden");
  }

  async function loadSessions() {
    const data = await api("/api/chat/sessions");
    state.sessions = data.sessions || [];
    renderSessionList();
  }

  function renderSessionList() {
    if (state.sessions.length === 0) {
      els.sessionList.innerHTML =
        '<li class="session-item empty">暂无会话，点击右上角新建</li>';
      return;
    }
    els.sessionList.innerHTML = state.sessions
      .map(
        (s) => `
        <li class="session-item ${s.id === state.currentSessionId ? "active" : ""}" data-id="${escapeHtml(
          s.id
        )}">
          <div class="session-title">${escapeHtml(sessionDisplayTitle(s))}</div>
          <div class="session-meta">${formatTime(s.updated_at)}</div>
        </li>
      `
      )
      .join("");

    document.querySelectorAll(".session-item").forEach((li) => {
      li.addEventListener("click", () => loadSession(li.dataset.id));
    });
  }

  function openNewSessionDialog() {
    if (!els.newSessionDialog) return;
    els.newSessionTitle.value = "";
    els.newSessionDialog.showModal();
    requestAnimationFrame(() => els.newSessionTitle.focus());
  }

  function closeNewSessionDialog() {
    els.newSessionDialog?.close();
  }

  async function createSession(title) {
    const data = await api("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title: title.trim() }),
    });
    await loadSessions();
    await loadSession(data.session_id);
    closeNewSessionDialog();
  }

  async function loadSession(sessionId) {
    const data = await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
    state.currentSessionId = data.id;
    if (data.approval_mode && MODES.includes(data.approval_mode)) {
      currentMode = data.approval_mode;
    }
    renderPlanState(data.plan_mode, data.plan_artifact);
    renderRecoveryState(data.recovery);
    updateModeIndicator();
    renderSessionList();
    renderMessages(data.messages || []);
    renderCurrentSessionContext(data);
    loadContextSidebar();
  }

  function renderCurrentSessionContext(session) {
    if (!session) return;
    if (els.ctxSessionId) els.ctxSessionId.textContent = session.id || "-";
    if (els.ctxSessionMode) {
      const mode = session.approval_mode || "approve";
      els.ctxSessionMode.innerHTML = `<span class="mode-${mode}">${escapeHtml(mode)}</span>`;
    }
    if (els.ctxSessionCreated) els.ctxSessionCreated.textContent = formatTime(session.created_at);
    if (els.ctxSessionUpdated) els.ctxSessionUpdated.textContent = formatTime(session.updated_at);
  }

  async function loadContextSidebar() {
    await Promise.all([
      loadContextBudget(), loadMemories(), loadIndexStatus(), loadDeliveryReport("session"),
    ]);
    clearTurnLog();
  }

  async function loadDeliveryReport(scope = state.reportScope) {
    if (!state.currentSessionId || !els.deliveryReport) return;
    state.reportScope = scope === "today" ? "today" : "session";
    els.btnReportSession?.classList.toggle("active", state.reportScope === "session");
    els.btnReportToday?.classList.toggle("active", state.reportScope === "today");
    els.deliveryReport.innerHTML = '<div class="empty-item">正在汇总…</div>';
    try {
      const report = await api(
        `/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/report?scope=${state.reportScope}`
      );
      renderDeliveryReport(report);
    } catch (err) {
      els.deliveryReport.innerHTML = `<div class="empty-item error-text">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderDeliveryReport(report) {
    if (!els.deliveryReport) return;
    const status = report.status_counts || {};
    const metrics = report.metrics || {};
    const operationCount = [
      ...(report.created_files || []),
      ...(report.modified_files || []),
      ...(report.other_changes || []),
    ].length;
    const passed = (report.verification_passed || []).length;
    const failed = (report.verification_failed || []).length;
    const pending = (report.pending_checks || []).length;
    const cost = Number(metrics.cost_usd || 0).toFixed(4);
    els.deliveryReport.innerHTML = `
      <div class="delivery-report-line"><span>运行</span><strong>${Number(report.run_count || 0)}</strong></div>
      <div class="delivery-report-line"><span>完成 / 受阻 / 失败</span><strong>${Number(status.completed || 0)} / ${Number(status.blocked || 0)} / ${Number(status.failed || 0)}</strong></div>
      <div class="delivery-report-line"><span>变更</span><strong>${operationCount}</strong></div>
      <div class="delivery-report-line"><span>验证 通过 / 失败 / 待确认</span><strong>${passed} / ${failed} / ${pending}</strong></div>
      <div class="delivery-report-line"><span>Token 输入 / 输出</span><strong>${Number(metrics.input_tokens || 0).toLocaleString()} / ${Number(metrics.output_tokens || 0).toLocaleString()}</strong></div>
      <div class="delivery-report-line"><span>成本</span><strong>$${cost}</strong></div>
      <div class="delivery-report-line"><span>有效交付 / 返工</span><strong>${Number(metrics.effective_deliveries || 0)} / ${Number(metrics.user_rework_runs || 0)}</strong></div>
    `;
  }

  async function loadContextBudget() {
    if (!state.currentSessionId || !els.ctxBudgetUsage) return;
    try {
      const data = await api(
        `/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/context`
      );
      const used = Number(data.current_input_tokens ?? data.current_tokens ?? 0);
      const budget = Number(data.input_budget_tokens || 0);
      const remaining = Number(data.remaining_input_tokens ?? budget - used);
      const percent = budget > 0 ? Math.min(100, Math.max(0, (used / budget) * 100)) : 0;
      els.ctxBudgetUsage.textContent = `${used.toLocaleString()} / ${budget.toLocaleString()}`;
      els.ctxBudgetBar.style.width = `${percent.toFixed(1)}%`;
      els.ctxBudgetBar.classList.toggle("warning", percent >= 75);
      els.ctxBudgetWindow.textContent = data.context_window_tokens
        ? `${Number(data.context_window_tokens).toLocaleString()} tokens`
        : "未知";
      els.ctxBudgetInput.textContent = `${budget.toLocaleString()} tokens`;
      els.ctxBudgetRemaining.textContent = `${remaining.toLocaleString()} tokens`;
      els.ctxBudgetOutput.textContent = `${Number(data.output_reserve_tokens || 0).toLocaleString()} tokens`;
      els.ctxBudgetSource.textContent = data.context_window_source || "unverified";
      const compactionCount = Number(data.compaction_count || 0);
      if (els.ctxCompactionRow && els.ctxCompaction) {
        els.ctxCompactionRow.classList.toggle("hidden", compactionCount === 0);
        if (compactionCount > 0) {
          const last = (data.recent_compactions || []).slice(-1)[0] || {};
          els.ctxCompaction.textContent =
            `${compactionCount} 次` +
            (last.before_tokens
              ? ` · 最近 ${Number(last.before_tokens).toLocaleString()} → ${Number(last.after_tokens || 0).toLocaleString()}`
              : "");
        }
      }
      const observations = data.usage_observations || [];
      if (els.ctxEstimateRow && els.ctxEstimate) {
        els.ctxEstimateRow.classList.toggle("hidden", observations.length === 0);
        if (observations.length) {
          const last = observations[observations.length - 1];
          els.ctxEstimateRow.title =
            `估算 ${Number(last.estimated_input || 0).toLocaleString()} / ` +
            `实际 ${Number(last.actual_input || 0).toLocaleString()}`;
          els.ctxEstimate.textContent = `${last.error_pct}%`;
        }
      }
      const warnings = data.warnings || [];
      els.ctxBudgetWarning.textContent = warnings.join("；");
      els.ctxBudgetWarning.classList.toggle("hidden", warnings.length === 0);
    } catch (err) {
      els.ctxBudgetUsage.textContent = "不可用";
      els.ctxBudgetWarning.textContent = err.message;
      els.ctxBudgetWarning.classList.remove("hidden");
    }
  }

  async function loadMemories(category = "") {
    if (!els.memoryList) return;
    try {
      const url = category
        ? `/api/memory/entries?category=${encodeURIComponent(category)}`
        : "/api/memory/entries";
      const data = await api(url);
      renderMemoryList(data.entries || []);
    } catch (err) {
      console.error("加载记忆失败", err);
      els.memoryList.innerHTML = '<li class="empty-item">加载失败</li>';
    }
  }

  function renderMemoryList(entries) {
    if (!els.memoryList) return;
    if (!entries.length) {
      els.memoryList.innerHTML = '<li class="empty-item">暂无记忆</li>';
      return;
    }
    els.memoryList.innerHTML = entries
      .map(
        (e) => `
        <li class="memory-item" data-id="${escapeHtml(e.id)}">
          <div class="memory-item-header">
            <span class="memory-category">${escapeHtml(e.category)}</span>
            <button class="btn btn-danger btn-sm btn-delete-memory" type="button">删除</button>
          </div>
          <div class="memory-content">${escapeHtml(e.content)}</div>
        </li>
      `
      )
      .join("");

    els.memoryList.querySelectorAll(".btn-delete-memory").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.closest(".memory-item").dataset.id;
        deleteMemoryEntry(id);
      });
    });
  }

  async function addMemoryFromForm(e) {
    e.preventDefault();
    if (!els.memoryCategory || !els.memoryContent) return;
    const category = els.memoryCategory.value;
    const content = els.memoryContent.value.trim();
    if (!content) return;
    try {
      await api("/api/memory/entries", {
        method: "POST",
        body: JSON.stringify({
          category,
          content,
          source: "sidebar",
          tags: state.currentSessionId ? [state.currentSessionId] : [],
        }),
      });
      els.memoryContent.value = "";
      await loadMemories();
    } catch (err) {
      console.error("添加记忆失败", err);
      alert(`添加记忆失败：${err.message}`);
    }
  }

  async function deleteMemoryEntry(id) {
    if (!id) return;
    try {
      await api(`/api/memory/entries/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadMemories();
    } catch (err) {
      console.error("删除记忆失败", err);
      alert(`删除记忆失败：${err.message}`);
    }
  }

  let memorySearchTimer = null;
  function searchMemoryFromInput(query) {
    if (memorySearchTimer) clearTimeout(memorySearchTimer);
    memorySearchTimer = setTimeout(async () => {
      if (!query.trim()) {
        await loadMemories();
        return;
      }
      try {
        const data = await api("/api/memory/search", {
          method: "POST",
          body: JSON.stringify({ query, top_k: 20 }),
        });
        renderMemoryList(data.entries || []);
      } catch (err) {
        console.error("搜索记忆失败", err);
      }
    }, 300);
  }

  async function loadIndexStatus() {
    if (!els.ctxIndexBadge || !els.ctxIndexMeta) return;
    try {
      const data = await api("/api/memory/files/status");
      renderIndexStatus(data);
    } catch (err) {
      console.error("加载索引状态失败", err);
      renderIndexStatus({ indexed: false, updated_at: null, file_count: 0 });
    }
  }

  function renderIndexStatus(status) {
    if (!els.ctxIndexBadge || !els.ctxIndexMeta) return;
    if (status.indexed) {
      els.ctxIndexBadge.textContent = "已索引";
      els.ctxIndexBadge.classList.add("indexed");
      const time = formatTime(status.updated_at);
      els.ctxIndexMeta.textContent = `${status.file_count || 0} 个文件${time ? " · " + time : ""}`;
    } else {
      els.ctxIndexBadge.textContent = "未索引";
      els.ctxIndexBadge.classList.remove("indexed");
      els.ctxIndexMeta.textContent = "";
    }
  }

  async function rebuildProjectIndex() {
    if (!els.btnRebuildIndex || !els.ctxIndexMsg) return;
    els.btnRebuildIndex.disabled = true;
    els.ctxIndexMsg.classList.remove("hidden", "success", "error");
    els.ctxIndexMsg.textContent = "正在重建索引…";
    try {
      await api("/api/memory/index", {
        method: "POST",
        body: JSON.stringify({ root_dir: ".", force: true }),
      });
      els.ctxIndexMsg.textContent = "索引重建成功";
      els.ctxIndexMsg.classList.add("success");
      await loadIndexStatus();
    } catch (err) {
      els.ctxIndexMsg.textContent = `索引失败：${err.message}`;
      els.ctxIndexMsg.classList.add("error");
    } finally {
      els.btnRebuildIndex.disabled = false;
      setTimeout(() => els.ctxIndexMsg.classList.add("hidden"), 3000);
    }
  }

  async function summarizeCurrentSession() {
    if (!state.currentSessionId || !els.btnSummarizeSession || !els.ctxSummarizeStatus) return;
    els.btnSummarizeSession.disabled = true;
    els.ctxSummarizeStatus.classList.remove("hidden", "success", "error");
    els.ctxSummarizeStatus.textContent = "正在总结…";
    try {
      await api(`/api/memory/summarize/${encodeURIComponent(state.currentSessionId)}`, {
        method: "POST",
      });
      els.ctxSummarizeStatus.textContent = "总结完成，已保存到记忆";
      els.ctxSummarizeStatus.classList.add("success");
      await loadMemories();
    } catch (err) {
      els.ctxSummarizeStatus.textContent = `总结失败：${err.message}`;
      els.ctxSummarizeStatus.classList.add("error");
    } finally {
      els.btnSummarizeSession.disabled = false;
      setTimeout(() => els.ctxSummarizeStatus.classList.add("hidden"), 4000);
    }
  }

  function setRightbarOpen(open) {
    state.rightbarOpen = open;
    if (els.chatRightbar) {
      els.chatRightbar.classList.toggle("open", state.rightbarOpen);
    }
    document.querySelector(".chat-layout")?.classList.toggle("rightbar-collapsed", !state.rightbarOpen);
    els.chatBackdrop?.classList.toggle("open", state.rightbarOpen);
    els.btnToggleRightbar?.setAttribute("aria-expanded", String(state.rightbarOpen));
  }

  function toggleRightbar() {
    setRightbarOpen(!state.rightbarOpen);
  }

  function setRightbarTab(tab) {
    const showFiles = tab === "files";
    state.rightbarTab = showFiles ? "files" : "context";
    els.tabContext?.classList.toggle("active", !showFiles);
    els.tabFiles?.classList.toggle("active", showFiles);
    els.tabContext?.setAttribute("aria-selected", String(!showFiles));
    els.tabFiles?.setAttribute("aria-selected", String(showFiles));
    els.rightbarContextPanel?.classList.toggle("hidden", showFiles);
    els.rightbarFilesPanel?.classList.toggle("hidden", !showFiles);
    if (showFiles && !state.projectTreeLoaded) loadProjectTree();
  }

  function setProjectTreeStatus(message, isError = false) {
    if (!els.projectTreeStatus) return;
    els.projectTreeStatus.textContent = message;
    els.projectTreeStatus.classList.toggle("error", isError);
  }

  function formatBytes(size) {
    if (size == null || Number.isNaN(Number(size))) return "";
    const bytes = Number(size);
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function hideFilePreview() {
    els.filePreview?.classList.add("hidden");
    els.projectTree?.querySelectorAll(".project-tree-row.selected").forEach((row) => {
      row.classList.remove("selected");
    });
  }

  async function previewProjectFile(entry, row) {
    if (!els.filePreview || !els.filePreviewContent) return;
    els.projectTree?.querySelectorAll(".project-tree-row.selected").forEach((item) => {
      item.classList.remove("selected");
    });
    row.classList.add("selected");
    els.filePreview.classList.remove("hidden");
    els.filePreviewName.textContent = entry.name;
    els.filePreviewPath.textContent = entry.path;
    els.filePreviewMeta.textContent = "正在读取…";
    els.filePreviewContent.textContent = "";
    try {
      const data = await api("/api/chat/project/file", {
        method: "POST",
        body: JSON.stringify({ path: entry.path, max_chars: 20000 }),
      });
      const suffix = data.truncated ? " · 已截断" : "";
      els.filePreviewMeta.textContent = `${formatBytes(data.size)} · ${data.encoding}${suffix}`;
      els.filePreviewPath.textContent = data.path;
      els.filePreviewContent.textContent = data.content;
      els.filePreview.scrollIntoView({ block: "nearest" });
    } catch (err) {
      els.filePreviewMeta.textContent = "读取失败";
      els.filePreviewContent.textContent = err.message;
    }
  }

  function createProjectTreeNode(entry) {
    const node = document.createElement("li");
    node.className = "project-tree-node";
    node.setAttribute("role", "treeitem");

    const row = document.createElement("button");
    row.type = "button";
    row.className = "project-tree-row";
    row.title = entry.path;

    const canExpand = entry.is_dir && !entry.is_symlink;
    const toggle = document.createElement("span");
    toggle.className = "project-tree-toggle";
    toggle.textContent = canExpand ? "›" : "";
    const icon = document.createElement("span");
    icon.className = "project-tree-icon";
    icon.textContent = entry.is_dir ? "▰" : "·";
    const name = document.createElement("span");
    name.className = "project-tree-name";
    name.textContent = entry.name + (entry.is_symlink ? " →" : "");
    const size = document.createElement("span");
    size.className = "project-tree-size";
    size.textContent = entry.is_dir ? "" : formatBytes(entry.size);
    row.append(toggle, icon, name, size);
    node.appendChild(row);

    if (canExpand) {
      row.setAttribute("aria-expanded", "false");
      row.addEventListener("click", async () => {
        let children = node.querySelector(":scope > .project-tree-children");
        const isExpanded = row.getAttribute("aria-expanded") === "true";
        if (children) {
          row.setAttribute("aria-expanded", String(!isExpanded));
          toggle.textContent = isExpanded ? "›" : "⌄";
          children.classList.toggle("hidden", isExpanded);
          return;
        }

        row.disabled = true;
        toggle.textContent = "…";
        try {
          const data = await api("/api/chat/project/directory", {
            method: "POST",
            body: JSON.stringify({
              path: entry.path,
              include_hidden: Boolean(els.projectIncludeHidden?.checked),
            }),
          });
          children = renderProjectTreeEntries(data.entries || [], data.truncated, false);
          children.classList.add("project-tree-children");
          node.appendChild(children);
          row.setAttribute("aria-expanded", "true");
          toggle.textContent = "⌄";
        } catch (err) {
          children = document.createElement("ul");
          children.className = "project-tree-children";
          const error = document.createElement("li");
          error.className = "project-tree-message error";
          error.textContent = err.message;
          children.appendChild(error);
          node.appendChild(children);
          toggle.textContent = "!";
        } finally {
          row.disabled = false;
        }
      });
    } else if (!entry.is_dir) {
      row.addEventListener("click", () => previewProjectFile(entry, row));
    } else {
      row.disabled = true;
    }
    return node;
  }

  function renderProjectTreeEntries(entries, truncated = false, isRoot = true) {
    const list = document.createElement("ul");
    list.className = `project-tree-list${isRoot ? " project-tree-root" : ""}`;
    list.setAttribute("role", "group");
    entries.forEach((entry) => list.appendChild(createProjectTreeNode(entry)));
    if (!entries.length) {
      const empty = document.createElement("li");
      empty.className = "project-tree-message";
      empty.textContent = "目录为空";
      list.appendChild(empty);
    }
    if (truncated) {
      const notice = document.createElement("li");
      notice.className = "project-tree-message";
      notice.textContent = "目录项过多，已截断";
      list.appendChild(notice);
    }
    return list;
  }

  async function loadProjectTree() {
    if (!els.projectTree || !els.projectRootInput || !els.btnRefreshTree) return;
    const path = els.projectRootInput.value.trim() || ".";
    els.btnRefreshTree.disabled = true;
    hideFilePreview();
    setProjectTreeStatus("正在加载…");
    els.projectTree.innerHTML = '<div class="empty-item">正在读取目录…</div>';
    try {
      const data = await api("/api/chat/project/directory", {
        method: "POST",
        body: JSON.stringify({
          path,
          include_hidden: Boolean(els.projectIncludeHidden?.checked),
        }),
      });
      els.projectRootInput.value = data.path;
      try {
        localStorage.setItem("mao.projectRoot", data.path);
      } catch (_) {
        // 浏览器禁用本地存储时仍可正常使用文件树。
      }
      els.projectTree.replaceChildren(
        renderProjectTreeEntries(data.entries || [], data.truncated, true)
      );
      const truncated = data.truncated ? " · 已截断" : "";
      setProjectTreeStatus(`${data.entries.length} 项${truncated}`);
      state.projectTreeLoaded = true;
    } catch (err) {
      els.projectTree.innerHTML = `<div class="empty-item error-text">${escapeHtml(err.message)}</div>`;
      setProjectTreeStatus(err.message, true);
      state.projectTreeLoaded = false;
    } finally {
      els.btnRefreshTree.disabled = false;
    }
  }

  function clearTurnLog() {
    state.turnLog = { toolCalls: [], filesWritten: [], engineering: [] };
    state.runDetails = {};
    if (!els.turnLog) return;
    els.turnLog.innerHTML = '<div class="empty-item">发送消息后将显示工具调用和文件记录</div>';
  }

  function appendTurnLog(toolCalls, filesWritten) {
    if (toolCalls?.length) state.turnLog.toolCalls.push(...toolCalls);
    if (filesWritten?.length) state.turnLog.filesWritten.push(...filesWritten);
    renderTurnLog();
  }

  function appendEngineeringEvent(engineering) {
    if (!engineering?.run_id) return;
    const existing = state.turnLog.engineering.findIndex(
      (item) => item.run_id === engineering.run_id
    );
    if (existing >= 0) {
      // 状态变化后已缓存的详情可能过期，下次展开时重新加载。
      if (state.turnLog.engineering[existing].status !== engineering.status) {
        delete state.runDetails[engineering.run_id];
      }
      state.turnLog.engineering[existing] = engineering;
    } else {
      state.turnLog.engineering.push(engineering);
    }
    renderTurnLog();
  }

  function renderTurnLog() {
    if (!els.turnLog) return;
    const { toolCalls, filesWritten, engineering } = state.turnLog;
    if (!toolCalls.length && !filesWritten.length && !engineering.length) {
      els.turnLog.innerHTML = '<div class="empty-item">发送消息后将显示工具调用和文件记录</div>';
      return;
    }
    let html = "";
    engineering.forEach((run) => {
      const labels = {
        running: "进行中",
        completed: "已完成",
        failed: "失败",
        blocked: "受阻",
      };
      const icon = run.status === "completed" ? "✓" : run.status === "running" ? "●" : "!";
      const intent = run.intent || {};
      const effectiveIntent = run.effective_intent || {};
      const displayIntent = Object.keys(effectiveIntent).length ? effectiveIntent : intent;
      const policy = intent.policy || {};
      const kindLabels = {
        unclassified: "未分类",
        answer: "问答",
        explain: "解释",
        diagnose: "诊断",
        change: "修改",
        build: "构建",
        review: "审查",
        plan: "方案",
        monitor: "监控",
      };
      const riskLabels = {
        unassessed: "风险未评估",
        low: "低风险",
        medium: "中风险",
        high: "高风险",
        external: "外部状态",
      };
      const depth = run.execution_depth || {};
      const depthLabels = {
        fast: "快速",
        standard: "标准",
        deep: "深入",
      };
      const toolCanWrite = Boolean(
        policy.allow_project_writes || policy.permission_follows_session
      );
      const writeState = !toolCanWrite || currentMode === "readonly"
        ? "只读"
        : (intent.write_authorized ? "写入已授权" : "写入需批准");
      const intentDetail = [
        kindLabels[displayIntent.kind] || displayIntent.kind,
        riskLabels[displayIntent.risk_level] || displayIntent.risk_level,
        depth.actual ? `${depthLabels[depth.actual] || depth.actual}执行` : "",
        writeState,
        Object.keys(effectiveIntent).length ? "按实际写入升级" : "",
      ].filter(Boolean).join(" · ");
      const recon = run.reconnaissance || {};
      const reconLabels = {
        not_started: "未开始",
        in_progress: "侦察中",
        partial: "部分覆盖",
        completed: "已覆盖",
      };
      const evidenceCount = Number(run.evidence_count || 0);
      const observedCount = (recon.observed_categories || []).length;
      const evidenceDetail = `证据 ${evidenceCount} 条 · 项目侦察 ${
        reconLabels[recon.status] || recon.status || "未开始"
      }（${observedCount}/6）`;
      const audit = run.audit || {};
      const auditLabels = {
        not_required: "无需工程验证",
        passed: "已通过",
        blocked: "未闭环",
        failed: "运行失败",
      };
      const auditGaps = [
        ...(audit.missing_checks || []),
        ...(audit.failed_checks || []),
      ].filter((item, index, values) => values.indexOf(item) === index);
      const verificationDetail = `验证门 ${Number(run.verification_count || 0)} 个 · 完成审计 ${
        auditLabels[audit.status] || audit.status || "进行中"
      }${auditGaps.length ? ` · 缺口 ${auditGaps.join("、")}` : ""}`;
      const routing = run.model_routing || {};
      const modelDetail = routing.selected_model
        ? `模型 ${routing.selected_model} · 路由 ${routing.source || "unknown"} · ${
            routing.reason || "未记录原因"
          }`
        : "";
      const detailState = state.runDetails[run.run_id] || {};
      let detailHtml = "";
      if (detailState.open) {
        if (detailState.loading) {
          detailHtml = '<div class="run-detail-line">正在加载详情…</div>';
        } else if (detailState.error) {
          detailHtml = `<div class="run-detail-line error-text">${escapeHtml(detailState.error)}</div>`;
        } else if (detailState.data) {
          detailHtml = renderRunDetail(detailState.data);
        }
      }
      html += `
        <div class="turn-log-item engineering-run ${escapeHtml(run.status || "running")}">
          <div class="turn-log-title">${icon} 工程记录 · ${escapeHtml(labels[run.status] || run.status)}</div>
          <div class="turn-log-detail">${escapeHtml(run.run_id)}</div>
          <div class="turn-log-detail">${escapeHtml(intentDetail)}</div>
          ${modelDetail ? `<div class="turn-log-detail">${escapeHtml(modelDetail)}</div>` : ""}
          <div class="turn-log-detail">${escapeHtml(evidenceDetail)}</div>
          <div class="turn-log-detail">${escapeHtml(verificationDetail)}</div>
          <button type="button" class="run-detail-toggle" data-run-id="${escapeHtml(run.run_id)}">${
            detailState.open ? "收起详情" : "展开详情"
          }</button>
          <div class="run-detail" ${detailState.open ? "" : "hidden"}>${detailHtml}</div>
        </div>
      `;
    });
    toolCalls.forEach((c) => {
      const status = c.success ? "✅" : "❌";
      const p = c.params || {};
      const detail =
        p.path || p.command || p.url || p.query ||
        Object.entries(p)
          .filter(([_, v]) => v !== undefined && v !== null && v !== "")
          .map(([k, v]) => `${k}=${v}`)
          .join(", ");
      html += `
        <div class="turn-log-item">
          <div class="turn-log-title">${status} ${escapeHtml(c.tool)}</div>
          ${detail ? `<div class="turn-log-detail">${escapeHtml(String(detail))}</div>` : ""}
        </div>
      `;
    });
    filesWritten.forEach((f) => {
      html += `
        <div class="turn-log-item">
          <div class="turn-log-title">📝 写入文件</div>
          <div class="turn-log-detail">${escapeHtml(f)}</div>
        </div>
      `;
    });
    els.turnLog.innerHTML = html;
  }

  async function toggleRunDetail(runId) {
    if (!runId || !state.currentSessionId) return;
    const entry =
      state.runDetails[runId] ||
      (state.runDetails[runId] = { open: false, loading: false, data: null, error: "" });
    entry.open = !entry.open;
    if (entry.open && !entry.data && !entry.loading) {
      entry.loading = true;
      entry.error = "";
      renderTurnLog();
      try {
        entry.data = await api(
          `/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/runs/${encodeURIComponent(runId)}`
        );
      } catch (err) {
        entry.error = err.message || "加载失败";
      } finally {
        entry.loading = false;
      }
    }
    renderTurnLog();
  }

  function renderRunDetail(run) {
    const RUN_DETAIL_LIST_LIMIT = 50;
    const sections = [];
    const addSection = (title, lines) => {
      const items = (lines || []).filter(Boolean);
      if (!items.length) return;
      sections.push(
        `<div class="run-detail-section"><div class="run-detail-heading">${escapeHtml(title)}</div>` +
          items.map((line) => `<div class="run-detail-line">${escapeHtml(line)}</div>`).join("") +
          "</div>"
      );
    };
    const bounded = (list, renderItem) => {
      const lines = (list || []).slice(0, RUN_DETAIL_LIST_LIMIT).map(renderItem);
      if ((list || []).length > RUN_DETAIL_LIST_LIMIT) {
        lines.push(`… 其余 ${list.length - RUN_DETAIL_LIST_LIMIT} 条略`);
      }
      return lines;
    };

    if (run.objective) addSection("目标", [run.objective]);
    if (run.intent) {
      const intent = run.intent;
      const policy = intent.policy || {};
      const followsSession = Boolean(policy.permission_follows_session);
      const writeState = intent.write_authorized
        ? "写入已授权"
        : (followsSession ? "权限跟随会话" : "只读或写入未授权");
      addSection("分类与边界", [
        `类型 ${intent.kind || "unclassified"} · 风险 ${intent.risk_level || "unassessed"} · ${
          writeState
        }`,
      ]);
    }
    if (run.execution_depth) {
      const depth = run.execution_depth;
      const budget = depth.budget || {};
      addSection("执行深度", [
        `请求 ${depth.requested || "auto"} · 建议 ${depth.recommended || "standard"} · 实际 ${
          depth.actual || "standard"
        } · 来源 ${depth.source || "automatic"}`,
        `工具轮次 ${Number(budget.max_tool_iterations || 0)} · Worker ${Number(
          budget.max_workers || 0
        )} · 上下文比例 ${Math.round(Number(budget.context_budget_ratio || 0) * 100)}%`,
        depth.reason || "",
      ]);
    }
    if (run.model_routing) {
      const routing = run.model_routing;
      const lines = [
        `${routing.requested_model || "无"} → ${routing.selected_model || "无"} · ${
          routing.source || "unknown"
        }`,
        routing.reason || "",
        `价格比较 ${routing.price_comparison || "unknown"} · 节省声明 ${
          routing.savings_claim_allowed ? "允许" : "不允许"
        } · 自动升级 ${Number(routing.upgrade_count || 0)}/${Number(
          routing.max_upgrades || 1
        )}`,
      ];
      (routing.candidates || []).forEach((candidate) => {
        const mark = candidate.eligible ? "✓" : "×";
        lines.push(
          `${mark} ${candidate.model} · score ${Number(candidate.score || 0).toFixed(1)} · ${
            (candidate.reasons || []).join("；") || "无说明"
          }`
        );
      });
      addSection("模型路由", lines);
    }
    if (run.effective_intent) {
      const intent = run.effective_intent;
      const mutation = run.observed_mutation || {};
      addSection("实际写入后的有效分类", [
        `类型 ${intent.kind || "unclassified"} · 风险 ${intent.risk_level || "unassessed"} · 验证 ${
          (intent.policy || {}).verification_depth || "targeted"
        } · 项目文件 ${Number(mutation.project_file_count || 0)} 个`,
      ]);
    }
    if (run.plan) {
      const planLabels = {
        pending: "待开始",
        in_progress: "进行中",
        completed: "已完成",
        failed: "失败",
        blocked: "受阻",
      };
      const steps = (run.plan.steps || []).map(
        (step) =>
          `[${planLabels[step.status] || step.status}] ${step.title}${step.note ? ` — ${step.note}` : ""}`
      );
      (run.plan.acceptance_criteria || []).forEach((criterion) =>
        steps.push(`验收：${criterion}`)
      );
      addSection(`工作计划（${planLabels[run.plan.status] || run.plan.status}）`, steps);
    }
    addSection(
      `证据（${(run.evidence || []).length} 条）`,
      bounded(run.evidence, (item) => {
        const mark = item.success ? "✓" : "✗";
        return `[${item.kind}]${mark} ${item.claim}${item.path ? `（${item.path}）` : ""}`;
      })
    );
    addSection(
      `验证门（${(run.verification || []).length} 个）`,
      bounded(run.verification, (gate) => {
        const mark = gate.passed === true ? "✓" : gate.passed === false ? "✗" : "…";
        return `${mark} [${gate.check_type}] ${gate.command_or_check}`;
      })
    );
    const reqLabels = {
      unverified: "未验证",
      satisfied: "已满足",
      failed: "未通过",
      waived: "已豁免",
    };
    addSection(
      `需求核对（${(run.requirements || []).length} 项）`,
      (run.requirements || []).map(
        (req) => `[${reqLabels[req.status] || req.status}] ${req.requirement}`
      )
    );
    if (run.audit) {
      const auditLabels = {
        not_required: "无需工程验证",
        passed: "已通过",
        blocked: "未闭环",
        failed: "运行失败",
      };
      const lines = [`状态：${auditLabels[run.audit.status] || run.audit.status}`];
      if ((run.audit.missing_checks || []).length) {
        lines.push(`缺失检查：${run.audit.missing_checks.join("、")}`);
      }
      if ((run.audit.failed_checks || []).length) {
        lines.push(`失败检查：${run.audit.failed_checks.join("、")}`);
      }
      if (run.audit.summary) lines.push(`摘要：${run.audit.summary}`);
      addSection("完成审计", lines);
    }
    addSection(
      `决策（${(run.decisions || []).length} 条）`,
      bounded(run.decisions, (decision) => `- ${decision}`)
    );
    addSection(
      `修改文件（${(run.files_changed || []).length} 个）`,
      (run.files_changed || []).map((path) => `- ${path}`)
    );
    addSection(
      "残余风险",
      (run.residual_risks || []).map((risk) => `- ${risk}`)
    );
    const metricLines = Object.entries(run.metrics || {}).map(([key, value]) => {
      const text = typeof value === "object" ? JSON.stringify(value) : String(value);
      return `${key} = ${text.slice(0, 160)}`;
    });
    addSection("指标", metricLines);
    return sections.join("") || '<div class="run-detail-line">暂无更多记录</div>';
  }

  function renderMessages(messages) {
    els.chatMessages.innerHTML = "";
    messages.forEach((m) => {
      if (m.role === "system") return;
      appendMessage(m.role, m.content, false);
    });
    scrollToBottom();
  }

  function appendMessage(role, content, scroll = true) {
    const div = document.createElement("div");
    div.className = `chat-message ${role}`;
    div.innerHTML = `
      <div class="chat-bubble ${role}">
        <div class="chat-role">${role === "user" ? "你" : "助手"}</div>
        <div class="chat-content">${renderMarkdown(content)}</div>
      </div>
    `;
    els.chatMessages.appendChild(div);
    if (scroll) scrollToBottom();
  }

  function appendToolInfo(toolCalls, filesWritten) {
    if (!toolCalls?.length && !filesWritten?.length) return;
    const div = document.createElement("div");
    div.className = "chat-tool-info";
    let html = "";
    if (toolCalls?.length) {
      html += `<div class="tool-calls">
        <strong>工具调用：</strong>
        ${toolCalls
          .map(
            (c) =>
              `<span class="tool-tag ${c.success ? "success" : "error"}">${
                c.success ? "✅" : "❌"
              } ${escapeHtml(c.tool)}</span>`
          )
          .join("")}
      </div>`;
    }
    if (filesWritten?.length) {
      html += `<div class="files-written">
        <strong>文件：</strong>
        ${filesWritten.map((f) => `<code>${escapeHtml(f)}</code>`).join(" ")}
      </div>`;
    }
    div.innerHTML = html;
    els.chatMessages.appendChild(div);
    scrollToBottom();
  }

  function scrollToBottom() {
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  }

  function createAssistantPlaceholder() {
    const div = document.createElement("div");
    div.className = "chat-message assistant streaming";
    div.innerHTML = `
      <div class="chat-bubble assistant">
        <div class="chat-role">助手</div>
        <div class="chat-content"><span class="streaming-cursor"></span></div>
      </div>
    `;
    els.chatMessages.appendChild(div);
    scrollToBottom();
    return {
      messageEl: div,
      contentEl: div.querySelector(".chat-content"),
    };
  }

  function createCollaborationPanel(plan) {
    const wrapper = document.createElement("div");
    wrapper.className = "collab-panel";

    const summary = plan.summary || "多模型协作计划";
    const tasks = plan.tasks || [];

    let html = `
      <div class="collab-summary">
        <span class="collab-title">🤖 多模型协作</span>
        <button class="collab-toggle" type="button">展开</button>
      </div>
      <div class="collab-body hidden">
        <div class="collab-desc">${escapeHtml(summary)}</div>
        <div class="collab-tasks">
    `;

    tasks.forEach((t) => {
      html += `
        <div class="collab-task" data-task-id="${escapeHtml(t.id)}">
          <span class="collab-status">⏳</span>
          <span class="collab-task-type">[${escapeHtml(t.type)}]</span>
          <span class="collab-task-title">${escapeHtml(t.title)}</span>
          <span class="collab-task-model">${escapeHtml(t.assigned_model || "")}</span>
          <div class="collab-task-detail hidden"></div>
        </div>
      `;
    });

    html += `
        </div>
        <div class="collab-review hidden"></div>
      </div>
    `;

    wrapper.innerHTML = html;

    const toggle = wrapper.querySelector(".collab-toggle");
    const body = wrapper.querySelector(".collab-body");
    toggle.addEventListener("click", () => {
      body.classList.toggle("hidden");
      toggle.textContent = body.classList.contains("hidden") ? "展开" : "折叠";
    });

    return { wrapper, taskMap: Object.fromEntries(
      Array.from(wrapper.querySelectorAll(".collab-task")).map((el) => [el.dataset.taskId, el])
    ) };
  }

  function updateTaskStatus(panel, taskId, status, error, files) {
    if (!panel || !panel.taskMap[taskId]) return;
    const el = panel.taskMap[taskId];
    const statusEl = el.querySelector(".collab-status");
    const detailEl = el.querySelector(".collab-task-detail");

    el.classList.remove("success", "error");
    if (status === "running") {
      statusEl.textContent = "⏳";
    } else if (status === "success") {
      statusEl.textContent = "✅";
      el.classList.add("success");
    } else if (status === "error") {
      statusEl.textContent = "❌";
      el.classList.add("error");
    }

    let detailHtml = "";
    if (error) {
      detailHtml += `<div class="collab-error">${escapeHtml(error)}</div>`;
    }
    if (files && files.length) {
      detailHtml += `<div class="collab-files">
        ${files.map((f) => `<code>${escapeHtml(f)}</code>`).join(" ")}
      </div>`;
    }
    if (detailHtml) {
      detailEl.innerHTML = detailHtml;
      detailEl.classList.remove("hidden");
    }
  }

  function updateCollaborationReview(panel, review) {
    if (!panel) return;
    const reviewEl = panel.wrapper.querySelector(".collab-review");
    const passed = review.passed;
    const issues = review.issues || [];
    let html = `<div class="collab-review-title ${passed ? "success" : "warning"}">
      ${passed ? "✅ 审查通过" : "⚠️ 审查未通过"}
    </div>`;
    if (issues.length) {
      html += `<ul class="collab-issues">${issues.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`;
    }
    reviewEl.innerHTML = html;
    reviewEl.classList.remove("hidden");
  }

  function createPermissionCard(request) {
    const requestId = request.request_id;
    const tool = request.tool;
    const params = request.params || {};
    const message = request.message || `${tool} 请求权限`;

    const div = document.createElement("div");
    div.className = "permission-message";
    div.dataset.requestId = requestId;

    let detail = "";
    if (tool === "collaboration") {
      const taskCount = params.task_count || (params.tasks ? params.tasks.length : 0);
      detail = `<span>${taskCount} 个子任务 · 输出 <code>${escapeHtml(params.output_dir || "")}</code></span>`;
    } else {
      // 通用展示：优先关键字段，兜底显示全部参数
      const keys = ["path", "command", "url", "query"];
      let shown = "";
      for (const k of keys) {
        if (params[k]) {
          shown = `<code>${escapeHtml(String(params[k]))}</code>`;
          break;
        }
      }
      if (!shown) {
        const entries = Object.entries(params)
          .filter(([_, v]) => v !== undefined && v !== null && v !== "")
          .map(([k, v]) => `${k}=${escapeHtml(String(v))}`);
        shown = entries.length ? `<span>${entries.join(", ")}</span>` : "";
      }
      detail = shown;
    }

    div.innerHTML = `
      <div class="permission-text">${escapeHtml(message)} ${detail}</div>
      <div class="permission-actions">
        <button class="btn btn-primary btn-approve" type="button">允许</button>
        <button class="btn btn-secondary btn-deny" type="button">拒绝</button>
      </div>
      <div class="permission-status hidden"></div>
    `;

    const statusEl = div.querySelector(".permission-status");

    async function respond(approved) {
      if (!state.currentSessionId) return;
      try {
        await api(
          `/api/chat/sessions/${encodeURIComponent(
            state.currentSessionId
          )}/permission/${encodeURIComponent(requestId)}`,
          {
            method: "POST",
            body: JSON.stringify({ approved }),
          }
        );
        div.querySelectorAll("button").forEach((b) => (b.disabled = true));
        statusEl.textContent = approved ? "✅ 已允许" : "❌ 已拒绝";
        statusEl.classList.remove("hidden");
      } catch (err) {
        statusEl.textContent = `请求失败：${escapeHtml(err.message)}`;
        statusEl.classList.remove("hidden");
      }
    }

    div.querySelector(".btn-approve").addEventListener("click", () => respond(true));
    div.querySelector(".btn-deny").addEventListener("click", () => respond(false));

    return div;
  }

  function parseSSE(buffer) {
    const events = [];
    let consumed = 0;
    while (true) {
      const idx = buffer.indexOf("\n\n", consumed);
      if (idx === -1) break;
      const frame = buffer.slice(consumed, idx);
      consumed = idx + 2;
      const lines = frame.split("\n");
      let eventName = "message";
      const dataLines = [];
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (dataLines.length) {
        events.push({ event: eventName, data: dataLines.join("\n") });
      }
    }
    return { events, consumed };
  }

  function finalizeStream(contentEl, doneEvent) {
    contentEl.innerHTML = renderMarkdown(doneEvent.assistant_message || "");
    appendToolInfo(doneEvent.tool_calls, doneEvent.files_written);
    scrollToBottom();
  }

  async function readSSEStream(body, contentEl, messageEl, onDone) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let textBuffer = "";
    let doneEvent = null;
    let collabPanel = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, consumed } = parseSSE(buffer);
      buffer = buffer.slice(consumed);

      for (const ev of events) {
        if (ev.event === "delta") {
          const data = JSON.parse(ev.data);
          textBuffer += data.delta || "";
          contentEl.innerHTML =
            renderMarkdown(textBuffer) + '<span class="streaming-cursor"></span>';
          scrollToBottom();
        } else if (
          ev.event === "engineering_start" ||
          ev.event === "engineering_update" ||
          ev.event === "engineering_complete"
        ) {
          const data = JSON.parse(ev.data);
          appendEngineeringEvent(data.engineering || {});
        } else if (ev.event === "plan") {
          const data = JSON.parse(ev.data);
          if (!collabPanel) {
            collabPanel = createCollaborationPanel(data.plan || {});
            messageEl.insertBefore(collabPanel.wrapper, contentEl.parentElement);
          }
        } else if (ev.event === "task_start") {
          const data = JSON.parse(ev.data);
          if (collabPanel) {
            updateTaskStatus(collabPanel, data.task?.id, "running");
          }
        } else if (ev.event === "task_retry") {
          const data = JSON.parse(ev.data);
          if (collabPanel) {
            updateTaskStatus(collabPanel, data.task?.id, "running");
          }
        } else if (ev.event === "task_complete") {
          const data = JSON.parse(ev.data);
          if (collabPanel) {
            const task = data.task || {};
            updateTaskStatus(
              collabPanel,
              task.id,
              task.success ? "success" : "error",
              task.error,
              task.files_written
            );
          }
        } else if (ev.event === "review_complete") {
          const data = JSON.parse(ev.data);
          if (collabPanel) {
            updateCollaborationReview(collabPanel, data.review || {});
          }
        } else if (ev.event === "permission_request") {
          const data = JSON.parse(ev.data);
          if (data.permission_request) {
            const card = createPermissionCard(data.permission_request);
            messageEl.appendChild(card);
            scrollToBottom();
          }
        } else if (ev.event === "model_failover") {
          const data = JSON.parse(ev.data);
          const failover = data.failover || {};
          const fromModel = failover.from_model || "?";
          const toModel = failover.to_model || "?";
          const reason = failover.reason || "";
          const notice = document.createElement("div");
          notice.className = "failover-notice";
          notice.textContent = `⚠ 模型 ${fromModel} 连接失效（${reason}），已自动切换到 ${toModel}`;
          messageEl.appendChild(notice);
          scrollToBottom();
        } else if (ev.event === "done") {
          doneEvent = JSON.parse(ev.data);
        } else if (ev.event === "error") {
          const data = JSON.parse(ev.data);
          throw new Error(data.error || "流式响应错误");
        }
      }
    }

    // 刷新剩余数据
    buffer += decoder.decode();
    const { events, consumed } = parseSSE(buffer);
    for (const ev of events) {
      if (ev.event === "done") doneEvent = JSON.parse(ev.data);
      else if (
        ev.event === "engineering_start" ||
        ev.event === "engineering_update" ||
        ev.event === "engineering_complete"
      ) {
        const data = JSON.parse(ev.data);
        appendEngineeringEvent(data.engineering || {});
      }
      else if (ev.event === "error") {
        const data = JSON.parse(ev.data);
        throw new Error(data.error || "流式响应错误");
      }
    }

    if (doneEvent) {
      finalizeStream(contentEl, doneEvent);
      onDone(doneEvent);
    }
  }

  async function sendMessage() {
    const text = els.chatInput.value.trim();
    if (!text || !state.currentSessionId || state.isLoading || state.recovery?.required) return;

    appendMessage("user", text);
    els.chatInput.value = "";
    state.isLoading = true;
    showStatus("助手思考中…");
    clearTurnLog();

    const { messageEl, contentEl } = createAssistantPlaceholder();

    try {
      const response = await fetch(
        `/api/chat/sessions/${encodeURIComponent(
          state.currentSessionId
        )}/messages/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败: ${response.status}`);
      }
      if (!response.body) {
        throw new Error("响应体为空");
      }

      await readSSEStream(response.body, contentEl, messageEl, (doneEvent) => {
        hideStatus();
        appendTurnLog(doneEvent.tool_calls, doneEvent.files_written);
      });
      await loadSessions();
      await refreshPlanState();
      await loadDeliveryReport(state.reportScope);
    } catch (err) {
      contentEl.innerHTML = `<span class="error-text">${escapeHtml(err.message)}</span>`;
      showStatus(err.message, true);
    } finally {
      messageEl.classList.remove("streaming");
      state.isLoading = false;
    }
  }

  // 事件绑定
  els.btnSend.addEventListener("click", sendMessage);
  els.btnPlanMode?.addEventListener("click", togglePlanMode);
  els.btnPlanCancel?.addEventListener("click", () => updatePlanState("cancel"));
  els.btnPlanApprove?.addEventListener("click", approvePlanAndImplement);
  els.btnPlanRevise?.addEventListener("click", revisePlan);
  els.btnRecoveryContinue?.addEventListener("click", () => decideRecovery("continue"));
  els.btnRecoveryAbandon?.addEventListener("click", () => decideRecovery("abandon"));
  els.planRevisionInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      revisePlan();
    }
  });
  els.btnToggleRightbar?.addEventListener("click", toggleRightbar);
  els.btnCloseRightbar?.addEventListener("click", () => setRightbarOpen(false));
  els.tabContext?.addEventListener("click", () => setRightbarTab("context"));
  els.tabFiles?.addEventListener("click", () => setRightbarTab("files"));
  els.btnRefreshTree?.addEventListener("click", loadProjectTree);
  els.projectIncludeHidden?.addEventListener("change", loadProjectTree);
  els.projectRootInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      loadProjectTree();
    }
  });
  els.btnClosePreview?.addEventListener("click", hideFilePreview);
  els.chatBackdrop?.addEventListener("click", () => setRightbarOpen(false));
  els.formAddMemory?.addEventListener("submit", addMemoryFromForm);
  els.memorySearch?.addEventListener("input", (e) => searchMemoryFromInput(e.target.value));
  els.btnRefreshMemories?.addEventListener("click", () => loadMemories());
  els.btnRebuildIndex?.addEventListener("click", rebuildProjectIndex);
  els.btnReportSession?.addEventListener("click", () => loadDeliveryReport("session"));
  els.btnReportToday?.addEventListener("click", () => loadDeliveryReport("today"));
  els.turnLog?.addEventListener("click", (event) => {
    const button = event.target.closest(".run-detail-toggle");
    if (button) toggleRunDetail(button.dataset.runId);
  });
  els.btnSummarizeSession?.addEventListener("click", summarizeCurrentSession);
  els.chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    } else if (e.key === "Tab" && e.shiftKey) {
      e.preventDefault();
      const idx = MODES.indexOf(currentMode);
      const nextMode = MODES[(idx + 1) % MODES.length];
      setMode(nextMode);
    }
  });
  els.btnNewSession.addEventListener("click", openNewSessionDialog);
  els.btnCancelSession?.addEventListener("click", closeNewSessionDialog);
  els.btnCancelSessionSecondary?.addEventListener("click", closeNewSessionDialog);
  els.newSessionForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = els.newSessionTitle.value.trim();
    if (!title) return;
    const submitButton = els.newSessionForm.querySelector('[type="submit"]');
    submitButton.disabled = true;
    try {
      await createSession(title);
    } catch (err) {
      showStatus(err.message, true);
    } finally {
      submitButton.disabled = false;
    }
  });

  // 初始化
  updateModeIndicator();
  setRightbarOpen(false);
  setRightbarTab("context");
  try {
    const savedProjectRoot = localStorage.getItem("mao.projectRoot");
    if (savedProjectRoot && els.projectRootInput) els.projectRootInput.value = savedProjectRoot;
  } catch (_) {
    // 本地存储不可用时使用默认目录。
  }
  loadSessions().then(() => {
    if (state.sessions.length > 0) {
      loadSession(state.sessions[0].id);
    } else {
      els.chatMessages.innerHTML =
        '<div class="chat-empty">点击左侧“新建”开始对话</div>';
    }
  });
})();
