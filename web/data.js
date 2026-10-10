const tableLabels = {
  nutrition: '食材营养',
  recipes: '食谱',
  eat_out: '外食条目',
  aliases: '食材别名',
  units: '单位换算',
  goal_rules: '目标规则',
  substitutions: '替换规则',
  target_ingredients: '目标食材'
};

const coreTables = ['nutrition', 'recipes', 'eat_out', 'aliases', 'units'];
const serviceState = document.getElementById('serviceState');
const datasetCounts = document.getElementById('datasetCounts');
const schemaRows = document.getElementById('schemaRows');
const refreshSchemaButton = document.getElementById('refreshSchema');
const regenButton = document.getElementById('regenButton');
const maintenanceResult = document.getElementById('maintenanceResult');

const nutritionForm = document.getElementById('nutritionForm');
const nutritionResult = document.getElementById('nutritionResult');
const recipeForm = document.getElementById('recipeForm');
const recipeResult = document.getElementById('recipeResult');
const recipePreviewButton = document.getElementById('recipePreview');
const eatOutForm = document.getElementById('eatOutForm');
const eatOutResult = document.getElementById('eatOutResult');
const aliasForm = document.getElementById('aliasForm');
const aliasResult = document.getElementById('aliasResult');
const unitForm = document.getElementById('unitForm');
const unitResult = document.getElementById('unitResult');
const batchForm = document.getElementById('batchForm');
const batchResult = document.getElementById('batchResult');

const state = { schema: null, activeTab: 'nutrition' };

const esc = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

function pretty(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? '');
  }
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? '');
  return Number.isInteger(number) ? String(number) : number.toFixed(1).replace(/\.0$/, '');
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join('、');
  if (value && typeof value === 'object') return pretty(value);
  return String(value ?? '');
}

function errorMessage(data, status) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || pretty(item)).join('；');
  }
  return data?.message
    || data?.error?.message
    || (typeof data?.error === 'string' ? data.error : '')
    || `请求失败（HTTP ${status}）`;
}

async function apiRequest(path, options = {}) {
  const init = { method: options.method || 'GET', headers: {} };
  if (Object.prototype.hasOwnProperty.call(options, 'payload')) {
    init.method = options.method || 'POST';
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.payload ?? {});
  }

  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false) {
    throw new Error(errorMessage(data, response.status));
  }
  return data;
}

function resultSummary(result) {
  const items = [];
  const row = result?.row || {};

  if (result?.action) items.push(['操作', result.action]);
  if (result?.table) items.push(['数据表', tableLabels[result.table] || result.table]);
  if (row?.id) items.push(['记录 ID', row.id]);
  if (result?.created !== undefined) items.push(['新增', result.created]);
  if (result?.total !== undefined) items.push(['总数', result.total]);
  if (result?.ok !== undefined && result?.total !== undefined) items.push(['成功', result.ok]);
  if (result?.failed !== undefined && result?.total !== undefined) items.push(['失败', result.failed]);

  if (result?.nutrition) {
    items.push(['热量', `${formatNumber(result.nutrition.calories)} kcal`]);
    items.push(['蛋白质', `${formatNumber(result.nutrition.protein_g)} g`]);
    items.push(['脂肪', `${formatNumber(result.nutrition.fat_g)} g`]);
    items.push(['碳水', `${formatNumber(result.nutrition.carbs_g)} g`]);
  }

  if (result?.serving_weight_g !== undefined) {
    items.push(['每份重量', `${formatNumber(result.serving_weight_g)} g`]);
  }

  if (result?.goal_fit?.passed !== undefined) {
    const passed = result.goal_fit.passed ? '通过' : '未通过';
    const reasons = result.goal_fit.reasons?.length
      ? `：${result.goal_fit.reasons.join('；')}`
      : '';
    items.push(['目标区间', `${passed}${reasons}`]);
  }

  if (Array.isArray(result?.warnings) && result.warnings.length) {
    items.push(['提醒', result.warnings.join('；')]);
  }

  if (result?.hint) items.push(['下一步', result.hint]);
  return items;
}

