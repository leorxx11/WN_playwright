// 下载：队列管理、按ID/网址添加

import { escapeHtml, toast } from '../util.js';
import {
  onJob, onUnsorted, queueAction, quotaWarning, startDownload, status, stopDownload,
} from '../status.js';

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
        <div class="q-quota"></div>
        <div class="q-summary"></div>
        <div class="q-nudge" hidden></div>
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
    </div>`;

  const $ = (sel) => page.querySelector(sel);
  const summaryEl = $('.q-summary');
  const quotaEl = $('.q-quota');
  const nudgeEl = $('.q-nudge');
  const queueEl = page.querySelector('.q-list');
  const textEl = $('textarea');
  const noteEl = $('.note');
  const btn = (act) => page.querySelector(`[data-act="${act}"]`);

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
    summaryEl.classList.toggle('bad', !!(job && job.quota_blocked));
    summaryEl.innerHTML = escapeHtml(parts.join(' — '))
      + (items.length ? `<div class="bar"><div style="width:${finished / items.length * 100}%"></div></div>` : '');
    renderQuota(job);
    renderNudge();

    if (!items.length) {
      queueEl.innerHTML = '<div class="q-empty">队列是空的。在「找漫画」里勾选后点「下载选中」，或在下面粘贴 ID。</div>';
      return;
    }
    queueEl.innerHTML = items.map((item) => {
      const title = item.title;
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
          <span class="q-title${title ? '' : ' unknown'}" title="${escapeHtml(title)}">${escapeHtml(title || '标题未知')}${time}${
            item.source ? `<span class="q-source">${escapeHtml(item.source)}</span>` : ''}</span>
          <span>${action}</span>
        </div>`;
    }).join('');
  }

  // 站点限制每个 IP 24 小时下载 100 个；这里按本机下载记录估算
  function renderQuota(job) {
    const q = job && job.quota;
    if (!q) {
      quotaEl.textContent = '';
      return;
    }
    const level = job.quota_blocked || !q.remaining ? 'bad' : q.remaining < 20 ? 'warn' : '';
    let free = q.next_free_at ? `，${shortTime(q.next_free_at)} 起恢复` : '';
    // 本机记录没用完但站点说用完了：同一个 IP 上可能还有别的设备在下载
    if (job.quota_blocked && q.remaining) free += ' · 站点已提示用完，可能同一 IP 还有别处在下载';
    quotaEl.className = `q-quota ${level}`;
    quotaEl.innerHTML = `<span class="meter"><span style="width:${Math.min(100, q.used / q.limit * 100)}%"></span></span>`
      + `近 24 小时已下载 <b>${q.used}</b> / ${q.limit}（站点每个 IP 的上限）· 还能下 ${q.remaining} 部${free}`;
  }

  function renderNudge() {
    const n = status.unsorted;
    const running = !!(status.job && status.job.running);
    nudgeEl.hidden = running || !n;
    nudgeEl.innerHTML = n ? `downloads 里有 ${n} 个文件待整理 · <a href="#/classify">去整理</a>` : '';
  }

  async function run(action, body, done) {
    try {
      const res = await queueAction(action, body);
      if (done) done(res);
    } catch (err) {
      toast(err.message);
    }
  }

  btn('start').addEventListener('click', () => {
    const quota = quotaWarning(0);
    if (quota && !confirm(`${quota}\n\n仍然开始下载？`)) return;
    run('start');
  });
  btn('stop').addEventListener('click', () => stopDownload().catch((err) => toast(err.message)));
  btn('retry').addEventListener('click', () => run('retry', {}, (res) => toast(`已重新排队 ${res.retried} 部`)));
  btn('clear').addEventListener('click', () => run('clear', {}, (res) => toast(`已清除 ${res.cleared} 条`)));

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
    const quota = quotaWarning(ids.length);
    if (quota && !confirm(`${quota}\n\n仍然加入队列？`)) return;
    try {
      const added = await startDownload(ids.map((id) => ({ id, title: '', source: '手动添加' })));
      const skipped = ids.length - added;
      toast(`已加入下载队列 ${added} 部${skipped ? `（${skipped} 部已在队列中）` : ''}`);
      textEl.value = '';
      noteEl.textContent = '';
      btn('add').disabled = true;
    } catch (err) {
      toast(err.message);
    }
  });

  const offJob = onJob(renderQueue);
  const offUnsorted = onUnsorted(renderNudge);

  renderQueue(status.job);
  return () => {
    offJob();
    offUnsorted();
  };
}
