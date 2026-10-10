const form = document.getElementById('nutritionForm');
const rowsContainer = document.getElementById('ingredientRows');
const rowTemplate = document.getElementById('ingredientRowTemplate');
const addIngredientButton = document.getElementById('addIngredient');
const calculateButton = document.getElementById('calculateButton');
const servingsInput = document.getElementById('servings');
const resultPanel = document.getElementById('resultPanel');
const resultTitle = document.getElementById('resultTitle');
const resultMeta = document.getElementById('resultMeta');
const emptyState = document.getElementById('emptyState');
const resultContent = document.getElementById('resultContent');
const resultSummary = document.getElementById('resultSummary');
const unresolvedPanel = document.getElementById('unresolvedPanel');
const breakdownBody = document.getElementById('breakdownBody');
const ingredientOptions = document.getElementById('ingredientOptions');
const serviceState = document.getElementById('serviceState');

const macroLabels = {
  calories: ['热量', 'kcal'],
  protein_g: ['蛋白质', 'g'],
  fat_g: ['脂肪', 'g'],
  carbs_g: ['碳水', 'g'],
  fiber_g: ['膳食纤维', 'g']
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function number(value, digits = 1) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '—';
  return parsed.toFixed(digits).replace(/\.0$/, '');
}

function setServiceState(online, message) {
  serviceState.classList.toggle('is-online', online);
  serviceState.classList.toggle('is-offline', !online);
  serviceState.querySelector('span:last-child').textContent = message;
}

function createIngredientRow(name = '', amount = '') {
  const fragment = rowTemplate.content.cloneNode(true);
  const row = fragment.querySelector('.ingredient-row');
  row.querySelector('input[name="name"]').value = name;
  row.querySelector('input[name="amount_g"]').value = amount;
  row.querySelector('.remove-row').addEventListener('click', () => {
    row.remove();
    if (!rowsContainer.querySelector('.ingredient-row')) createIngredientRow('', '');
    updateRemoveButtons();
  });
  rowsContainer.appendChild(fragment);
  updateRemoveButtons();
}

function updateRemoveButtons() {
  const rows = [...rowsContainer.querySelectorAll('.ingredient-row')];
  rows.forEach((row) => {
    row.querySelector('.remove-row').disabled = rows.length <= 1;
  });
}

function collectItems() {
  const items = [];
  const errors = [];
  [...rowsContainer.querySelectorAll('.ingredient-row')].forEach((row, index) => {
    const name = row.querySelector('input[name="name"]').value.trim();
    const amountText = row.querySelector('input[name="amount_g"]').value.trim();
    const amount = Number(amountText);
    if (!name && !amountText) return;
    if (!name) {
      errors.push(`第 ${index + 1} 行缺少食材名`);
      return;
    }
    if (!amountText || !Number.isFinite(amount) || amount <= 0) {
      errors.push(`第 ${index + 1} 行重量必须是大于 0 的数字`);
      return;
    }
    items.push({ name, amount_g: amount });
  });
  if (!items.length && !errors.length) errors.push('请至少填写一条食材和重量');
  return { items, errors };
}

function reasonText(item) {
  const reason = String(item?.reason || '');
  if (reason === 'no_nutrition_row') return '营养库中没有这个食材';
  if (reason.startsWith('nounit:')) return `无法换算单位“${reason.slice(7) || '未知'}”`;
  if (reason.startsWith('unparsed:')) return '重量格式无法识别';
  return reason || '无法计算';
}

function provenanceText(item) {
  const ref = String(item?.source_ref || '').trim();
  const name = String(item?.source_name || '').trim();
  const source = String(item?.source || '').trim();
  if (ref && name) return `${ref} · ${name}`;
  return ref || name || source || '数据表未登记来源';
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok || payload?.ok === false) {
    const message = payload?.message || payload?.error || `请求失败（${response.status}）`;
    throw new Error(message);
  }
  return payload;
}

function renderSummary(data) {
  const total = data.total_nutrition || {};
  const perServing = data.per_serving_nutrition || {};
  const servings = Number(data.servings) || 1;
  const unresolvedCount = Array.isArray(data.unresolved) ? data.unresolved.length : 0;
  const resolvedCount = Array.isArray(data.ingredient_breakdown) ? data.ingredient_breakdown.length : 0;
  const complete = data.complete === true;

  resultTitle.textContent = complete ? '本次营养结果' : '部分食材未计算';
  resultMeta.textContent = `${resolvedCount} 种已识别食材 · 总重 ${number(data.total_weight_g)} 克${servings > 1 ? ` · 每份 ${number(data.serving_weight_g)} 克` : ''}`;

  resultSummary.innerHTML = `
    <div class="macro-grid">
      ${Object.entries(macroLabels).map(([key, [label, unit]], index) => `
        <div class="macro-card${index === 0 ? ' is-primary' : ''}">
          <span>${label}</span>
          <strong>${number(total[key])}</strong>
          <small>${unit} · 录入总合计</small>
        </div>
      `).join('')}
    </div>
    ${servings > 1 ? `
      <div class="serving-strip">
        分成 <strong>${servings}</strong> 份后，每份热量 <strong>${number(perServing.calories)} kcal</strong>，
        蛋白质 <strong>${number(perServing.protein_g)} g</strong>，脂肪 <strong>${number(perServing.fat_g)} g</strong>，
        碳水 <strong>${number(perServing.carbs_g)} g</strong>，膳食纤维 <strong>${number(perServing.fiber_g)} g</strong>。
      </div>
    ` : ''}
    ${unresolvedCount ? `
      <div class="unresolved-panel">
        <strong>有 ${unresolvedCount} 项没有计入合计</strong>
        <ul class="unresolved-list">
          ${data.unresolved.map((item) => `<li>${esc(item.name || '未命名食材')}${item.amount ? `（${esc(item.amount)}）` : ''}：${esc(reasonText(item))}</li>`).join('')}
        </ul>
        <div>请先到数据录入台补齐营养数据或别名，再重新计算。</div>
      </div>
    ` : ''}
    ${!resolvedCount ? '<div class="unresolved-panel"><strong>没有可计算的食材</strong><div>当前结果全部为 0，请检查食材名称或先补营养数据。</div></div>' : ''}
  `;
}

