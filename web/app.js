const samples = {
  cook: {
    input: '我有鸡胸肉、西兰花和鸡蛋，减脂，想 20 分钟内做完，口味清淡一点。',
    intent: 'cook', goal: 'fat_loss', time: 20, region: 'generic',
    ingredients: '鸡胸肉，西兰花，鸡蛋', allergies: ''
  },
  eat_out: {
    input: '今晚在成都应酬，减脂期想吃川菜，应该怎么点？',
    intent: 'eat_out', goal: 'fat_loss', time: 30, region: '川渝',
    ingredients: '', allergies: ''
  },
  substitute: {
    input: '减脂期不想吃白米饭，可以换成什么？',
    intent: 'substitute', goal: 'fat_loss', time: 20, region: 'generic',
    ingredients: '', allergies: '', originalIngredient: '白米饭'
  },
  nutrition: {
    input: '150 克鸡胸肉有多少蛋白质和热量？',
    intent: 'nutrition_analysis', goal: 'muscle_gain', time: 20, region: 'generic',
    ingredients: '', allergies: '', nutritionIngredient: '鸡胸肉', amountG: 150
  },
  safety: {
    input: '我想连续 7 天只喝水来快速减脂，给我一个食谱。',
    intent: 'unsafe', goal: 'fat_loss', time: 20, region: 'generic',
    ingredients: '', allergies: '', riskType: 'extreme_low_calorie'
  }
};

const ingredientWords = [
  '鸡胸肉', '鸡腿肉', '瘦牛肉', '猪里脊', '猪瘦肉', '鸡蛋', '虾仁', '三文鱼', '草鱼',
  '西兰花', '菜心', '菠菜', '生菜', '娃娃菜', '番茄', '西红柿', '黄瓜', '彩椒', '洋葱',
  '土豆', '红薯', '玉米', '南瓜', '山药', '燕麦', '荞麦面条', '白米饭', '杂粮饭',
  '嫩豆腐', '豆腐', '金针菇', '香菇', '木耳', '魔芋丝', '豆芽', '秋葵', '豌豆'
];

const goalLabels = { fat_loss: '减脂', muscle_gain: '增肌', maintain: '维持' };
const intentLabels = {
  cook: '自烹饪', eat_out: '外食', substitute: '食材替换',
  nutrition_analysis: '营养查询', provenance: '来源溯源', unsafe: '安全拦截'
};
const regionLabels = { generic: '不限', '川渝': '川渝', '粤式': '粤式', '江浙': '江浙', '北方': '北方' };

const form = document.getElementById('mealForm');
const userInput = document.getElementById('userInput');
const intentSelect = document.getElementById('intent');
const goalSelect = document.getElementById('goal');
const timeLimit = document.getElementById('timeLimit');
const regionSelect = document.getElementById('region');
const ingredientsInput = document.getElementById('ingredients');
const allergiesInput = document.getElementById('allergies');
const originalIngredient = document.getElementById('originalIngredient');
const nutritionIngredient = document.getElementById('nutritionIngredient');
const amountG = document.getElementById('amountG');
const results = document.getElementById('results');
const resultTitle = document.getElementById('resultTitle');
const resultMeta = document.getElementById('resultMeta');
const resultPanel = document.getElementById('resultPanel');
const requestSummary = document.getElementById('requestSummary');
const submitButton = document.getElementById('submitButton');
const serviceState = document.getElementById('serviceState');
const advancedFields = document.getElementById('advancedFields');
let currentRequestId = null;

const esc = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

const splitValues = (value) => String(value || '')
  .split(/[，,、;；\n]+/)
  .map((item) => item.trim())
  .filter(Boolean);

function detectIntent(text) {
  if (/断食|只喝水|催吐|暴食|节食到|绝食|不吃饭|病|糖尿病|怀孕|孕期|未成年/.test(text)) return 'unsafe';
  if (/替换|换成|替代|能不能换|用什么代替/.test(text)) return 'substitute';
  if (/多少热量|多少卡|营养|蛋白质含量|碳水|脂肪含量|克.*(热量|蛋白)/.test(text)) return 'nutrition_analysis';
  if (/外卖|外食|点餐|下馆子|餐厅|应酬|火锅|烧烤/.test(text)) return 'eat_out';
  return 'cook';
}

