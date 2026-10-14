/* ==========================================================================
   公共前端工具：接口请求、提示条、格式化、标签页、退出登录
   ========================================================================== */

const BEHAVIOR_COLORS = {
  hand_raising: '#2b6cb0',
  reading: '#2f855a',
  writing: '#6b46c1',
  using_phone: '#c53030',
  bowing_head: '#c2760b',
  leaning_over_table: '#7b8794',
};

const BEHAVIOR_ORDER = ['hand_raising', 'reading', 'writing', 'using_phone', 'bowing_head', 'leaning_over_table'];
const BEHAVIOR_CN = {
  hand_raising: '举手', reading: '阅读', writing: '写作',
  using_phone: '使用手机', bowing_head: '低头', leaning_over_table: '靠在桌上',
};
const FOCUSED_KEYS = ['hand_raising', 'reading', 'writing'];

function isFocused(key) { return FOCUSED_KEYS.indexOf(key) >= 0; }
function behaviorCn(key) { return BEHAVIOR_CN[key] || key; }

async function api(path, options) {
  const opts = Object.assign({ credentials: 'same-origin' }, options || {});
  opts.headers = Object.assign({}, opts.headers || {});
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json';
    if (typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
  }
  const response = await fetch(path, opts);
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('登录状态已失效，请重新登录');
  }
  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch (err) { data = text; }
  }
  if (!response.ok) {
    let detail = '请求失败（' + response.status + '）';
    if (data && data.detail) {
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    }
    throw new Error(detail);
  }
  return data;
}

let toastTimer = null;
function toast(message, type) {
  const box = document.getElementById('toast');
  if (!box) { alert(message); return; }
  box.textContent = message;
  box.className = 'toast show ' + (type || '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.className = 'toast ' + (type || ''); }, 2600);
}

function esc(text) {
  if (text === null || text === undefined) return '';
  return String(text).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function fmtPercent(value, digits) {
  if (value === null || value === undefined || value === '') return '--';
  return Number(value).toFixed(digits === undefined ? 1 : digits) + '%';
}

function fmtDateTime(iso) {
  if (!iso) return '--';
  return String(iso).replace('T', ' ').slice(0, 19);
}

function fmtTime(iso) {
  if (!iso) return '--';
  return String(iso).replace('T', ' ').slice(11, 19);
}

function fmtDuration(minutes) {
  if (minutes === null || minutes === undefined) return '--';
  if (minutes < 1) return Math.round(minutes * 60) + ' 秒';
  if (minutes < 60) return minutes.toFixed(1) + ' 分钟';
  const hours = Math.floor(minutes / 60);
  return hours + ' 小时 ' + Math.round(minutes - hours * 60) + ' 分钟';
}

/* 秒数 -> mm:ss，用于视频检测的已用时间 / 预计剩余时间 */
function fmtSeconds(seconds) {
  if (seconds === null || seconds === undefined) return '--';
  const total = Math.max(0, Math.round(Number(seconds)));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return String(minutes).padStart(2, '0') + ':' + String(rest).padStart(2, '0');
}

function attentionClass(score) {
  if (score === null || score === undefined) return 'normal';
  if (score >= 85) return 'focused';
  if (score >= 70) return 'normal';
  if (score >= 60) return 'warning';
  return 'danger';
}

function statusBadge(status) {
  if (status === 'running') return '<span style="color:#c2760b">进行中</span>';
  if (status === 'finished') return '<span style="color:#2f9e44">已结束</span>';
  return esc(status);
}

function behaviorColor(key) {
  return BEHAVIOR_COLORS[key] || '#7b8794';
}

function initTabs(root) {
  const scope = root || document;
  scope.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      const group = tab.closest('.tabs');
      group.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
      tab.classList.add('active');
      const name = tab.dataset.tab;
      const container = group.parentElement;
      container.querySelectorAll('.tab-panel').forEach((panel) => {
        panel.classList.toggle('active', panel.dataset.panel === name);
      });
      document.dispatchEvent(new CustomEvent('tab-shown', { detail: { tab: name } }));
    });
  });
}

function bindLogout() {
  const button = document.getElementById('logoutBtn');
  if (!button) return;
  button.addEventListener('click', async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' });
    } catch (err) { /* 忽略退出异常，直接跳转登录页 */ }
    window.location.href = '/login';
  });
}

window.addEventListener('DOMContentLoaded', () => {
  bindLogout();
  initTabs(document);
});