function renderBreakdown(data) {
  breakdownBody.innerHTML = data.ingredient_breakdown.map((item) => {
    const share = Math.max(0, Math.min(100, Math.round(Number(item.calorie_share || 0) * 100)));
    const rawName = item.raw_name && item.raw_name !== item.name ? `原始输入：${item.raw_name}` : '营养库标准名';
    return `
      <tr>
        <td class="ingredient-cell">
          <strong>${esc(item.name)}</strong>
          <small>${esc(rawName)}</small>
        </td>
        <td>${number(item.amount_g)} g</td>
        <td class="calorie-cell">
          <strong>${number(item.calories)} kcal</strong>
          <div class="calorie-bar" title="占本次总热量 ${share}%"><span style="width:${share}%"></span></div>
          <small>${share}%</small>
        </td>
        <td>${number(item.protein_g)} g</td>
        <td>${number(item.fat_g)} g</td>
        <td>${number(item.carbs_g)} g</td>
        <td>${number(item.fiber_g)} g</td>
        <td class="source-cell" title="${esc(provenanceText(item))}">${esc(provenanceText(item))}</td>
      </tr>
    `;
  }).join('');
}

function renderResult(data) {
  emptyState.hidden = true;
  resultContent.hidden = false;
  resultPanel.setAttribute('aria-busy', 'false');
  renderSummary(data);
  renderBreakdown(data);
}

function showError(message) {
  emptyState.hidden = true;
  resultContent.hidden = false;
  resultTitle.textContent = '计算没有完成';
  resultMeta.textContent = message;
  resultSummary.innerHTML = `<div class="unresolved-panel"><strong>请检查后重试</strong><div>${esc(message)}</div></div>`;
  breakdownBody.innerHTML = '';
  resultPanel.setAttribute('aria-busy', 'false');
}

async function loadIngredientOptions() {
  try {
    const [nutrition, aliases] = await Promise.all([
      apiRequest('/data/rows?table=nutrition&limit=200&offset=0'),
      apiRequest('/data/rows?table=aliases&limit=200&offset=0')
    ]);
    const names = new Set();
    (nutrition?.result?.rows || []).forEach((row) => row.name && names.add(String(row.name).trim()));
    (aliases?.result?.rows || []).forEach((row) => {
      if (row.alias) names.add(String(row.alias).trim());
      if (row.standard) names.add(String(row.standard).trim());
    });
    ingredientOptions.innerHTML = [...names].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN')).map((name) => `<option value="${esc(name)}"></option>`).join('');
    setServiceState(true, '营养数据已连接');
  } catch (error) {
    setServiceState(false, '营养数据未就绪');
  }
}

async function calculate(event) {
  event.preventDefault();
  const { items, errors } = collectItems();
  if (errors.length) {
    showError(errors.join('；'));
    return;
  }

  const servings = Number(servingsInput.value);
  if (!Number.isInteger(servings) || servings < 1 || servings > 100) {
    showError('份数必须是 1 到 100 之间的整数');
    return;
  }

  calculateButton.disabled = true;
  calculateButton.querySelector('span').textContent = '计算中…';
  resultPanel.setAttribute('aria-busy', 'true');

  try {
    const payload = await apiRequest('/nutrition/calculate', {
      method: 'POST',
      body: JSON.stringify({ items, servings })
    });
    renderResult(payload.result || {});
    setServiceState(true, '营养数据已连接');
  } catch (error) {
    showError(error.message);
    setServiceState(false, '计算服务未就绪');
  } finally {
    calculateButton.disabled = false;
    calculateButton.querySelector('span').textContent = '计算营养';
  }
}

addIngredientButton.addEventListener('click', () => {
  createIngredientRow();
  const rows = rowsContainer.querySelectorAll('.ingredient-row');
  rows[rows.length - 1]?.querySelector('input[name="name"]')?.focus();
});

form.addEventListener('submit', calculate);

createIngredientRow('鸡胸肉', '150');
createIngredientRow('西兰花', '200');
loadIngredientOptions();
