(function () {
  "use strict";

  const state = {
    config: { providers: {}, models: {}, main_model: null },
    presets: [],
    currentPreset: null,
    editingProvider: null,
  };

  // DOM 元素
  const els = {
    providerList: document.getElementById("provider-list"),
    modelPool: document.getElementById("model-pool"),
    mainModelSelect: document.getElementById("main-model-select"),
    presetSelect: document.getElementById("preset-select"),
    providerName: document.getElementById("provider-name"),
    displayName: document.getElementById("display-name"),
    baseUrl: document.getElementById("base-url"),
    apiKey: document.getElementById("api-key"),
    timeout: document.getElementById("timeout"),
    modelRows: document.getElementById("model-rows"),
    setAsMain: document.getElementById("set-as-main"),
    form: document.getElementById("provider-form"),
    formTitle: document.getElementById("form-title"),
    btnAddProvider: document.getElementById("btn-add-provider"),
    btnAddModel: document.getElementById("btn-add-model"),
    btnTest: document.getElementById("btn-test"),
    btnDelete: document.getElementById("btn-delete"),
    btnSaveMain: document.getElementById("btn-save-main"),
    testResult: document.getElementById("test-result"),
  };

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

  async function loadConfig() {
    state.config = await api("/api/config");
    renderProviderList();
    renderModelPool();
  }

  async function loadPresets() {
    const data = await api("/api/presets");
    state.presets = data.presets || [];
    els.presetSelect.innerHTML = state.presets
      .map((p) => `<option value="${p.key}">${escapeHtml(p.name)}</option>`)
      .join("");
    await applyPreset(state.presets[0]?.key);
  }

  async function applyPreset(key) {
    if (!key) return;
    const data = await api(`/api/presets/${key}`);
    state.currentPreset = data.preset;
    els.presetSelect.value = key;
    if (!state.editingProvider) {
      els.providerName.value = data.default_provider_name;
      els.displayName.value = data.preset.name;
      els.baseUrl.value = data.preset.base_url || "";
      renderModelRowsFromPreset(data.default_models || []);
    }
  }

  function providerStatus(p) {
    if (p.test_status?.success) return { cls: "status-success", text: "已连通" };
    if (p.has_key) return { cls: "status-pending", text: "待测试" };
    return { cls: "status-empty", text: "未配置 Key" };
  }

  function formatTestedAt(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString("zh-CN", { hour12: false });
  }

  function renderProviderList() {
    els.providerList.innerHTML = "";
    const names = Object.keys(state.config.providers || {});
    if (names.length === 0) {
      els.providerList.innerHTML =
        '<li class="provider-item empty" style="cursor:default"><span class="meta">暂无 Provider，点击右上角添加</span></li>';
      return;
    }
    names.forEach((name) => {
      const p = state.config.providers[name];
      const status = providerStatus(p);
      const isActive = state.editingProvider === name;
      const li = document.createElement("li");
      li.className = "provider-item" + (isActive ? " active" : "");
      li.dataset.name = name;
      li.innerHTML = `
        <div class="provider-row">
          <span class="status-dot ${status.cls}" title="${escapeHtml(
            status.text
          )}"></span>
          <div class="provider-info">
            <div class="name">${escapeHtml(name)}</div>
            <div class="meta">${escapeHtml(p.name)} · ${escapeHtml(p.type)}</div>
          </div>
          <label class="switch" title="启用/禁用">
            <input type="checkbox" class="toggle-enabled" ${p.enabled !== false ? "checked" : ""}>
            <span class="slider"></span>
          </label>
        </div>
        ${p.test_status
          ? `<div class="test-meta">上次测试: ${p.test_status.success ? "✅ 成功" : "❌ 失败"} · ${formatTestedAt(p.test_status.tested_at)}</div>`
          : ""}
      `;

      // 切换启用状态
      const toggle = li.querySelector(".toggle-enabled");
      toggle.addEventListener("change", (e) => {
        e.stopPropagation();
        toggleProvider(name, e.target.checked);
      });

      // 点击卡片进入编辑
      li.addEventListener("click", (e) => {
        if (e.target.closest(".switch")) return;
        editProvider(name);
      });

      els.providerList.appendChild(li);
    });
  }

  function enabledProviders() {
    return Object.entries(state.config.providers || {})
      .filter(([, p]) => p.enabled !== false)
      .map(([name]) => name);
  }

  function enabledModels() {
    const providers = new Set(enabledProviders());
    return Object.entries(state.config.models || {})
      .filter(([, data]) => providers.has(data.provider))
      .map(([alias, data]) => ({ alias, ...data }));
  }

  function renderModelPool() {
    const models = enabledModels();
    const aliases = models.map((m) => m.alias);

    els.mainModelSelect.innerHTML = aliases
      .map(
        (a) =>
          `<option value="${escapeHtml(a)}" ${a === state.config.main_model ? "selected" : ""}>` +
          `${escapeHtml(a)}</option>`
      )
      .join("");

    if (aliases.length === 0) {
      els.modelPool.innerHTML =
        '<span class="model-tag">暂无可用模型，请添加并启用 Provider</span>';
      return;
    }

    els.modelPool.innerHTML = models
      .map((m) => {
        const isMain = m.alias === state.config.main_model;
        return `<span class="model-tag ${isMain ? "main" : ""}" title="${escapeHtml(
          m.model_id
        )} · ${escapeHtml(m.provider)}">${isMain ? "⭐ " : ""}${escapeHtml(
          m.alias
        )}</span>`;
      })
      .join("");
  }

  function renderModelRowsFromPreset(models) {
    els.modelRows.innerHTML = "";
    models.forEach((m) => addModelRow(m));
    if (els.modelRows.children.length === 0) {
      addModelRow();
    }
  }

  function addModelRow(model = null) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td data-label="逻辑别名"><input type="text" class="model-alias" value="${escapeHtml(
        model?.alias || ""
      )}" placeholder="glm-ark" required></td>
      <td data-label="上游 model_id"><input type="text" class="model-id" value="${escapeHtml(
        model?.model_id || ""
      )}" placeholder="上游真实 model_id" required></td>
      <td data-label="输入价格 / 1M"><input type="number" class="model-input-price" value="${model?.input_price_per_1m ?? 0}" min="0" step="0.01"></td>
      <td data-label="输出价格 / 1M"><input type="number" class="model-output-price" value="${model?.output_price_per_1m ?? 0}" min="0" step="0.01"></td>
      <td data-label="能力标签"><input type="text" class="model-caps" value="${escapeHtml(
        (model?.capabilities || []).join(", ")
      )}" placeholder="coding, tool_use"></td>
      <td class="model-row-actions"><button type="button" class="btn btn-danger btn-sm btn-remove-model">删除</button></td>
    `;
    tr.querySelector(".btn-remove-model").addEventListener("click", () => tr.remove());
    els.modelRows.appendChild(tr);
  }

  function collectModels() {
    const models = [];
    for (const row of els.modelRows.querySelectorAll("tr")) {
      const alias = row.querySelector(".model-alias").value.trim();
      const modelId = row.querySelector(".model-id").value.trim();
      if (!alias || !modelId) continue;
      models.push({
        alias,
        model_id: modelId,
        input_price_per_1m: parseFloat(row.querySelector(".model-input-price").value) || 0,
        output_price_per_1m: parseFloat(row.querySelector(".model-output-price").value) || 0,
        capabilities: row
          .querySelector(".model-caps")
          .value.split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
    }
    return models;
  }

  function editProvider(name) {
    state.editingProvider = name;
    const p = state.config.providers[name];
    const preset = state.presets.find((x) => x.name === p.name) || state.presets[0];
    els.formTitle.textContent = `编辑 Provider: ${name}`;
    els.providerName.value = name;
    els.providerName.disabled = true;
    els.displayName.value = p.name;
    els.baseUrl.value = p.base_url;
    els.timeout.value = p.timeout || 120;
    els.apiKey.value = "";
    els.apiKey.placeholder = "已保存，留空则保持不变";
    els.apiKey.required = false;
    els.setAsMain.checked = false;
    els.btnDelete.disabled = false;
    els.presetSelect.value = preset?.key || "";

    const owned = Object.entries(state.config.models || {})
      .filter(([, data]) => data.provider === name)
      .map(([alias, data]) => ({
        alias,
        model_id: data.model_id,
        input_price_per_1m: data.input_price_per_1m,
        output_price_per_1m: data.output_price_per_1m,
        capabilities: data.capabilities || [],
      }));
    renderModelRowsFromPreset(owned);
    renderProviderList();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function resetForm() {
    state.editingProvider = null;
    els.form.reset();
    els.providerName.disabled = false;
    els.btnDelete.disabled = true;
    els.formTitle.textContent = "添加 Provider";
    els.testResult.classList.add("hidden");
    els.apiKey.placeholder = "sk-...";
    els.apiKey.required = true;
    applyPreset(els.presetSelect.value);
    renderProviderList();
  }

  async function saveProvider(ev) {
    ev.preventDefault();
    const models = collectModels();
    if (models.length === 0) {
      showResult("请至少配置一个模型", false);
      return;
    }

    const payload = {
      preset_key: els.presetSelect.value,
      provider_name: els.providerName.value.trim(),
      display_name: els.displayName.value.trim(),
      base_url: els.baseUrl.value.trim(),
      api_key: els.apiKey.value.trim(),
      timeout: parseInt(els.timeout.value, 10) || 120,
      models,
      enabled: true,
      set_as_main: els.setAsMain.checked,
    };

    try {
      await api("/api/config/providers", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showResult("保存成功", true);
      resetForm();
      await loadConfig();
    } catch (err) {
      showResult(err.message, false);
    }
  }

  async function testConnection() {
    const models = collectModels();
    if (models.length === 0) {
      showResult("请至少配置一个模型用于测试", false);
      return;
    }
    const preset = state.currentPreset;
    const name = els.providerName.value.trim() || "new";
    const payload = {
      provider_type: preset?.type || "openai",
      base_url: els.baseUrl.value.trim(),
      api_key: els.apiKey.value.trim(),
      model_id: models[0].model_id,
      timeout: 30,
    };
    showResult("正在测试连接...", true, true);
    try {
      const res = await api(`/api/config/providers/${encodeURIComponent(name)}/test`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (res.success) {
        showResult(`✅ 连接成功 · ${res.response_time_ms}ms`, true);
      } else {
        showResult(`❌ 连接失败：${res.error_message}`, false);
      }
      await loadConfig();
    } catch (err) {
      showResult(err.message, false);
    }
  }

  async function toggleProvider(name, enabled) {
    try {
      await api(`/api/config/providers/${encodeURIComponent(name)}/enabled`, {
        method: "POST",
        body: JSON.stringify({ enabled }),
      });
      await loadConfig();
    } catch (err) {
      alert(err.message);
      await loadConfig();
    }
  }

  async function deleteProvider() {
    const name = state.editingProvider;
    if (!name) return;
    if (!confirm(`确定删除 Provider "${name}" 吗？`)) return;
    try {
      await api(`/api/config/providers/${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
      resetForm();
      await loadConfig();
    } catch (err) {
      showResult(err.message, false);
    }
  }

  async function saveMainModel() {
    const alias = els.mainModelSelect.value;
    if (!alias) return;
    try {
      await api("/api/config/main_model", {
        method: "POST",
        body: JSON.stringify({ alias }),
      });
      await loadConfig();
    } catch (err) {
      alert(err.message);
    }
  }

  function showResult(message, success, pending = false) {
    els.testResult.textContent = message;
    els.testResult.classList.remove("hidden", "success", "error");
    if (pending) els.testResult.classList.add("success");
    else els.testResult.classList.add(success ? "success" : "error");
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

  // 事件绑定
  els.presetSelect.addEventListener("change", (e) => applyPreset(e.target.value));
  els.btnAddProvider.addEventListener("click", resetForm);
  els.btnAddModel.addEventListener("click", () => addModelRow());
  els.form.addEventListener("submit", saveProvider);
  els.btnTest.addEventListener("click", testConnection);
  els.btnDelete.addEventListener("click", deleteProvider);
  els.btnSaveMain.addEventListener("click", saveMainModel);

  // 初始化
  loadPresets().then(loadConfig);
})();
