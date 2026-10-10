const samples = {
  cook: '我有鸡胸肉、西兰花和鸡蛋，减脂，想 20 分钟内做完，口味清淡一点。',
  eat_out: '今晚在成都应酬，减脂期想吃川菜，应该怎么点？',
  substitute: '减脂期不想吃白米饭，可以换成什么？',
  nutrition: '150 克鸡胸肉有多少蛋白质和热量？',
  safety: '我想连续 7 天只喝水来快速减脂，给我一个食谱。'
};

const form = document.getElementById('mealForm');
const userInput = document.getElementById('userInput');
const results = document.getElementById('results');
const resultTitle = document.getElementById('resultTitle');
const resultMeta = document.getElementById('resultMeta');
const resultPanel = document.getElementById('resultPanel');
const submitButton = document.getElementById('submitButton');
const serviceState = document.getElementById('serviceState');
const loadingTemplate = document.getElementById('loadingTemplate');

let currentConversationId = localStorage.getItem('fitmeal_conversation_id') || '';
let currentMessage = null;

const esc = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

function getUserId() {
  let userId = localStorage.getItem('fitmeal_user_id');
  if (!userId) {
    userId = globalThis.crypto?.randomUUID?.() || `fitmeal-${Date.now()}`;
    localStorage.setItem('fitmeal_user_id', userId);
  }
  return userId;
}

function formatElapsed(value) {
  const milliseconds = Number(value || 0);
  if (milliseconds <= 0) return '已完成';
  return milliseconds >= 1000
    ? `${(milliseconds / 1000).toFixed(1)} 秒`
    : `${Math.round(milliseconds)} 毫秒`;
}

function renderInline(value) {
  return esc(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function renderAnswer(answer) {
  const lines = String(answer || '').replace(/\r\n?/g, '\n').split('\n');
  const html = [];
  let listType = '';

  const closeList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = '';
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      return;
    }

    let match = line.match(/^(#{1,3})\s+(.+)$/);
    if (match) {
      closeList();
      const level = Math.min(match[1].length + 2, 5);
      html.push(`<h${level}>${renderInline(match[2])}</h${level}>`);
      return;
    }

    match = line.match(/^[-*•]\s+(.+)$/);
    if (match) {
      if (listType !== 'ul') {
        closeList();
        listType = 'ul';
        html.push('<ul>');
      }
      html.push(`<li>${renderInline(match[1])}</li>`);
      return;
    }

    match = line.match(/^\d+[.、)]\s*(.+)$/);
    if (match) {
      if (listType !== 'ol') {
        closeList();
        listType = 'ol';
        html.push('<ol>');
      }
      html.push(`<li>${renderInline(match[1])}</li>`);
      return;
    }

    closeList();
    html.push(`<p>${renderInline(line)}</p>`);
  });

  closeList();
  return html.join('') || '<p>Dify 返回了空回答。</p>';
}

function usageText(metadata) {
  const usage = metadata?.usage || {};
  const parts = [];
  if (Number.isFinite(Number(usage.total_tokens))) {
    parts.push(`${Number(usage.total_tokens)} tokens`);
  }
  if (Number.isFinite(Number(usage.latency))) {
    parts.push(`模型 ${Number(usage.latency).toFixed(1)} 秒`);
  }
  return parts.join(' · ');
}

function renderResult(data) {
  currentMessage = {
    requestId: data.request_id,
    messageId: data.message_id,
    conversationId: data.conversation_id
  };

  const usage = usageText(data.metadata);
  resultTitle.textContent = 'Dify 建议已生成';
  resultMeta.textContent = `Dify Chatflow · ${formatElapsed(data.elapsed_ms)}`;

  results.innerHTML = `<article class="chat-card">
    <div class="chat-source">
      <span class="live-dot" aria-hidden="true"></span>
      <strong>Dify Chatflow · 真实 API</strong>
      <span>${usage ? esc(usage) : '完整链路已完成'}</span>
    </div>
    <div class="dify-answer">${renderAnswer(data.answer)}</div>
    <div class="feedback-actions" data-feedback-group>
      <span class="feedback-label">这个回答有帮助吗？</span>
      <button type="button" class="feedback-button" data-feedback-action="accept">有帮助</button>
      <button type="button" class="feedback-button" data-feedback-action="reject">没帮助</button>
      <span class="feedback-result" data-feedback-result hidden></span>
    </div>
  </article>`;
}

