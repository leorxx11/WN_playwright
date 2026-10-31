// 下载：队列管理、按ID/网址添加、最近下载记录

import { api, escapeHtml, toast } from '../util.js';
import { onJob, queueAction, startDownload, status, stopDownload } from '../status.js';

const STATUS_LABEL = {
  pending: '等待', downloading: '下载中', done: '完成',
  skipped: '已存在', failed: '失败', cancelled: '已取消',
};

// 从粘贴的文本里找漫画ID：支持纯数字和 photos-index-aid-123.html 这类网址
export function parseIds(text) {
  const ids = [];
  for (const token of text.split(/[\s,，;；]+/)) {
    const m = token.match(/aid-(\d+)/) || token.match(/^(\d+)$/);
    if (m) {
      const id = Number(m[1]);
      if (id > 0 && !ids.includes(id)) ids.push(id);
    }
  }
  return ids;
}

function shortTime(iso) {
  return iso ? iso.replace('T', ' ').slice(5, 16) : '';
}

export function mount(page) {
  page.innerHTML = `
    <div class="cards wide">
      <div class="card">
        <div class="card-head">
          <h2>下载队列</h2>
          <div class="actions">
            <button data-act="start" class="primary">开始下载</button>
            <button data-act="stop">暂停</button>
            <button data-act="retry">重试失败</button>
            <button data-act="clear">清除已完成</button>
          </div>
        </div>
        <div class="q-summary"></div>
        <div class="q-list"></div>
      </div>
      <div class="card">
        <h2>按 ID 或网址添加</h2>
        <textarea rows="4" placeholder="每行或用空格分隔一个，例如&#10;349802&#10;https://www.wn10.cfd/photos-index-aid-396779.html"></textarea>
        <div class="actions">
          <span class="note"></span>
          <button data-act="add" class="primary" disabled>加入队列</button>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>最近下载</h2><button data-act="history">刷新</button></div>
        <div class="h-list q-list"></div>
      </div>
    </div>`;

  const $ = (sel) => page.querySelector(sel);
  const summaryEl = $('.q-summary');
  const queueEl = page.querySelector('.q-list');
  const historyEl = $('.h-list');
  const textEl = $('textarea');
  const noteEl = $('.note');
  const btn = (act) => page.querySelector(`[data-act="${act}"]`);

  let historyTitles = new Map();   // 记录里的标题，用来补全队列中未知标题

  function titleOf(item) {
    return item.title || historyTitles.get(item.id) || '';
  }

  function renderQueue(job) {
    const items = job ? job.items : [];
    const c = (job && job.counts) || {};
    const finished = (c.done || 0) + (c.skipped || 0) + (c.failed || 0);
    const running = !!(job && job.running);

    btn('start').hidden = running;
    btn('start').disabled = !(job && job.pending);
    btn('stop').hidden = !running;
    btn('stop').disabled = !!(job && job.stop_requested);
    btn('retry').disabled = !((c.failed || 0) + (c.cancelled || 0));
    btn('retry').textContent = c.failed ? `重试失败 (${c.failed})` : '重试失败';
    btn('clear').disabled = !((c.done || 0) + (c.skipped || 0));

    const parts = [];
    if (items.length) {
      parts.push(`共 ${items.length} 部 · 完成 ${(c.done || 0) + (c.skipped || 0)} · 失败 ${c.failed || 0} · 等待 ${job.pending || 0}`);
    }
    if (job && job.message) parts.push(job.message);
    summaryEl.innerHTML = escapeHtml(parts.join(' — '))
      + (items.length ? `<div class="bar"><div style="width:${finished / items.length * 100}%"></div></div>` : '');

    if (!items.length) {
      queueEl.innerHTML = '<div class="q-empty">队列是空的。在搜索、书架、已导出页面勾选后点「下载选中」，或在下面粘贴 ID。</div>';
      return;
    }
    queueEl.innerHTML = items.map((item) => {
      const title = titleOf(item);
      let action = '';
      if (item.status === 'failed' || item.status === 'cancelled') {
        action = `<button data-retry="${item.id}">重试</button> <button data-remove="${item.id}">移除</button>`;
      } else if (item.status !== 'downloading') {
        action = `<button data-remove="${item.id}">移除</button>`;
      }
      const time = item.finished_at ? `<span class="q-time">${shortTime(item.finished_at)}</span>` : '';
      return `
        <div class="q-row">
          <span class="badge s-${item.status}">${STATUS_LABEL[item.status] || item.status}</span>
          <span class="q-id">#${item.id}</span>
          <span class="q-title${title ? '' : ' unknown'}" title="${escapeHtml(title)}">${escapeHtml(title || '标题未知')}${time}</span>
          <span>${action}</span>
        </div>`;
    }).join('');
  }

  async function loadHistory() {
    try {
      const records = await api('/api/download/history?limit=100');
      historyTitles = new Map(records.filter((r) => r.title).map((r) => [r.id, r.title]));
      historyEl.innerHTML = records.map((r) => `
        <div class="q-row">
          <span class="badge s-done">完成</span>
          <span class="q-id">#${r.id}</span>
          <span class="q-title${r.title ? '' : ' unknown'}" title="${escapeHtml(r.title)}">${escapeHtml(r.title || '标题未知')}</span>
          <span class="q-time">${shortTime(r.downloaded_at)}</span>
        </div>`).join('') || '<div class="q-empty">还没有下载记录</div>';
      renderQueue(status.job);
    } catch (err) {
      historyEl.innerHTML = `<div class="q-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  async function run(action, body, done) {
    try {
      const res = await queueAction(action, body);
      if (done) done(res);
    } catch (err) {
      toast(err.message);
    }
  }

  btn('start').addEventListener('click', () => run('start'));
  btn('stop').addEventListener('click', () => stopDownload().catch((err) => toast(err.message)));
  btn('retry').addEventListener('click', () => run('retry', {}, (res) => toast(`已重新排队 ${res.retried} 部`)));
  btn('clear').addEventListener('click', () => run('clear', {}, (res) => toast(`已清除 ${res.cleared} 条`)));
  btn('history').addEventListener('click', loadHistory);

  queueEl.addEventListener('click', (e) => {
    const retry = e.target.closest('[data-retry]');
    const remove = e.target.closest('[data-remove]');
    if (retry) run('retry', { ids: [Number(retry.dataset.retry)] });
    if (remove) run('remove', { ids: [Number(remove.dataset.remove)] });
  });

  textEl.addEventListener('input', () => {
    const ids = parseIds(textEl.value);
    noteEl.textContent = textEl.value.trim() ? `识别到 ${ids.length} 个漫画 ID` : '';
    btn('add').disabled = !ids.length;
  });

  btn('add').addEventListener('click', async () => {
    const ids = parseIds(textEl.value);
    if (!ids.length) return;
    try {
      const added = await startDownload(ids.map((id) => ({ id, title: historyTitles.get(id) || '' })));
      const skipped = ids.length - added;
      toast(`已加入下载队列 ${added} 部${skipped ? `（${skipped} 部已在队列中）` : ''}`);
      textEl.value = '';
      noteEl.textContent = '';
      btn('add').disabled = true;
    } catch (err) {
      toast(err.message);
    }
  });

  const offJob = onJob((job, prev) => {
    renderQueue(job);
    if (prev && prev.running && !job.running) loadHistory();
  });

  renderQueue(status.job);
  loadHistory();
  return offJob;
}