function renderResult(container, title, result, tone = 'success') {
  if (!container) return;
  const isError = tone === 'error';
  container.hidden = false;
  container.classList.toggle('is-error', isError);

  if (isError) {
    const message = result instanceof Error ? result.message : formatValue(result);
    container.innerHTML = `
      <div class="api-result-head"><strong>${esc(title)}</strong></div>
      <p>${esc(message)}</p>
    `;
    return;
  }

  const items = resultSummary(result);
  const summary = items.length
    ? `<div class="result-summary-grid">${items.map(([label, value]) => `
        <div class="result-summary-item">
          <span>${esc(label)}</span>
          <strong>${esc(formatValue(value))}</strong>
        </div>`).join('')}</div>`
    : '<p>操作已完成。</p>';

  container.innerHTML = `
    <div class="api-result-head"><strong>${esc(title)}</strong></div>
    ${summary}
    <details>
      <summary>查看接口返回</summary>
      <pre>${esc(pretty(result))}</pre>
    </details>
  `;
}

function readForm(form) {
  const payload = {};
  for (const field of form.elements) {
    if (!field.name || field.disabled) continue;

    if (field.type === 'checkbox') {
      if (!field.checked) continue;
      if (field.dataset.multi === 'true') {
        if (!Array.isArray(payload[field.name])) payload[field.name] = [];
        payload[field.name].push(field.value);
      } else {
        payload[field.name] = true;
      }
      continue;
    }

    const value = field.value.trim();
    if (value !== '') payload[field.name] = value;
  }
  return payload;
}

function setButtonBusy(button, busy, busyText) {
  if (!button) return;
  if (busy) {
    if (!button.dataset.idleText) button.dataset.idleText = button.textContent;
    button.textContent = busyText || '处理中…';
    button.disabled = true;
  } else {
    button.textContent = button.dataset.idleText || button.textContent;
    button.disabled = false;
  }
}

async function runRequest({
  button,
  endpoint,
  payload,
  resultElement,
  title,
  successTitle,
  busyText,
  confirmText,
  refreshSchemaAfter = false
}) {
  if (confirmText && !window.confirm(confirmText)) return false;
  setButtonBusy(button, true, busyText);
  try {
    const data = await apiRequest(endpoint, { method: 'POST', payload });
    renderResult(resultElement, successTitle || title, data.result || data, 'success');
    if (refreshSchemaAfter) await loadSchema({ quiet: true });
    return true;
  } catch (error) {
    renderResult(resultElement, title, error, 'error');
    return false;
  } finally {
    setButtonBusy(button, false);
  }
}

async function submitForm({ form, button, endpoint, resultElement, title, successTitle, busyText, confirmText, refreshSchemaAfter = true }) {
  if (!form.reportValidity()) return false;
  return runRequest({
    button,
    endpoint,
    payload: readForm(form),
    resultElement,
    title,
    successTitle,
    busyText,
    confirmText,
    refreshSchemaAfter
  });
}

function renderSchema() {
  if (!state.schema) return;

  datasetCounts.innerHTML = coreTables.map((table) => {
    const info = state.schema[table];
    return `
      <div class="count-item">
        <span>${esc(tableLabels[table] || table)}</span>
        <strong>${esc(info?.rows ?? '—')}</strong>
      </div>
    `;
  }).join('');

  schemaRows.innerHTML = Object.entries(state.schema).map(([table, info]) => `
    <tr>
      <td>${esc(tableLabels[table] || table)}<br><small>${esc(table)}</small></td>
      <td><code>${esc(info.file || '')}</code></td>
      <td>${esc(info.rows ?? 0)}</td>
      <td><code>${esc((info.columns || []).join(', '))}</code></td>
    </tr>
  `).join('');
}

function setServiceState(online, text) {
  serviceState.classList.toggle('is-online', online);
  serviceState.classList.toggle('is-offline', !online);
  serviceState.innerHTML = `<span class="state-dot" aria-hidden="true"></span><span>${esc(text)}</span>`;
}

async function loadSchema({ quiet = false } = {}) {
  try {
    const data = await apiRequest('/data/schema');
    state.schema = data.result;
    renderSchema();
    const tableCount = Object.keys(state.schema || {}).length;
    setServiceState(true, `数据服务已连接 · ${tableCount} 张表`);
    return true;
  } catch (error) {
    setServiceState(false, '数据服务未就绪');
    if (!quiet) renderResult(maintenanceResult, '数据概览读取失败', error, 'error');
    return false;
  }
}

function selectTab(name) {
  state.activeTab = name;
  document.querySelectorAll('[data-tab]').forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.hidden = panel.id !== `panel-${name}`;
  });
}

