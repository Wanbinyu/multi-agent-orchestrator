(function () {
  "use strict";

  // 用户不可见：窗口/预算由系统托管，避免误填把输入预算算成 0
  const SAFE_BUDGET = {
    context_window_tokens: 0, // 0 → 运行时默认安全预算（当前 200K）
    max_output_tokens: 8192,
    context_safety_ratio: 0.08,
    compaction_threshold: 0.75,
    context_window_source: "unverified",
    context_window_verified_at: "",
  };

  const state = {
    config: { providers: {}, models: {}, main_model: null },
    presets: [],
    catalog: [],
    catalogByAlias: {},
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
    modelTable: document.getElementById("model-table"),
    setAsMain: document.getElementById("set-as-main"),
    form: document.getElementById("provider-form"),
    formTitle: document.getElementById("form-title"),
    btnAddProvider: document.getElementById("btn-add-provider"),
    btnAddModel: document.getElementById("btn-add-model"),
    btnApplyPresetModels: document.getElementById("btn-apply-preset-models"),
    catalogPick: document.getElementById("catalog-pick"),
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
      const detail = data.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : `请求失败: ${res.status}`;
      throw new Error(msg);
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

  async function loadCatalog() {
    try {
      const data = await api("/api/catalog/models");
      state.catalog = data.models || [];
      state.catalogByAlias = {};
      state.catalog.forEach((m) => {
        state.catalogByAlias[m.alias] = m;
      });
      fillCatalogPick();
    } catch (err) {
      console.warn("加载模型目录失败", err);
      state.catalog = [];
      state.catalogByAlias = {};
    }
  }

  function fillCatalogPick() {
    if (!els.catalogPick) return;
    const opts = ['<option value="">从目录添加…</option>'];
    const type = state.currentPreset?.type;
    const list = type
      ? state.catalog.filter((m) => m.provider_type === type)
      : state.catalog;
    // 若按协议过滤后为空，仍展示全部
    const source = list.length ? list : state.catalog;
    source.forEach((m) => {
      opts.push(
        `<option value="${escapeHtml(m.alias)}">${escapeHtml(m.alias)} · ${escapeHtml(
          m.name
        )}</option>`
      );
    });
    els.catalogPick.innerHTML = opts.join("");
  }

  async function applyPreset(key) {
    if (!key) return;
    const data = await api(`/api/presets/${key}`);
    state.currentPreset = data.preset;
    els.presetSelect.value = key;
    fillCatalogPick();
    if (!state.editingProvider) {
      els.providerName.value = data.default_provider_name;
      els.displayName.value = data.preset.name;
      els.baseUrl.value = data.preset.base_url || "";
      renderModelRowsFromPreset(data.default_models || []);
    }
  }

  async function applyPresetModelsOnly() {
    const key = els.presetSelect.value;
    if (!key) return;
    if (
      els.modelRows.children.length > 0 &&
      !confirm("用当前预设的推荐模型列表覆盖下方表格？")
    ) {
      return;
    }
    const data = await api(`/api/presets/${key}`);
    state.currentPreset = data.preset;
    renderModelRowsFromPreset(data.default_models || []);
    showResult("已填入预设推荐模型（含目录默认预算字段）", true);
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

  function modelsForProvider(providerName) {
    return Object.entries(state.config.models || {})
      .filter(([, data]) => data.provider === providerName)
      .map(([alias, data]) => ({ alias, ...data }));
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
      const owned = modelsForProvider(name);
      const li = document.createElement("li");
      li.className = "provider-item" + (isActive ? " active" : "");
      li.dataset.name = name;

      const chips = owned
        .map((m) => {
          const isMain = m.alias === state.config.main_model;
          return (
            `<span class="provider-model-chip ${isMain ? "main" : ""}" title="${escapeHtml(
              m.model_id || ""
            )}">` +
            `<button type="button" class="chip-alias" data-alias="${escapeHtml(
              m.alias
            )}">${isMain ? "⭐ " : ""}${escapeHtml(m.alias)}</button>` +
            `<button type="button" class="chip-del" data-alias="${escapeHtml(
              m.alias
            )}" title="删除模型">×</button>` +
            `</span>`
          );
        })
        .join("");

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
        ${
          owned.length
            ? `<div class="provider-model-chips">${chips}</div>`
            : `<div class="provider-model-chips empty-chips">无模型</div>`
        }
        ${
          p.test_status
            ? `<div class="test-meta">上次测试: ${
                p.test_status.success ? "✅ 成功" : "❌ 失败"
              } · ${formatTestedAt(p.test_status.tested_at)}</div>`
            : ""
        }
      `;

      const toggle = li.querySelector(".toggle-enabled");
      toggle.addEventListener("change", (e) => {
        e.stopPropagation();
        toggleProvider(name, e.target.checked);
      });

      li.querySelectorAll(".chip-del").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          deleteModel(btn.dataset.alias);
        });
      });

      li.querySelectorAll(".chip-alias").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          editProvider(name);
        });
      });

      li.addEventListener("click", (e) => {
        if (e.target.closest(".switch")) return;
        if (e.target.closest(".chip-del")) return;
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
          `<option value="${escapeHtml(a)}" ${
            a === state.config.main_model ? "selected" : ""
          }>` + `${escapeHtml(a)}</option>`
      )
      .join("");

    if (aliases.length === 0) {
      els.modelPool.innerHTML =
        '<span class="model-tag">暂无可用模型，请添加并启用 Provider</span>';
      return;
    }

    els.modelPool.innerHTML = "";
    models.forEach((m) => {
      const isMain = m.alias === state.config.main_model;
      const tag = document.createElement("span");
      tag.className = "model-tag" + (isMain ? " main" : "");
      tag.title = `${m.model_id || ""} · ${m.provider || ""}`;
      tag.innerHTML =
        `<span class="tag-label">${isMain ? "⭐ " : ""}${escapeHtml(m.alias)}</span>` +
        `<button type="button" class="tag-del" title="删除模型" aria-label="删除 ${escapeHtml(
          m.alias
        )}">×</button>`;
      tag.querySelector(".tag-del").addEventListener("click", (e) => {
        e.stopPropagation();
        deleteModel(m.alias);
      });
      tag.querySelector(".tag-label").addEventListener("click", () => {
        if (m.provider) editProvider(m.provider);
      });
      els.modelPool.appendChild(tag);
    });
  }

  function renderModelRowsFromPreset(models) {
    els.modelRows.innerHTML = "";
    models.forEach((m) => addModelRow(m));
    if (els.modelRows.children.length === 0) {
      addModelRow();
    }
  }

  function catalogDefaults(alias) {
    return state.catalogByAlias[alias] || null;
  }

  function safeBudgetFields() {
    return { ...SAFE_BUDGET };
  }

  function addModelRow(model = null) {
    const tr = document.createElement("tr");
    const cat = model?.alias ? catalogDefaults(model.alias) : null;
    const merged = mergeWithCatalog(model, cat);

    tr.dataset.dynamicAlias = merged.dynamic_model_alias ? "true" : "false";
    tr.dataset.capabilityStatus = JSON.stringify(merged.capability_status || {});
    tr.dataset.metadataSource = merged.metadata_source || "unverified";
    tr.dataset.metadataVerifiedAt = merged.metadata_verified_at || "";

    tr.innerHTML = `
      <td data-label="逻辑别名"><input type="text" class="model-alias" list="catalog-alias-list" value="${escapeHtml(
        merged.alias || ""
      )}" placeholder="如 deepseek-v4-pro" required></td>
      <td data-label="上游 model_id"><input type="text" class="model-id" value="${escapeHtml(
        merged.model_id || ""
      )}" placeholder="上游真实 model_id" required></td>
      <td data-label="输入价格 / 1M"><input type="number" class="model-input-price" value="${
        merged.input_price_per_1m ?? 0
      }" min="0" step="0.01"></td>
      <td data-label="输出价格 / 1M"><input type="number" class="model-output-price" value="${
        merged.output_price_per_1m ?? 0
      }" min="0" step="0.01"></td>
      <td data-label="能力标签"><input type="text" class="model-caps" value="${escapeHtml(
        (merged.capabilities || []).join(", ")
      )}" placeholder="coding, tool_use"></td>
      <td class="model-row-actions">
        <button type="button" class="btn btn-sm btn-autofill-row" title="按内置目录填充别名与 model_id">目录默认</button>
        <button type="button" class="btn btn-danger btn-sm btn-remove-model">删除</button>
      </td>
    `;

    ensureCatalogDatalist();

    const aliasInput = tr.querySelector(".model-alias");
    aliasInput.addEventListener("change", () => tryAutofillRow(tr, { force: false }));
    aliasInput.addEventListener("blur", () => tryAutofillRow(tr, { force: false }));
    tr.querySelector(".btn-autofill-row").addEventListener("click", () =>
      tryAutofillRow(tr, { force: true })
    );
    tr.querySelector(".btn-remove-model").addEventListener("click", () => tr.remove());
    els.modelRows.appendChild(tr);
  }

  function ensureCatalogDatalist() {
    let list = document.getElementById("catalog-alias-list");
    if (!list) {
      list = document.createElement("datalist");
      list.id = "catalog-alias-list";
      document.body.appendChild(list);
    }
    list.innerHTML = state.catalog
      .map((m) => `<option value="${escapeHtml(m.alias)}">${escapeHtml(m.name)}</option>`)
      .join("");
  }

  function mergeWithCatalog(model, cat) {
    const budget = safeBudgetFields();
    if (
      cat &&
      (cat.context_window_tokens || 0) >= 16000 &&
      cat.metadata_source &&
      !String(cat.metadata_source).includes("unverified")
    ) {
      budget.context_window_tokens = cat.context_window_tokens;
      budget.context_window_source = cat.context_window_source || "catalog";
      budget.context_window_verified_at = cat.context_window_verified_at || "";
    }
    if (cat && (cat.max_output_tokens || 0) >= 8192) {
      budget.max_output_tokens = cat.max_output_tokens;
    }
    return {
      alias: model?.alias || cat?.alias || "",
      model_id: model?.model_id || cat?.model_id || "",
      input_price_per_1m: model?.input_price_per_1m ?? cat?.input_price_per_1m ?? 0,
      output_price_per_1m: model?.output_price_per_1m ?? cat?.output_price_per_1m ?? 0,
      capabilities: model?.capabilities || cat?.capabilities || [],
      capability_status: model?.capability_status || cat?.capability_status || {},
      metadata_source: model?.metadata_source || cat?.metadata_source || "unverified",
      metadata_verified_at:
        model?.metadata_verified_at || cat?.metadata_verified_at || "",
      dynamic_model_alias:
        model?.dynamic_model_alias === true || cat?.dynamic_model_alias === true,
      ...budget,
    };
  }

  function tryAutofillRow(tr, { force }) {
    const alias = tr.querySelector(".model-alias").value.trim();
    const cat = catalogDefaults(alias);
    if (!cat) {
      if (force) {
        showResult(
          `别名「${alias || "?"}」不在内置目录；预算仍由系统自动管理`,
          true
        );
      }
      return;
    }

    const idInput = tr.querySelector(".model-id");
    const priceIn = tr.querySelector(".model-input-price");
    const priceOut = tr.querySelector(".model-output-price");
    const caps = tr.querySelector(".model-caps");

    if (force || !idInput.value.trim()) idInput.value = cat.model_id || "";
    if (force || Number(priceIn.value) === 0)
      priceIn.value = cat.input_price_per_1m ?? 0;
    if (force || Number(priceOut.value) === 0)
      priceOut.value = cat.output_price_per_1m ?? 0;
    if (force || !caps.value.trim())
      caps.value = (cat.capabilities || []).join(", ");

    tr.dataset.dynamicAlias = cat.dynamic_model_alias ? "true" : "false";
    tr.dataset.capabilityStatus = JSON.stringify(cat.capability_status || {});
    tr.dataset.metadataSource = cat.metadata_source || "unverified";
    tr.dataset.metadataVerifiedAt = cat.metadata_verified_at || "";

    if (force) {
      showResult(`已按目录填充「${alias}」的别名/model_id/价格（预算自动）`, true);
    }
  }

  function collectModels() {
    const models = [];
    const budget = safeBudgetFields();
    for (const row of els.modelRows.querySelectorAll("tr")) {
      const alias = row.querySelector(".model-alias").value.trim();
      const modelId = row.querySelector(".model-id").value.trim();
      if (!alias || !modelId) continue;
      models.push({
        alias,
        model_id: modelId,
        input_price_per_1m:
          parseFloat(row.querySelector(".model-input-price").value) || 0,
        output_price_per_1m:
          parseFloat(row.querySelector(".model-output-price").value) || 0,
        capabilities: row
          .querySelector(".model-caps")
          .value.split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        capability_status: JSON.parse(row.dataset.capabilityStatus || "{}"),
        metadata_source: row.dataset.metadataSource || "unverified",
        metadata_verified_at: row.dataset.metadataVerifiedAt || "",
        dynamic_model_alias: row.dataset.dynamicAlias === "true",
        ...budget,
      });
    }
    return models;
  }

  function editProvider(name) {
    state.editingProvider = name;
    const p = state.config.providers[name];
    const preset =
      state.presets.find((x) => x.name === p.name) ||
      state.presets.find((x) => x.type === p.type) ||
      state.presets[0];
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
    if (preset) {
      els.presetSelect.value = preset.key;
      state.currentPreset = state.currentPreset || { type: p.type, name: p.name };
    }
    fillCatalogPick();

    const owned = modelsForProvider(name).map((data) => ({
      alias: data.alias,
      model_id: data.model_id,
      input_price_per_1m: data.input_price_per_1m,
      output_price_per_1m: data.output_price_per_1m,
      capabilities: data.capabilities || [],
      capability_status: data.capability_status || {},
      metadata_source: data.metadata_source || "unverified",
      metadata_verified_at: data.metadata_verified_at || "",
      dynamic_model_alias: data.dynamic_model_alias === true,
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
      showResult("请至少配置一个模型（可用「一键预设模型」或「从目录添加」）", false);
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
      const res = await api(
        `/api/config/providers/${encodeURIComponent(name)}/test`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      if (res.success) {
        showResult(`✅ 连接成功 · ${res.response_time_ms}ms`, true);
      } else {
        const code = res.error_code ? `[${res.error_code}] ` : "";
        const action = res.action ? `；建议：${res.action}` : "";
        showResult(`❌ 连接失败：${code}${res.error_message}${action}`, false);
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
    if (!confirm(`确定删除 Provider "${name}" 及其全部模型吗？`)) return;
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

  async function deleteModel(alias) {
    if (!alias) return;
    if (
      !confirm(
        `确定删除模型「${alias}」吗？\n不会删除所属 Provider；若它是主模型会自动改派。`
      )
    ) {
      return;
    }
    try {
      const res = await api(`/api/config/models/${encodeURIComponent(alias)}`, {
        method: "DELETE",
      });
      if (state.editingProvider) {
        // 若正在编辑该 Provider，从表格去掉该行
        for (const tr of [...els.modelRows.querySelectorAll("tr")]) {
          if (tr.querySelector(".model-alias")?.value.trim() === alias) {
            tr.remove();
          }
        }
      }
      await loadConfig();
      if (state.editingProvider) {
        const still = modelsForProvider(state.editingProvider);
        if (still.length === 0) {
          showResult(`已删除 ${alias}；该 Provider 下已无模型，请添加后保存`, true);
        } else {
          showResult(
            `已删除 ${alias}` +
              (res.main_model ? `；主模型现为 ${res.main_model}` : ""),
            true
          );
        }
      } else {
        showResult(`已删除模型 ${alias}`, true);
      }
    } catch (err) {
      alert(err.message);
      await loadConfig();
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

  function onCatalogPick() {
    const alias = els.catalogPick.value;
    if (!alias) return;
    const cat = catalogDefaults(alias);
    if (!cat) return;
    addModelRow({
      alias: cat.alias,
      model_id: cat.model_id,
      input_price_per_1m: cat.input_price_per_1m,
      output_price_per_1m: cat.output_price_per_1m,
      capabilities: cat.capabilities,
      capability_status: cat.capability_status,
      metadata_source: cat.metadata_source,
      metadata_verified_at: cat.metadata_verified_at,
      dynamic_model_alias: cat.dynamic_model_alias,
    });
    els.catalogPick.value = "";
    showResult(`已添加目录模型「${alias}」`, true);
  }

  // 事件绑定
  els.presetSelect.addEventListener("change", (e) => applyPreset(e.target.value));
  els.btnAddProvider.addEventListener("click", resetForm);
  els.btnAddModel.addEventListener("click", () => addModelRow());
  if (els.btnApplyPresetModels) {
    els.btnApplyPresetModels.addEventListener("click", () => applyPresetModelsOnly());
  }
  if (els.catalogPick) {
    els.catalogPick.addEventListener("change", onCatalogPick);
  }
  els.form.addEventListener("submit", saveProvider);
  els.btnTest.addEventListener("click", testConnection);
  els.btnDelete.addEventListener("click", deleteProvider);
  els.btnSaveMain.addEventListener("click", saveMainModel);

  // 初始化
  Promise.all([loadPresets(), loadCatalog()]).then(loadConfig);
})();
