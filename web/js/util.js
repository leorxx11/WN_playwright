// 通用工具：请求、提示、转义、本地偏好

export async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(data.detail || `请求失败 (${resp.status})`);
    err.status = resp.status;   // 401 表示需要去账号页重新登录
    throw err;
  }
  return data;
}

let toastTimer = null;
export function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

export function normalize(text) {
  return String(text).normalize('NFKC').toLowerCase();
}

export function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

export function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 隐私模式等情况下忽略 */ }
}

export function timeAgo(hours) {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} 分钟前`;
  if (hours < 48) return `${Math.round(hours)} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}