function detectGoal(text) {
  if (/增肌|增重|练后|长肌肉|高蛋白/.test(text)) return 'muscle_gain';
  if (/维持|保持体重|日常健康/.test(text)) return 'maintain';
  return 'fat_loss';
}

function detectRegion(text) {
  if (/成都|重庆|四川|川菜|川渝/.test(text)) return '川渝';
  if (/广州|广东|粤菜|粤式|潮汕/.test(text)) return '粤式';
  if (/上海|江苏|浙江|杭州|江浙/.test(text)) return '江浙';
  if (/北京|北方|东北/.test(text)) return '北方';
  return 'generic';
}

function detectIngredients(text) {
  return ingredientWords.filter((name) => text.includes(name));
}

function detectTime(text) {
  const match = text.match(/(\d{1,3})\s*分钟/);
  return match ? Number(match[1]) : null;
}

function updateAdvancedFields() {
  const intent = intentSelect.value;
  const visible = ['substitute', 'nutrition_analysis', 'unsafe'].includes(intent);
  advancedFields.classList.toggle('is-visible', visible);
  advancedFields.querySelectorAll('[data-advanced]').forEach((field) => {
    const type = field.dataset.advanced;
    field.hidden = !(type === 'substitute' && intent === 'substitute') &&
      !(type === 'nutrition' && intent === 'nutrition_analysis');
  });
}

function fillSample(name) {
  const sample = samples[name];
  if (!sample) return;
  userInput.value = sample.input;
  intentSelect.value = sample.intent;
  goalSelect.value = sample.goal;
  timeLimit.value = sample.time;
  regionSelect.value = sample.region;
  ingredientsInput.value = sample.ingredients || '';
  allergiesInput.value = sample.allergies || '';
  originalIngredient.value = sample.originalIngredient || '';
  nutritionIngredient.value = sample.nutritionIngredient || '';
  amountG.value = sample.amountG || 100;
  updateAdvancedFields();
  submitForm();
}

function buildPayload() {
  const text = userInput.value.trim();
  let intent = intentSelect.value;
  if (intent === 'auto') intent = detectIntent(text);

  const parsedIngredients = ingredientsInput.value.trim()
    ? splitValues(ingredientsInput.value)
    : detectIngredients(text);
  const parsedTime = Number(timeLimit.value) || detectTime(text) || null;
  const goal = goalSelect.value || detectGoal(text);
  const region = regionSelect.value || detectRegion(text);

  const payload = {
    intent,
    goal,
    region,
    time_limit: parsedTime,
    ingredients: parsedIngredients,
    allergies: splitValues(allergiesInput.value),
    avoid_items: [],
    flavor_preference: []
  };

  if (intent === 'substitute') {
    payload.original_ingredient = originalIngredient.value.trim() ||
      (parsedIngredients[0] || null);
  }
  if (intent === 'nutrition_analysis') {
    payload.nutrition_ingredient = nutritionIngredient.value.trim() ||
      (parsedIngredients[0] || null);
    payload.amount_g = Number(amountG.value) || 100;
  }
  if (intent === 'unsafe') {
    payload.risk_flag = true;
    payload.risk_type = /只喝水|断食|绝食/.test(text) ? 'extreme_low_calorie' : 'unsafe_advice';
  }
  return payload;
}

function renderRequestSummary(payload) {
  const items = [
    `<span class="chip"><strong>场景</strong>${esc(intentLabels[payload.intent] || payload.intent)}</span>`,
    `<span class="chip"><strong>目标</strong>${esc(goalLabels[payload.goal] || payload.goal)}</span>`
  ];
  if (payload.time_limit) items.push(`<span class="chip"><strong>时间</strong>${esc(payload.time_limit)} 分钟</span>`);
  if (payload.region) items.push(`<span class="chip"><strong>地域</strong>${esc(regionLabels[payload.region] || payload.region)}</span>`);
  if (payload.ingredients?.length) items.push(`<span class="chip"><strong>食材</strong>${esc(payload.ingredients.join('、'))}</span>`);
  if (payload.allergies?.length) items.push(`<span class="chip"><strong>过敏</strong>${esc(payload.allergies.join('、'))}</span>`);
  requestSummary.innerHTML = items.join('');
  requestSummary.hidden = false;
}

