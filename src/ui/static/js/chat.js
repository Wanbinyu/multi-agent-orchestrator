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
    chatRightbar: document.getElementById("chat-rightbar"),
    btnToggleRightbar: document.getElementById("btn-toggle-rightbar"),
    btnCloseRightbar: document.getElementById("btn-close-rightbar"),
    chatBackdrop: document.getElementById("chat-backdrop"),
    ctxSessionId: document.getElementById("ctx-session-id"),
    ctxSessionMode: document.getElementById("ctx-session-mode"),
    ctxSessionCreated: document.getElementById("ctx-session-created"),
    ctxSessionUpdated: document.getElementById("ctx-session-updated"),
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
    currentMode = mode;
    updateModeIndicator();
    if (!state.currentSessionId) return;
    try {
      await api(`/api/chat/sessions/${encodeURIComponent(state.currentSessionId)}/mode`, {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
    } catch (err) {
      console.error("切换模式失败", err);
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
    // 简单渲染：把代码块包在 pre/code 中，其余换行转 br
    let html = escapeHtml(text);
    html = html.replace(
      /```(\w*)\n([\s\S]*?)```/g,
      (_, lang, code) =>
        `<pre class="code-block"><code class="language-${escapeHtml(lang)}">${escapeHtml(code)}</code></pre>`
    );
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\n/g, "<br>");
    return html;
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
    await loadMemories();
    await loadIndexStatus();
    clearTurnLog();
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
    if (existing >= 0) state.turnLog.engineering[existing] = engineering;
    else state.turnLog.engineering.push(engineering);
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
      html += `
        <div class="turn-log-item engineering-run ${escapeHtml(run.status || "running")}">
          <div class="turn-log-title">${icon} 工程记录 · ${escapeHtml(labels[run.status] || run.status)}</div>
          <div class="turn-log-detail">${escapeHtml(run.run_id)}</div>
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
    if (!text || !state.currentSessionId || state.isLoading) return;

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
