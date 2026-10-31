// 账号：登录状态、验证、重新登录

import { escapeHtml, timeAgo, toast } from '../util.js';
import { accountSummary, onAccount, refreshAccount, startLogin, verifyAccount } from '../status.js';

export function mount(page) {
  page.innerHTML = `
    <div class="cards">
      <div class="card">
        <h2>登录状态</h2>
        <dl class="kv"></dl>
        <div class="actions">
          <button data-act="verify">检查登录状态</button>
          <button data-act="login" class="primary">重新登录</button>
        </div>
        <div class="status-line" hidden></div>
      </div>
      <div class="card">
        <h2>说明</h2>
        <ul>
          <li>账号密码在项目根目录的 <code>.env</code> 里设置（WNACG_USERNAME / WNACG_PASSWORD）。</li>
          <li>重新登录会打开浏览器窗口，遇到 Cloudflare 验证请在窗口里手动完成。</li>
          <li>登录和下载共用同一个浏览器 profile，正在下载时点重新登录，会等当前这批下载结束后再登录。</li>
          <li>cookie 生成后 24 小时内有效，过期后请点「重新登录」。</li>
        </ul>
      </div>
    </div>`;

  const kv = page.querySelector('.kv');
  const line = page.querySelector('.status-line');
  const verifyBtn = page.querySelector('[data-act="verify"]');
  const loginBtn = page.querySelector('[data-act="login"]');

  function render(s) {
    const a = s.account;
    if (!a) return;
    const c = a.cookie;
    const cookieText = !c ? '没有 cookie'
      : `${c.created_at.replace('T', ' ')}（${timeAgo(c.age_hours)}，${c.expired ? '已过期' : '24 小时内有效'}）`;
    kv.innerHTML = `
      <dt>用户名</dt><dd>${escapeHtml(a.username || '未设置')}</dd>
      <dt>当前域名</dt><dd>${escapeHtml(a.domain)}</dd>
      <dt>Cookie</dt><dd>${escapeHtml(cookieText)}</dd>
      <dt>状态</dt><dd>${escapeHtml(accountSummary(s).text)}</dd>`;

    const login = a.login;
    const busy = ['waiting', 'running'].includes(login.state);
    loginBtn.disabled = busy;
    loginBtn.textContent = busy ? '登录中...' : '重新登录';

    let level = '';
    let text = '';
    if (login.state !== 'idle') {
      level = { success: 'ok', failed: 'bad', waiting: 'warn', running: 'warn' }[login.state];
      text = login.message;
    } else if (s.verified) {
      level = s.verified.logged_in ? 'ok' : 'bad';
      text = s.verified.message;
    }
    line.hidden = !text;
    line.className = `status-line ${level}`;
    line.textContent = text;
  }

  verifyBtn.addEventListener('click', async () => {
    verifyBtn.disabled = true;
    verifyBtn.textContent = '检查中...';
    try {
      await verifyAccount();
    } catch (err) {
      toast(err.message);
    } finally {
      verifyBtn.disabled = false;
      verifyBtn.textContent = '检查登录状态';
    }
  });

  loginBtn.addEventListener('click', async () => {
    try {
      await startLogin();
    } catch (err) {
      toast(err.message);
    }
  });

  const off = onAccount(render);
  refreshAccount();
  return off;
}
