const tableLabels = {
  nutrition: '食材营养',
  recipes: '食谱',
  eat_out: '外食条目',
  substitutions: '替换规则',
  aliases: '食材别名',
  units: '单位换算',
  goal_rules: '目标规则',
  target_ingredients: '目标食材'
};

const preferredColumns = {
  nutrition: ['name', 'category', 'calories', 'protein_g', 'fat_g', 'carbs_g', 'fiber_g', 'source'],
  recipes: ['name', 'region', 'goal', 'servings', 'serving_weight_g', 'calories', 'protein_g', 'fat_g', 'carbs_g', 'cooking_time', 'tags', 'source'],
  eat_out: ['name', 'region', 'suitable_goals', 'order_strategy', 'risk_notes', 'calorie_range', 'tags'],
  substitutions: ['original', 'substitute', 'reason', 'nutrition_change', 'applies_to', 'source', 'confidence'],
  aliases: ['alias', 'standard', 'note'],
  units: ['unit', 'ingredient', 'grams', 'note'],
  goal_rules: ['goal', 'calorie_min', 'calorie_max', 'protein_min', 'fat_max', 'description'],
  target_ingredients: ['ingredient', 'category', 'priority', 'target_recipes', 'current_recipes', 'reason', 'note']
};

const queryPlaceholders = {
  nutrition: '例：鸡胸肉、protein、usda_fdc',
  recipes: '例：西兰花、快手菜、15',
  eat_out: '例：牛肉、轻食、减脂',
  substitutions: '例：鸡蛋、豆腐、蛋白质',
  aliases: '例：大虾、鸡胸、口语叫法',
  units: '例：个、鸡蛋、50',
  goal_rules: '例：fat_loss、减脂、520',
  target_ingredients: '例：上海青、P0、评测集'
};

const validLimits = new Set([20, 50, 100, 200]);
const state = {
  schema: null,
  table: 'nutrition',
  query: '',
  limit: 50,
  offset: 0,
  total: 0,
  columns: [],
  rows: [],
  allColumns: false,
  loading: false
};

const serviceState = document.getElementById('serviceState');
const tableCount = document.getElementById('tableCount');
const currentTotal = document.getElementById('currentTotal');
const currentReturned = document.getElementById('currentReturned');
const queryForm = document.getElementById('queryForm');
const tableSelect = document.getElementById('tableSelect');
const queryInput = document.getElementById('queryInput');
const limitSelect = document.getElementById('limitSelect');
const queryButton = document.getElementById('queryButton');
const queryHint = document.getElementById('queryHint');
const resultTitle = document.getElementById('resultTitle');
const resultMeta = document.getElementById('resultMeta');
const allColumnsToggle = document.getElementById('allColumnsToggle');
const tableState = document.getElementById('tableState');
const tableWrap = document.getElementById('tableWrap');
const tableHead = document.getElementById('tableHead');
const tableBody = document.getElementById('tableBody');
const pager = document.getElementById('pager');
const pagerInfo = document.getElementById('pagerInfo');
const prevPage = document.getElementById('prevPage');
const nextPage = document.getElementById('nextPage');
const rowDialog = document.getElementById('rowDialog');
const dialogTitle = document.getElementById('dialogTitle');
const dialogBody = document.getElementById('dialogBody');
const dialogClose = document.getElementById('dialogClose');

let requestSequence = 0;

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

function formatValue(value) {
  if (Array.isArray(value)) return value.join('、');
  if (value && typeof value === 'object') return pretty(value);
  return String(value ?? '');
}

function formatCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '—';
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

async function apiRequest(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false) {
    throw new Error(errorMessage(data, response.status));
  }
  return data;
}

function setServiceState(online, text) {
  serviceState.classList.toggle('is-online', online);
  serviceState.classList.toggle('is-offline', !online);
  serviceState.querySelector('span:last-child').textContent = text;
}

