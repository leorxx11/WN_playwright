// 外壳：导航、路由、顶栏状态

import { escapeHtml } from './util.js';
import { accountSummary, onAccount, onJob, pollJob, refreshAccount, verifyAccount } from './status.js';
import * as searchPage from './pages/search.js';
import * as shelfPage from './pages/shelf.js';
import * as filesPage from './pages/files.js';
import * as downloadsPage from './pages/downloads.js';
import * as classifyPage from './pages/classify.js';
import * as accountPage from './pages/account.js';

const PAGES = [
  { key: 'search', label: '搜索', module: searchPage },
  { key: 'shelf', label: '书架', module: shelfPage },
  { key: 'files', label: '已导出', module: filesPage },
  { key: 'downloads', label: '下载', module: downloadsPage },
  { key: 'classify', label: '分类', module: classifyPage },
  { key: 'account', label: '账号', module: accountPage },
];
const DEFAULT_PAGE = 'files';

const nav = document.getElementById('nav');
const pageEl = document.getElementById('page');
let unmount = null;

nav.innerHTML = PAGES.map((p) =>
  `<a href="#/${p.key}" data-key="${p.key}" class="${p.module ? '' : 'soon'}">${p.label}</a>`).join('');

function route() {
  const key = location.hash.replace(/^#\//, '') || DEFAULT_PAGE;
  const page = PAGES.find((p) => p.key === key) || PAGES.find((p) => p.key === DEFAULT_PAGE);

  nav.querySelectorAll('a').forEach((a) => a.classList.toggle('active', a.dataset.key === page.key));
  if (unmount) unmount();
  unmount = null;
  pageEl.innerHTML = '';

  if (page.module) {
    unmount = page.module.mount(pageEl);
  } else {
    pageEl.innerHTML = `<div class="placeholder">「${escapeHtml(page.label)}」页面还在做，暂时请用命令行脚本。</div>`;
  }
}

window.addEventListener('hashchange', route);

/* ---------- 顶栏 ---------- */

const accountPill = document.getElementById('accountPill');
onAccount((s) => {
  const { level, text } = accountSummary(s);
  const domain = s.account ? ` · ${s.account.domain}` : '';
  accountPill.innerHTML = `<span class="dot ${level}"></span><span class="text">${escapeHtml(text + domain)}</span>`;
});

const jobPill = document.getElementById('jobPill');
onJob((job) => {
  const total = job.items.length;
  if (!total) {
    jobPill.hidden = true;
    return;
  }
  const c = job.counts || {};
  const finished = (c.done || 0) + (c.skipped || 0) + (c.failed || 0);
  const current = job.items.find((i) => i.status === 'downloading');
  let text;
  if (job.running) text = `下载中 ${finished}/${total}${current ? ` · #${current.id}` : ''}`;
  else if (job.pending) text = `待下载 ${job.pending} 部`;
  else text = `上次下载：成功 ${(c.done || 0) + (c.skipped || 0)} · 失败 ${c.failed || 0}`;
  jobPill.hidden = false;
  jobPill.title = job.message || '';
  jobPill.innerHTML = `<span class="text">${escapeHtml(text)}</span>`
    + (job.running ? `<span class="mini"><div style="width:${finished / total * 100}%"></div></span>` : '');
});

route();
pollJob();
// 切回页面时同步一次队列（可能在别的标签页里改过）
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') pollJob();
});
refreshAccount().then(() => verifyAccount().catch(() => { /* 顶栏保持 cookie 状态即可 */ }));