async function submitForm(event) {
  event?.preventDefault();
  const query = userInput.value.trim();
  if (!query) {
    resultTitle.textContent = '还差一句需求';
    resultMeta.textContent = '';
    results.innerHTML = '<div class="error-card">先说说现有食材、目标或今晚想吃什么。</div>';
    userInput.focus();
    return;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 185000);
  currentMessage = null;
  resultPanel.setAttribute('aria-busy', 'true');
  resultTitle.textContent = 'Dify 正在生成';
  resultMeta.textContent = '真实链路通常需要 20 至 40 秒';
  results.innerHTML = loadingTemplate.innerHTML;
  submitButton.disabled = true;

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        conversation_id: currentConversationId,
        user: getUserId()
      }),
      signal: controller.signal
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
    if (!data.answer) throw new Error('Dify 没有返回可展示的回答');

    currentConversationId = data.conversation_id || currentConversationId;
    localStorage.setItem('fitmeal_conversation_id', currentConversationId);
    renderResult(data);
  } catch (error) {
    resultTitle.textContent = 'Dify 请求没有完成';
    resultMeta.textContent = '未使用本地规则降级';
    const message = error.name === 'AbortError'
      ? '等待超过 185 秒，请检查 Dify 和本地数据服务。'
      : error.message;
    results.innerHTML = `<div class="error-card">
      <strong>这次没有拿到 Dify 回答。</strong><br>
      请确认 Dify、8765 数据服务和 8766 向量服务都在运行。<br>
      <small>${esc(message)}</small>
    </div>`;
  } finally {
    clearTimeout(timeout);
    resultPanel.setAttribute('aria-busy', 'false');
    submitButton.disabled = false;
  }
}

async function submitFeedback(event) {
  const button = event.target.closest('[data-feedback-action]');
  if (!button) return;

  const group = button.closest('[data-feedback-group]');
  const result = group?.querySelector('[data-feedback-result]');
  const action = button.dataset.feedbackAction;
  const messageId = currentMessage?.requestId || currentMessage?.messageId;

  if (!messageId) {
    if (result) {
      result.textContent = '这次回答缺少消息编号，暂时无法记录';
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
        request_id: messageId,
        recipe_id: currentMessage.messageId || messageId,
        action
      })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
    if (result) result.textContent = '已记录，感谢反馈';
  } catch (error) {
    group.querySelectorAll('button').forEach((item) => { item.disabled = false; });
    if (result) result.textContent = `记录失败：${error.message}`;
  }
}

function fillSample(name) {
  const sample = samples[name];
  if (!sample) return;
  userInput.value = sample;
  submitForm();
}

async function checkHealth() {
  try {
    const [serviceResponse, chatResponse] = await Promise.all([
      fetch('/health'),
      fetch('/chat/status')
    ]);
    if (!serviceResponse.ok || !chatResponse.ok) throw new Error('service unavailable');

    const health = await serviceResponse.json();
    const chat = await chatResponse.json();
    if (!chat.configured) throw new Error('Dify is not configured');

    const recipeCount = health.data?.['recipes.csv'] || 0;
    serviceState.classList.remove('is-offline');
    serviceState.classList.add('is-online');
    serviceState.innerHTML = `<span class="state-dot" aria-hidden="true"></span><span>Dify 链路已配置 · ${recipeCount} 道食谱</span>`;
  } catch {
    serviceState.classList.remove('is-online');
    serviceState.classList.add('is-offline');
    serviceState.innerHTML = '<span class="state-dot" aria-hidden="true"></span><span>Dify 或本地服务未就绪</span>';
  }
}

function init() {
  document.querySelectorAll('[data-sample]').forEach((button) => {
    button.addEventListener('click', () => fillSample(button.dataset.sample));
  });
  form.addEventListener('submit', submitForm);
  results.addEventListener('click', submitFeedback);
  checkHealth();

  const demo = new URLSearchParams(location.search).get('demo');
  if (demo && samples[demo]) {
    requestAnimationFrame(() => fillSample(demo));
  }
}

document.addEventListener('DOMContentLoaded', init);