function readInitialState() {
  const params = new URLSearchParams(window.location.search);
  const requestedTable = params.get('table');
  const requestedLimit = Number(params.get('limit'));
  const requestedOffset = Number(params.get('offset'));

  if (requestedTable && tableLabels[requestedTable]) state.table = requestedTable;
  if (validLimits.has(requestedLimit)) state.limit = requestedLimit;
  if (Number.isInteger(requestedOffset) && requestedOffset >= 0) state.offset = requestedOffset;
  state.query = (params.get('q') || '').trim();

  tableSelect.value = state.table;
  limitSelect.value = String(state.limit);
  queryInput.value = state.query;
  queryInput.placeholder = queryPlaceholders[state.table];
}

function updateUrl() {
  const params = new URLSearchParams();
  params.set('table', state.table);
  if (state.query) params.set('q', state.query);
  if (state.limit !== 50) params.set('limit', String(state.limit));
  if (state.offset) params.set('offset', String(state.offset));
  window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
}

function visibleColumns() {
  const preferred = (preferredColumns[state.table] || []).filter((column) => state.columns.includes(column));
  if (state.allColumns || !preferred.length) return [...state.columns];
  return preferred;
}

function showTableState(message, isError = false) {
  tableState.hidden = false;
  tableState.textContent = message;
  tableState.classList.toggle('is-error', isError);
  tableWrap.hidden = true;
  pager.hidden = true;
}

function renderRows() {
  const columns = visibleColumns();
  const hasRows = state.rows.length > 0;
  resultTitle.textContent = tableLabels[state.table] || state.table;
  allColumnsToggle.disabled = !state.columns.length;

  const source = state.schema?.[state.table]?.file || '';
  const totalText = `${formatCount(state.total)} 条`;
  resultMeta.textContent = state.query
    ? `关键词“${state.query}” · 匹配 ${totalText}${source ? ` · ${source}` : ''}`
    : `全表 ${totalText}${source ? ` · ${source}` : ''}`;
  currentTotal.textContent = formatCount(state.total);
  currentReturned.textContent = formatCount(state.rows.length);

  if (!hasRows) {
    const message = state.query
      ? `没有找到与“${state.query}”匹配的记录。`
      : '这张表暂时没有数据。';
    showTableState(message);
    return;
  }

  tableState.hidden = true;
  tableState.classList.remove('is-error');
  tableWrap.hidden = false;

  tableHead.innerHTML = `<tr><th scope="col">#</th>${columns.map((column) => `<th scope="col">${esc(column)}</th>`).join('')}</tr>`;
  tableBody.innerHTML = state.rows.map((row, index) => {
    const cells = columns.map((column) => {
      const value = formatValue(row[column]);
      const display = value || '—';
      const className = value ? 'cell-text' : 'cell-text empty-cell';
      return `<td><span class="${className}" title="${esc(value)}">${esc(display)}</span></td>`;
    }).join('');
    return `<tr data-row-index="${index}" tabindex="0" aria-label="查看第 ${state.offset + index + 1} 条记录详情"><td class="row-index">${state.offset + index + 1}</td>${cells}</tr>`;
  }).join('');

  const start = state.offset + 1;
  const end = Math.min(state.offset + state.rows.length, state.total);
  const page = Math.floor(state.offset / state.limit) + 1;
  const pages = Math.max(1, Math.ceil(state.total / state.limit));
  pager.hidden = false;
  pagerInfo.textContent = `显示第 ${start}–${end} 条，共 ${formatCount(state.total)} 条 · 第 ${page}/${pages} 页`;
  prevPage.disabled = state.offset <= 0;
  nextPage.disabled = state.offset + state.limit >= state.total;
}

function openDialog(row, rowIndex) {
  const titleValue = row.name || row.original || row.alias || row.unit || row.ingredient || `第 ${rowIndex + 1} 条`;
  dialogTitle.textContent = `${tableLabels[state.table] || state.table} · ${titleValue}`;
  dialogBody.innerHTML = `<div class="detail-list">${state.columns.map((column) => {
    const value = formatValue(row[column]);
    return `<div class="detail-key">${esc(column)}</div><div class="detail-value">${esc(value || '—')}</div>`;
  }).join('')}</div>`;

  if (typeof rowDialog.showModal === 'function') {
    rowDialog.showModal();
  } else {
    rowDialog.setAttribute('open', '');
  }
}

function closeDialog() {
  if (typeof rowDialog.close === 'function') {
    rowDialog.close();
  } else {
    rowDialog.removeAttribute('open');
  }
}