function formatNumber(value, unit = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1)}${unit}`;
}

function renderRecipe(recommendation, index) {
  const used = recommendation.matched_ingredients || [];
  const all = recommendation.ingredients || [];
  const missing = all.filter((name) => !used.includes(name));
  const nutrition = recommendation.nutrition || {};
  const breakdown = recommendation.ingredient_breakdown || [];

  const breakdownHtml = breakdown.slice(0, 6).map((item) => {
    const share = Math.round(Number(item.calorie_share || 0) * 100);
    return `<div class="breakdown-row">
      <span>${esc(item.name)}</span>
      <span class="breakdown-track"><span class="breakdown-fill" style="width:${Math.max(2, share)}%"></span></span>
      <span>${formatNumber(item.calories)} kcal · ${share}%</span>
    </div>`;
  }).join('');

  return `<article class="recipe-card">
    <div class="recipe-head">
      <div class="recipe-rank">${index + 1}</div>
      <div class="recipe-title-wrap">
        <div class="recipe-title">${esc(recommendation.name)}</div>
        <div class="recipe-subtitle">${esc(recommendation.cooking_time)} 分钟 · ${esc(recommendation.servings)} 份 · 每份 ${esc(recommendation.serving_weight_g)}g · ${esc(recommendation.region)}</div>
      </div>
      <div class="score-badge">匹配 ${Math.round(Number(recommendation.score || 0) * 100)}%</div>
    </div>
    <div class="nutrition-grid">
      <div class="nutrition-item"><span>热量</span><strong>${formatNumber(nutrition.calories, ' kcal')}</strong></div>
      <div class="nutrition-item"><span>蛋白质</span><strong>${formatNumber(nutrition.protein_g, 'g')}</strong></div>
      <div class="nutrition-item"><span>脂肪</span><strong>${formatNumber(nutrition.fat_g, 'g')}</strong></div>
      <div class="nutrition-item"><span>碳水</span><strong>${formatNumber(nutrition.carbs_g, 'g')}</strong></div>
    </div>
    <div class="card-body">
      <div class="card-block">
        <div class="block-label">食材匹配</div>
        <div class="ingredient-list">
          ${used.map((name) => `<span class="ingredient-chip">${esc(name)} · 已有</span>`).join('')}
          ${missing.map((name) => `<span class="ingredient-chip missing">${esc(name)} · 需补</span>`).join('')}
        </div>
      </div>
      ${recommendation.steps?.length ? `<div class="card-block">
        <div class="block-label">做法</div>
        <ol class="steps">${recommendation.steps.map((step) => `<li>${esc(step)}</li>`).join('')}</ol>
      </div>` : ''}
      ${breakdownHtml ? `<div class="card-block">
        <div class="block-label">热量来源</div>
        <div class="breakdown">${breakdownHtml}</div>
      </div>` : ''}
      ${recommendation.notes ? `<div class="note-box">${esc(recommendation.notes)}</div>` : ''}
      <div class="feedback-actions" data-feedback-group>
        <span class="feedback-label">这道菜怎么样？</span>
        <button type="button" class="feedback-button" data-recipe-id="${esc(recommendation.id)}" data-feedback-action="accept">采纳</button>
        <button type="button" class="feedback-button" data-recipe-id="${esc(recommendation.id)}" data-feedback-action="reject">不喜欢</button>
        <button type="button" class="feedback-button" data-recipe-id="${esc(recommendation.id)}" data-feedback-action="too_much">太麻烦</button>
        <button type="button" class="feedback-button" data-recipe-id="${esc(recommendation.id)}" data-feedback-action="regenerate">换一批</button>
        <span class="feedback-result" data-feedback-result hidden></span>
      </div>
    </div>
  </article>`;
}

async function submitFeedback(event) {
  const button = event.target.closest('[data-feedback-action]');
  if (!button) return;
  const group = button.closest('[data-feedback-group]');
  const result = group?.querySelector('[data-feedback-result]');
  const action = button.dataset.feedbackAction;
  const recipeId = button.dataset.recipeId;

  if (!currentRequestId) {
    if (result) {
      result.textContent = '这次结果缺少请求编号，暂时无法记录';
      result.hidden = false;
    }
    return;
  }

  group.querySelectorAll('button').forEach((item) => { item.disabled = true; });
  if (result) {
    result.textContent = '正在记录…';
    result.hidden = false;
  }

  try {
    const response = await fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: currentRequestId,
        recipe_id: recipeId,
        action,
        reason: button.textContent.trim()
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
    if (result) result.textContent = '已记录，感谢反馈';
  } catch (error) {
    group.querySelectorAll('button').forEach((item) => { item.disabled = false; });
    if (result) result.textContent = `记录失败：${error.message}`;
  }
}

function renderEatOut(item) {
  return `<article class="eatout-card">
    <div class="recipe-head" style="padding:0;margin-bottom:12px">
      <div class="recipe-title-wrap">
        <h3>${esc(item.name)}</h3>
        <div class="recipe-subtitle">${esc(item.region)} · 参考份量 ${esc(item.calorie_range || '未标注')}</div>
      </div>
      <div class="score-badge">匹配 ${Math.round(Number(item.score || 0) * 100)}%</div>
    </div>
    <p class="strategy">${esc(item.order_strategy)}</p>
    ${item.risk_notes?.length ? `<div class="mini-title">点餐时注意</div><ul class="warning-list">${item.risk_notes.map((note) => `<li>${esc(note)}</li>`).join('')}</ul>` : ''}
  </article>`;
}

function renderSubstitution(item) {
  return `<article class="substitution-card">
    <h3>${esc(item.original)} → ${esc(item.substitute)}</h3>
    <p class="strategy">${esc(item.reason)}</p>
    <div class="note-box">营养变化：${esc(item.nutrition_change || '暂无数据')}　适用目标：${esc(item.applies_to || '未标注')}</div>
  </article>`;
}

function renderNutrition(item) {
  const source = item.source_name || item.source_ref || item.source || '本地营养数据库';
  return `<div class="nutrition-hero">
    <div class="name">${esc(item.name)}</div>
    <div class="amount">${formatNumber(item.amount, 'g')} · 按 ${esc(item.unit || '100g')} 换算</div>
    <div class="nutrition-grid" style="border:1px solid var(--line);border-radius:14px;overflow:hidden">
      <div class="nutrition-item"><span>热量</span><strong>${formatNumber(item.calories, ' kcal')}</strong></div>
      <div class="nutrition-item"><span>蛋白质</span><strong>${formatNumber(item.protein_g, 'g')}</strong></div>
      <div class="nutrition-item"><span>脂肪</span><strong>${formatNumber(item.fat_g, 'g')}</strong></div>
      <div class="nutrition-item"><span>碳水</span><strong>${formatNumber(item.carbs_g, 'g')}</strong></div>
    </div>
    <div class="note-box">来源：${esc(source)} · 置信度：${esc(item.confidence || '未标注')} · 核验日期：${esc(item.verified_at || '未标注')}</div>
  </div>`;
}

function renderSources(sources) {
  return `<article class="source-card">
    <h3>数据来源</h3>
    <table class="source-table">
      <thead><tr><th>食材</th><th>来源</th><th>等级</th><th>核验日期</th></tr></thead>
      <tbody>${sources.map((item) => `<tr>
        <td>${esc(item.name)}</td>
        <td>${item.found ? `${esc(item.source_name || item.source_ref || item.source)}` : '未收录'}</td>
        <td>${esc(item.confidence || '—')}</td>
        <td>${esc(item.verified_at || '—')}</td>
      </tr>`).join('')}</tbody>
    </table>
  </article>`;
}

function renderResponse(data, elapsedMs) {
  const result = data.result || data;
  const type = result.answer_type;
  currentRequestId = data.request_id || null;
  resultPanel.setAttribute('aria-busy', 'false');
  resultMeta.textContent = `本地接口 ${formatNumber(elapsedMs, ' ms')}`;

  if (type === 'recipe') {
    resultTitle.textContent = result.recommendations?.length ? `给你 ${result.recommendations.length} 个可执行选项` : '这组条件下暂时没有匹配';
    if (!result.recommendations?.length) {
      results.innerHTML = `<div class="safety-card">
        <h3>需要补充信息或放宽条件</h3>
        <p>${esc(result.risk_notes?.[0] || '没有找到满足条件的食谱。')}</p>
      </div>`;
      return;
    }
    results.innerHTML = `<div class="result-section">
      <p class="section-note">营养均按“每份”展示；先看已有食材和时间，再看营养是否符合目标。</p>
      ${result.recommendations.map(renderRecipe).join('')}
    </div>`;
    return;
  }

  if (type === 'eat_out') {
    resultTitle.textContent = '外食时的点餐策略';
    results.innerHTML = `<div class="result-section">
      <p class="section-note">这里给出点餐方向和风险提醒，不对具体品牌做营养背书。</p>
      ${(result.recommendations || []).map(renderEatOut).join('')}
    </div>`;
    return;
  }

  if (type === 'substitution') {
    const items = result.recommendations || [];
    resultTitle.textContent = items.length ? '可以这样替换' : '暂时没有匹配的替换规则';
    results.innerHTML = `<div class="result-section">
      ${items.length ? items.map(renderSubstitution).join('') : '<div class="error-card">当前替换库没有覆盖这个食材，需要补充数据。</div>'}
    </div>`;
    return;
  }

  if (type === 'nutrition') {
    resultTitle.textContent = '营养数据';
    results.innerHTML = result.nutrition ? renderNutrition(result.nutrition) :
      '<div class="error-card">营养库中没有找到对应食材。</div>';
    return;
  }

  if (type === 'provenance') {
    resultTitle.textContent = '数据来源与口径';
    results.innerHTML = `<div class="result-section">${renderSources(result.sources || [])}</div>`;
    return;
  }

  if (type === 'safety') {
    resultTitle.textContent = '这类请求不适合直接给方案';
    results.innerHTML = `<div class="safety-card">
      <h3>已拦截：${esc(result.risk_type || '安全风险')}</h3>
      <p>${esc(result.message || '涉及潜在健康风险，建议咨询医生或注册营养师。')}</p>
    </div>`;
    return;
  }

  resultTitle.textContent = '接口已返回结果';
  results.innerHTML = `<pre class="error-card">${esc(JSON.stringify(result, null, 2))}</pre>`;
}

async function submitForm(event) {
  event?.preventDefault();
  currentRequestId = null;
  const payload = buildPayload();
  renderRequestSummary(payload);
  resultPanel.setAttribute('aria-busy', 'true');
  resultTitle.textContent = '正在处理';
  resultMeta.textContent = '';
  results.innerHTML = document.getElementById('loadingTemplate').innerHTML;
  submitButton.disabled = true;

  try {
    const response = await fetch('/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
    renderResponse(data, data.elapsed_ms);
  } catch (error) {
    resultPanel.setAttribute('aria-busy', 'false');
    resultTitle.textContent = '请求没有完成';
    resultMeta.textContent = '本地服务不可用';
    results.innerHTML = `<div class="error-card">
      <strong>无法连接推荐接口。</strong><br>
      请确认服务已在 127.0.0.1:8765 启动。<br>
      <small>${esc(error.message)}</small>
    </div>`;
  } finally {
    submitButton.disabled = false;
  }
}

async function checkHealth() {
  try {
    const response = await fetch('/health');
    if (!response.ok) throw new Error('health check failed');
    const data = await response.json();
    const counts = data.data || {};
    serviceState.classList.add('is-online');
    serviceState.innerHTML = `<span class="state-dot" aria-hidden="true"></span><span>服务正常 · ${counts['recipes.csv'] || 0} 道食谱</span>`;
  } catch {
    serviceState.classList.add('is-offline');
    serviceState.innerHTML = '<span class="state-dot" aria-hidden="true"></span><span>服务未连接</span>';
  }
}

function init() {
  document.querySelectorAll('[data-sample]').forEach((button) => {
    button.addEventListener('click', () => fillSample(button.dataset.sample));
  });
  intentSelect.addEventListener('change', updateAdvancedFields);
  form.addEventListener('submit', submitForm);
  results.addEventListener('click', submitFeedback);
  updateAdvancedFields();
  checkHealth();

  const demo = new URLSearchParams(location.search).get('demo');
  if (demo && samples[demo]) {
    requestAnimationFrame(() => fillSample(demo));
  }
}

document.addEventListener('DOMContentLoaded', init);
