// 外壳：导航、路由、顶栏状态

import { escapeHtml } from './util.js';
import {
  accountSummary, onAccount, onJob, onUnsorted, pollJob, refreshAccount, refreshUnsorted, verifyAccount,
} from './status.js';
import * as findPage from './pages/find.js';
import * as downloadsPage from './pages/downloads.js';
import * as classifyPage from './pages/classify.js';
import * as accountPage from './pages/account.js';

// 找漫画 → 下载 → 整理
const PAGES = [
  { key: 'find', label: '找漫画', module: findPage },
  { key: 'downloads', label: '下载', module: downloadsPage },
  { key: 'classify', label: '整理', module: classifyPage },
  { key: 'account', label: '账号', module: accountPage },
];
const DEFAULT_PAGE = 'find';
// 旧页面地址并入了「找漫画」
const ALIASES = { search: 'find', shelf: 'find', files: 'find' };

const nav = document.getElementById('nav');
const pageEl = document.getElementById('page');
let unmount = null;

nav.innerHTML = PAGES.map((p) =>
  `<a href="#/${p.key}" data-key="${p.key}">${p.label}<span class="nav-count" hidden></span></a>`).join('');

function setNavCount(key, count, title) {
  const el = nav.querySelector(`[data-key="${key}"] .nav-count`);
  el.hidden = !count;
  el.textContent = count || '';
  el.title = title;
}

function route() {
  const raw = location.hash.replace(/^#\//, '') || DEFAULT_PAGE;
  const key = ALIASES[raw] || raw;
  const page = PAGES.find((p) => p.key === key) || PAGES.find((p) => p.key === DEFAULT_PAGE);

  nav.querySelectorAll('a').forEach((a) => a.classList.toggle('active', a.dataset.key === page.key));
  if (unmount) unmount();
  unmount = null;
  pageEl.innerHTML = '';

  unmount = page.module.mount(pageEl);
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
  const c = job.counts || {};
  const waiting = (c.pending || 0) + (c.downloading || 0);
  setNavCount('downloads', waiting, `${waiting} 部等待下载`);

  const total = job.items.length;
  if (!total) {
    jobPill.hidden = true;
    return;
  }
  const finished = (c.done || 0) + (c.skipped || 0) + (c.failed || 0);
  const current = job.items.find((i) => i.status === 'downloading');
  let text;
  if (job.quota_blocked) text = `已达下载上限 · 待下载 ${job.pending} 部`;
  else if (job.running) text = `下载中 ${finished}/${total}${current ? ` · #${current.id}` : ''}`;
  else if (job.pending) text = `待下载 ${job.pending} 部`;
  else text = `上次下载：成功 ${(c.done || 0) + (c.skipped || 0)} · 失败 ${c.failed || 0}`;
  jobPill.hidden = false;
  jobPill.title = job.message || '';
  jobPill.innerHTML = `<span class="text">${escapeHtml(text)}</span>`
    + (job.running ? `<span class="mini"><div style="width:${finished / total * 100}%"></div></span>` : '');
});

onUnsorted((n) => setNavCount('classify', n, `downloads 里有 ${n} 个文件待整理`));

route();
pollJob();
refreshUnsorted();
// 切回页面时同步一次（可能在别的标签页里改过，或在文件夹里手动移动过文件）
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    pollJob();
    refreshUnsorted();
  }
});
refreshAccount().then(() => verifyAccount().catch(() => { /* 顶栏保持 cookie 状态即可 */ }));