async function loadSchema() {
  try {
    const data = await apiRequest('/data/schema');
    state.schema = data.result || {};
    tableCount.textContent = formatCount(Object.keys(state.schema).length);
    setServiceState(true, '数据服务已连接');
  } catch (error) {
    tableCount.textContent = '—';
    setServiceState(false, '数据服务未就绪');
    throw error;
  }
}

async function loadRows() {
  const sequence = ++requestSequence;
  state.loading = true;
  queryButton.disabled = true;
  queryButton.textContent = '查询中…';
  showTableState('正在读取数据…');

  const params = new URLSearchParams({
    table: state.table,
    q: state.query,
    limit: String(state.limit),
    offset: String(state.offset)
  });

  try {
    const data = await apiRequest(`/data/rows?${params}`);
    if (sequence !== requestSequence) return;

    const result = data.result || {};
    state.total = Number(result.total) || 0;
    state.columns = Array.isArray(result.columns) ? result.columns : [];
    state.rows = Array.isArray(result.rows) ? result.rows : [];
    state.limit = Number(result.limit) || state.limit;
    state.offset = Number(result.offset) || 0;
    state.query = String(result.query || '');

    updateUrl();
    renderRows();
    setServiceState(true, '数据服务已连接');
  } catch (error) {
    if (sequence !== requestSequence) return;
    state.rows = [];
    state.total = 0;
    state.columns = [];
    currentTotal.textContent = '—';
    currentReturned.textContent = '—';
    resultMeta.textContent = '查询没有完成';
    showTableState(`读取失败：${error.message}`, true);
    setServiceState(false, '数据服务未就绪');
  } finally {
    if (sequence === requestSequence) {
      state.loading = false;
      queryButton.disabled = false;
      queryButton.textContent = '查询数据';
    }
  }
}

function resetToFirstPage() {
  state.offset = 0;
  loadRows();
}

function bindEvents() {
  queryForm.addEventListener('submit', (event) => {
    event.preventDefault();
    state.table = tableSelect.value;
    state.query = queryInput.value.trim();
    state.limit = Number(limitSelect.value) || 50;
    resetToFirstPage();
  });

  tableSelect.addEventListener('change', () => {
    state.table = tableSelect.value;
    state.query = queryInput.value.trim();
    queryInput.placeholder = queryPlaceholders[state.table];
    resetToFirstPage();
  });

  limitSelect.addEventListener('change', () => {
    state.limit = Number(limitSelect.value) || 50;
    resetToFirstPage();
  });

  allColumnsToggle.addEventListener('change', () => {
    state.allColumns = allColumnsToggle.checked;
    if (state.rows.length) renderRows();
  });

  prevPage.addEventListener('click', () => {
    state.offset = Math.max(0, state.offset - state.limit);
    loadRows();
  });

  nextPage.addEventListener('click', () => {
    state.offset += state.limit;
    loadRows();
  });

  tableBody.addEventListener('click', (event) => {
    const rowElement = event.target.closest('tr[data-row-index]');
    if (!rowElement) return;
    const rowIndex = Number(rowElement.dataset.rowIndex);
    openDialog(state.rows[rowIndex], rowIndex);
  });

  tableBody.addEventListener('keydown', (event) => {
    if (!['Enter', ' '].includes(event.key)) return;
    const rowElement = event.target.closest('tr[data-row-index]');
    if (!rowElement) return;
    event.preventDefault();
    const rowIndex = Number(rowElement.dataset.rowIndex);
    openDialog(state.rows[rowIndex], rowIndex);
  });

  dialogClose.addEventListener('click', closeDialog);
  rowDialog.addEventListener('click', (event) => {
    if (event.target === rowDialog) closeDialog();
  });
}

async function init() {
  readInitialState();
  bindEvents();
  queryHint.textContent = '关键词会匹配当前表的全部字段，不区分英文大小写';
  try {
    await Promise.all([loadSchema(), loadRows()]);
  } catch {
    // 两个请求各自负责页面状态，这里只避免未处理的 Promise 异常。
  }
}

document.addEventListener('DOMContentLoaded', init);