function bindTabNavigation() {
  const tabs = [...document.querySelectorAll('[data-tab]')];
  tabs.forEach((button) => {
    button.addEventListener('click', () => selectTab(button.dataset.tab));
  });

  document.querySelector('.data-tabs')?.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const current = tabs.findIndex((button) => button.dataset.tab === state.activeTab);
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const next = (current + direction + tabs.length) % tabs.length;
    event.preventDefault();
    tabs[next].focus();
    selectTab(tabs[next].dataset.tab);
  });
}

function bindForms() {
  nutritionForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submitForm({
      form: nutritionForm,
      button: nutritionForm.querySelector('button[type="submit"]'),
      endpoint: '/data/nutrition',
      resultElement: nutritionResult,
      title: '食材保存失败',
      successTitle: '食材已保存',
      busyText: '保存中…'
    });
  });

  recipeForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submitForm({
      form: recipeForm,
      button: recipeForm.querySelector('button[type="submit"]'),
      endpoint: '/data/recipes',
      resultElement: recipeResult,
      title: '食谱保存失败',
      successTitle: '食谱已保存',
      busyText: '保存中…'
    });
  });

  recipePreviewButton.addEventListener('click', () => {
    submitForm({
      form: recipeForm,
      button: recipePreviewButton,
      endpoint: '/data/recipes/preview',
      resultElement: recipeResult,
      title: '食谱试算失败',
      successTitle: '食谱营养试算',
      busyText: '试算中…',
      refreshSchemaAfter: false
    });
  });

  eatOutForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submitForm({
      form: eatOutForm,
      button: eatOutForm.querySelector('button[type="submit"]'),
      endpoint: '/data/eat_out',
      resultElement: eatOutResult,
      title: '外食条目保存失败',
      successTitle: '外食条目已保存',
      busyText: '保存中…'
    });
  });

  aliasForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submitForm({
      form: aliasForm,
      button: aliasForm.querySelector('button[type="submit"]'),
      endpoint: '/data/aliases',
      resultElement: aliasResult,
      title: '别名保存失败',
      successTitle: '别名已保存',
      busyText: '保存中…'
    });
  });

  unitForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submitForm({
      form: unitForm,
      button: unitForm.querySelector('button[type="submit"]'),
      endpoint: '/data/units',
      resultElement: unitResult,
      title: '单位换算保存失败',
      successTitle: '单位换算已保存',
      busyText: '保存中…'
    });
  });

  batchForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!batchForm.reportValidity()) return;

    const button = batchForm.querySelector('button[type="submit"]');
    const raw = batchForm.elements.itemsJson.value.trim();
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      renderResult(batchResult, 'JSON 无法解析', new Error(error.message), 'error');
      return;
    }

    const items = Array.isArray(payload) ? payload : payload?.items;
    if (!Array.isArray(items)) {
      renderResult(batchResult, '格式不正确', new Error('顶层必须是数组，或包含 items 数组的对象。'), 'error');
      return;
    }
    if (!items.length) {
      renderResult(batchResult, '没有可导入的数据', new Error('items 数组不能为空。'), 'error');
      return;
    }

    await runRequest({
      button,
      endpoint: '/data/import',
      payload,
      resultElement: batchResult,
      title: '批量导入失败',
      successTitle: `批量导入完成 · 共 ${items.length} 条`,
      busyText: '导入中…',
      confirmText: `即将向本地数据写入 ${items.length} 条记录，是否继续？`,
      refreshSchemaAfter: true
    });
  });

  refreshSchemaButton.addEventListener('click', async () => {
    refreshSchemaButton.disabled = true;
    refreshSchemaButton.textContent = '读取中…';
    const ok = await loadSchema();
    if (ok) {
      renderResult(maintenanceResult, '数据概览已刷新', {
        action: 'schema_loaded',
        table_count: Object.keys(state.schema || {}).length
      }, 'success');
    }
    refreshSchemaButton.disabled = false;
    refreshSchemaButton.textContent = '刷新数据概览';
  });

  regenButton.addEventListener('click', () => {
    runRequest({
      button: regenButton,
      endpoint: '/data/regen',
      payload: {},
      resultElement: maintenanceResult,
      title: '食谱营养重算失败',
      successTitle: '食谱营养已重算',
      busyText: '重算中…',
      confirmText: '这会按当前营养库重算所有食谱的营养缓存，是否继续？',
      refreshSchemaAfter: false
    });
  });
}

function init() {
  bindTabNavigation();
  bindForms();
  loadSchema({ quiet: true });
}

document.addEventListener('DOMContentLoaded', init);
