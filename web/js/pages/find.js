// 找漫画：左侧选来源（搜索 / 追更 / 书架），右侧同一个勾选列表直接下载

import { api, escapeHtml, toast } from '../util.js';
import { createComicList } from '../comic-list.js';
import { followJob, progressText } from '../fetch-job.js';

const TYPE_NAME = { keyword: '关键词', tag: '标签' };
// 追更状态：只有追更中的参与「全部刷新」
const STATUS_NAME = { active: '追更中', paused: '暂停', finished: '已完结' };
const STATUS_ORDER = Object.keys(STATUS_NAME);
const sortFollows = (list) => [...list].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status));

// 切换页面后回来保留状态；后台任务（搜索、刷新追更、读取书架）切走也会继续
const cache = {
  source: { kind: 'search' },   // { kind: 'search' } | { kind: 'follow', id } | { kind: 'shelf', id }
  search: { type: 'keyword', query: '', maxPages: 20, jobId: null, items: null, running: false },
  follows: null,                // 追更摘要列表
  followItems: new Map(),       // 追更id -> 列表
  followJobs: new Map(),        // 正在刷新的追更id -> jobId
  refreshingAll: false,
  shelves: null,
  shelfItems: new Map(),        // 书架id -> 列表
  shelfJob: null,               // { id, jobId }
};

function shortTime(iso) {
  return iso ? iso.replace('T', ' ').slice(5, 16) : '从未刷新';
}

function errorHtml(err) {
  const link = err.status === 401 ? ' <a href="#/account">去账号页</a>' : '';
  return `${escapeHtml(err.message)}${link}`;
}

export function mount(page) {
  page.innerHTML = `
    <div class="split find">
      <aside class="subnav">
        <ul class="src-search"><li data-src="search"><div class="s-label">搜索</div><div class="s-meta">关键词或标签</div></li></ul>
        <div class="subnav-head"><h2>追更</h2><button class="refresh-follows">全部刷新</button></div>
        <ul class="src-follows"></ul>
        <div class="subnav-head"><h2>书架</h2><button class="refresh-shelves" title="重新读取书架列表">刷新</button></div>
        <ul class="src-shelves"></ul>
      </aside>
      <section>
        <div class="src-head"></div>
        <div class="list-host"></div>
      </section>
    </div>`;

  const $ = (sel) => page.querySelector(sel);
  const headEl = $('.src-head');
  const followsEl = $('.src-follows');
  const shelvesEl = $('.src-shelves');
  const refreshAllBtn = $('.refresh-follows');

  const followers = new Set();   // 本页在轮询的任务，卸载时停止轮询
  let headRefs = {};             // 当前来源头部里的元素

  const list = createComicList($('.list-host'), {
    source: sourceLabel,
    onAuthor: (name) => {
      Object.assign(cache.search, { type: 'keyword', query: name });
      select({ kind: 'search' });
      runSearch();
    },
  });

  function watch(jobId, onProgress) {
    const f = followJob(jobId, onProgress);
    followers.add(f);
    f.promise.finally(() => followers.delete(f)).catch(() => {});
    return f;
  }

  const isCurrent = (kind, id) => cache.source.kind === kind && (id === undefined || cache.source.id === id);
  const currentFollow = () => (cache.follows || []).find((f) => f.id === cache.source.id);
  const currentShelf = () => (cache.shelves || []).find((s) => s.id === cache.source.id);

  function sourceLabel() {
    const src = cache.source;
    if (src.kind === 'follow') return `追更：${currentFollow()?.query || ''}`;
    if (src.kind === 'shelf') return `书架：${currentShelf()?.name || src.id}`;
    return cache.search.query ? `搜索：${cache.search.query}` : '';
  }

  function setStatus(text, { bad = false, html = false } = {}) {
    const el = headRefs.status;
    if (!el) return;
    el.className = `pb-status${bad ? ' bad' : ''}`;
    if (html) el.innerHTML = text; else el.textContent = text;
  }

  /* ---------- 左侧来源 ---------- */

  function renderSources() {
    page.querySelector('[data-src="search"]').classList.toggle('active', isCurrent('search'));

    if (!cache.follows) {
      followsEl.innerHTML = '<li class="s-empty">读取中…</li>';
    } else {
      followsEl.innerHTML = cache.follows.map((f) => {
        const refreshing = cache.followJobs.has(f.id);
        const fresh = f.undownloaded ? `<span class="s-new">${f.undownloaded} 部未下载</span>` : '';
        const state = f.status === 'active' ? '' : `<span class="s-status">${STATUS_NAME[f.status]}</span>`;
        const classes = [isCurrent('follow', f.id) ? 'active' : '', `f-${f.status}`].join(' ');
        return `
          <li data-follow="${f.id}" class="${classes}">
            <div class="s-label">${escapeHtml(f.query)}${fresh}</div>
            <div class="s-meta">${state}${TYPE_NAME[f.type]} · ${f.total} 部 · ${refreshing ? '刷新中…' : shortTime(f.checked_at)}</div>
          </li>`;
      }).join('') || '<li class="s-empty">搜索后点「追更这个搜索」，以后一键看有没有新的</li>';
    }
    const activeCount = (cache.follows || []).filter((f) => f.status === 'active').length;
    refreshAllBtn.disabled = cache.refreshingAll || !activeCount;
    refreshAllBtn.title = `依次重新搜索 ${activeCount} 个追更中的（暂停、已完结的不刷新）`;
    if (!cache.refreshingAll) refreshAllBtn.textContent = '全部刷新';

    if (!cache.shelves) {
      shelvesEl.innerHTML = '<li class="s-empty">读取中…</li>';
    } else {
      shelvesEl.innerHTML = cache.shelves.map((s) => `
        <li data-shelf="${s.id}" class="${isCurrent('shelf', s.id) ? 'active' : ''}">
          <div class="s-label">${escapeHtml(s.name || `书架 ${s.id}`)}</div>
          <div class="s-meta">${s.id === 0 ? '所有收藏' : `ID ${s.id}`}</div>
        </li>`).join('') || '<li class="s-empty">没有书架</li>';
    }
  }

  async function loadFollows() {
    try {
      cache.follows = sortFollows(await api('/api/follows'));
    } catch (err) {
      followsEl.innerHTML = `<li class="s-empty">${errorHtml(err)}</li>`;
      return;
    }
    renderSources();
    if (isCurrent('follow')) renderHead();
  }

  async function loadShelves() {
    cache.shelves = null;
    renderSources();
    try {
      cache.shelves = await api('/api/shelves');
    } catch (err) {
      shelvesEl.innerHTML = `<li class="s-empty">${errorHtml(err)}</li>`;
      return;
    }
    renderSources();
  }

  function select(source) {
    cache.source = source;
    renderSources();
    renderHead();
    showItems();
  }

  /* ---------- 右侧头部 ---------- */

  function renderHead() {
    const src = cache.source;
    if (src.kind === 'search') renderSearchHead();
    else if (src.kind === 'follow') renderFollowHead();
    else renderShelfHead();
  }

  function segHtml(type) {
    return `<div class="seg" role="group" aria-label="搜索类型">${
      ['keyword', 'tag'].map((t) => `<button data-type="${t}" aria-pressed="${t === type}">${TYPE_NAME[t]}</button>`).join('')
    }</div>`;
  }

  function renderSearchHead() {
    const s = cache.search;
    headEl.innerHTML = `
      <div class="pagebar">
        ${segHtml(s.type)}
        <input class="q" type="text" autocomplete="off" value="${escapeHtml(s.query)}"
          placeholder="${s.type === 'tag' ? '输入标签（需与站点标签完全一致），回车搜索' : '输入关键词，回车搜索'}">
        <label>最多 <input class="pages" type="number" min="1" max="100" value="${s.maxPages}"> 页</label>
        <button class="go primary">搜索</button>
        <button class="cancel" hidden>取消</button>
        <button class="follow-btn" hidden>追更这个搜索</button>
        <div class="pb-status"></div>
      </div>`;
    headRefs = {
      query: headEl.querySelector('.q'),
      pages: headEl.querySelector('.pages'),
      go: headEl.querySelector('.go'),
      cancel: headEl.querySelector('.cancel'),
      followBtn: headEl.querySelector('.follow-btn'),
      status: headEl.querySelector('.pb-status'),
    };
    headEl.querySelectorAll('[data-type]').forEach((b) => b.addEventListener('click', () => {
      s.type = b.dataset.type;
      s.query = headRefs.query.value;
      renderSearchHead();
    }));
    headRefs.go.addEventListener('click', () => { s.query = headRefs.query.value; runSearch(); });
    headRefs.query.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        s.query = headRefs.query.value;
        runSearch();
      }
    });
    headRefs.cancel.addEventListener('click', () => api(`/api/jobs/${s.jobId}/cancel`, { method: 'POST' }).catch((err) => toast(err.message)));
    headRefs.followBtn.addEventListener('click', followSearch);
    updateSearchHead();
    if (!s.query) headRefs.query.focus();
  }

  function updateSearchHead(job) {
    const s = cache.search;
    if (!isCurrent('search') || !headRefs.go) return;
    headRefs.go.disabled = s.running;
    headRefs.cancel.hidden = !s.running;
    const followed = (cache.follows || []).find((f) => f.type === s.type && f.query === s.query.trim());
    headRefs.followBtn.hidden = s.running || !s.items;
    headRefs.followBtn.disabled = !!followed;
    headRefs.followBtn.textContent = followed ? '已在追更' : '追更这个搜索';
    if (job && job.state === 'running') setStatus(progressText(job, '搜索'));
    else if (s.items) setStatus(`「${s.query}」共 ${s.items.length} 部`);
  }

  function renderFollowHead() {
    const f = currentFollow();
    if (!f) {
      headEl.innerHTML = '<div class="pagebar"><div class="pb-status">追更不存在</div></div>';
      headRefs = {};
      return;
    }
    const refreshing = cache.followJobs.has(f.id);
    headEl.innerHTML = `
      <div class="pagebar">
        <span class="f-title">${escapeHtml(f.query)}</span>
        <div class="seg f-status" role="group" aria-label="追更状态">${
          STATUS_ORDER.map((st) => `<button data-status="${st}" aria-pressed="${st === f.status}">${STATUS_NAME[st]}</button>`).join('')
        }</div>
        ${segHtml(f.type)}
        <label>最多 <input class="pages" type="number" min="1" max="100" value="${f.max_pages}"> 页</label>
        <button class="f-refresh primary"${refreshing ? ' disabled' : ''}>${refreshing ? '刷新中…' : '刷新'}</button>
        <button class="cancel"${refreshing ? '' : ' hidden'}>取消</button>
        <label class="f-folder-wrap" title="下载后在「整理」页会默认放进这个文件夹">整理到 class/
          <input class="f-folder" type="text" value="${escapeHtml(f.folder)}" placeholder="不指定" spellcheck="false"></label>
        <button class="f-delete">取消追更</button>
        <div class="pb-status"></div>
      </div>`;
    headRefs = { status: headEl.querySelector('.pb-status') };
    const finale = f.has_finale && f.status !== 'finished'
      ? ' · 结果里有「完結」，<button class="link-btn f-finish">标记为已完结</button>' : '';
    setStatus(`上次刷新 ${escapeHtml(shortTime(f.checked_at))} · 共 ${f.total} 部 · 未下载 ${f.undownloaded} 部${finale}`, { html: true });

    const patch = async (body) => {
      try {
        Object.assign(f, await api(`/api/follows/${f.id}`, { method: 'PATCH', body: JSON.stringify(body) }));
        renderSources();
        return true;
      } catch (err) {
        toast(err.message);
        return false;
      }
    };
    const setFollowStatus = async (st) => {
      if (st === f.status || !await patch({ status: st })) return;
      cache.follows = sortFollows(cache.follows);
      renderSources();
      renderFollowHead();
      toast(st === 'active' ? '已恢复追更，「全部刷新」会刷新它' : `已设为${STATUS_NAME[st]}，「全部刷新」时跳过`);
    };
    headEl.querySelectorAll('[data-status]').forEach((b) => b.addEventListener('click', () => setFollowStatus(b.dataset.status)));
    headEl.querySelector('.f-finish')?.addEventListener('click', () => setFollowStatus('finished'));
    headEl.querySelectorAll('[data-type]').forEach((b) => b.addEventListener('click', async () => {
      if (b.dataset.type !== f.type && await patch({ type: b.dataset.type })) {
        renderFollowHead();
        toast('已修改，点「刷新」按新的方式重新搜索');
      }
    }));
    headEl.querySelector('.pages').addEventListener('change', (e) => {
      patch({ max_pages: Math.min(100, Math.max(1, Number(e.target.value) || 20)) });
    });
    const folderEl = headEl.querySelector('.f-folder');
    folderEl.addEventListener('change', async () => {
      if (await patch({ folder: folderEl.value })) {
        toast(f.folder ? `下载后整理时默认放进 class/${f.folder}/` : '已取消整理文件夹');
      }
    });
    folderEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') folderEl.blur(); });
    headEl.querySelector('.f-refresh').addEventListener('click', () => refreshFollow(f.id).catch(() => {}));
    headEl.querySelector('.cancel').addEventListener('click', () => {
      const jobId = cache.followJobs.get(f.id);
      if (jobId) api(`/api/jobs/${jobId}/cancel`, { method: 'POST' }).catch((err) => toast(err.message));
    });
    headEl.querySelector('.f-delete').addEventListener('click', async () => {
      if (!confirm(`取消追更「${f.query}」？已下载的文件不受影响。`)) return;
      try {
        await api(`/api/follows/${f.id}`, { method: 'DELETE' });
      } catch (err) {
        toast(err.message);
        return;
      }
      cache.follows = cache.follows.filter((x) => x.id !== f.id);
      cache.followItems.delete(f.id);
      select({ kind: 'search' });
    });
  }

  function renderShelfHead() {
    const shelf = currentShelf();
    const name = shelf ? shelf.name || `书架 ${shelf.id}` : `书架 ${cache.source.id}`;
    const loading = cache.shelfJob && cache.shelfJob.id === cache.source.id;
    headEl.innerHTML = `
      <div class="pagebar">
        <span class="f-title">${escapeHtml(name)}</span>
        <button class="s-reload">重新读取</button>
        <button class="cancel"${loading ? '' : ' hidden'}>取消</button>
        <div class="pb-status"></div>
      </div>`;
    headRefs = { status: headEl.querySelector('.pb-status') };
    const items = cache.shelfItems.get(cache.source.id);
    if (items) setStatus(`共 ${items.length} 部`);
    headEl.querySelector('.s-reload').addEventListener('click', () => openShelf(cache.source.id, true));
    headEl.querySelector('.cancel').addEventListener('click', () => {
      api(`/api/jobs/${cache.shelfJob.jobId}/cancel`, { method: 'POST' }).catch((err) => toast(err.message));
    });
  }

  /* ---------- 列表内容 ---------- */

  function showItems() {
    const src = cache.source;
    if (src.kind === 'search') {
      const s = cache.search;
      if (s.items) {
        list.setItems(s.items);
        list.refreshDownloaded();
      } else {
        list.clear(s.running ? '搜索中…' : '输入关键词或标签开始搜索');
      }
    } else if (src.kind === 'follow') {
      const items = cache.followItems.get(src.id);
      if (items) {
        list.setItems(items);
      } else {
        list.clear('读取中…');
        loadFollowItems(src.id);
      }
    } else {
      const items = cache.shelfItems.get(src.id);
      if (items) {
        list.setItems(items);
        list.refreshDownloaded();
      } else {
        list.clear(cache.shelfJob && cache.shelfJob.id === src.id ? '读取中…' : '');
        if (!cache.shelfJob || cache.shelfJob.id !== src.id) openShelf(src.id);
      }
    }
  }

  async function loadFollowItems(id) {
    try {
      const detail = await api(`/api/follows/${id}`);
      cache.followItems.set(id, detail.items);
      if (isCurrent('follow', id)) list.setItems(detail.items);
    } catch (err) {
      if (isCurrent('follow', id)) list.clear(err.message);
    }
  }

  /* ---------- 搜索 ---------- */

  function followSearchJob(jobId) {
    const s = cache.search;
    s.running = true;
    updateSearchHead();
    watch(jobId, (job) => updateSearchHead(job)).promise
      .then((job) => {
        s.items = job.items;
        if (isCurrent('search')) {
          list.setItems(job.items);
          if (job.state === 'cancelled') setStatus(`「${s.query}」共 ${job.items.length} 部（已取消，显示已读取的部分）`);
        }
      })
      .catch((err) => {
        s.jobId = null;
        if (isCurrent('search')) {
          list.clear('搜索失败');
          setStatus(errorHtml(err), { bad: true, html: true });
        }
      })
      .finally(() => {
        s.running = false;
        updateSearchHead();
      });
  }

  async function runSearch() {
    const s = cache.search;
    s.query = s.query.trim();
    if (!s.query) {
      headRefs.query?.focus();
      return;
    }
    if (headRefs.pages) s.maxPages = Math.min(100, Math.max(1, Number(headRefs.pages.value) || 20));
    renderSearchHead();
    s.items = null;
    list.clear('搜索中…');
    setStatus('搜索中…');
    try {
      const job = await api('/api/search', {
        method: 'POST',
        body: JSON.stringify({ query: s.query, type: s.type, max_pages: s.maxPages }),
      });
      s.jobId = job.id;
      followSearchJob(job.id);
    } catch (err) {
      list.clear('输入关键词或标签开始搜索');
      setStatus(errorHtml(err), { bad: true, html: true });
    }
  }

  async function followSearch() {
    const s = cache.search;
    try {
      const created = await api('/api/follows', {
        method: 'POST',
        body: JSON.stringify({ type: s.type, query: s.query, max_pages: s.maxPages, job_id: s.jobId }),
      });
      cache.follows = sortFollows([created, ...(cache.follows || []).filter((f) => f.id !== created.id)]);
      cache.followItems.set(created.id, s.items);
      renderSources();
      updateSearchHead();
      toast(`已追更「${s.query}」，以后在左侧点「刷新」看有没有新的`);
    } catch (err) {
      toast(err.message);
    }
  }

  /* ---------- 追更 ---------- */

  // 刷新一个追更，搜索完成后更新摘要和列表；返回 Promise
  async function refreshFollow(id) {
    let job;
    try {
      job = await api(`/api/follows/${id}/refresh`, { method: 'POST' });
    } catch (err) {
      if (isCurrent('follow', id)) setStatus(errorHtml(err), { bad: true, html: true });
      else toast(err.message);
      throw err;
    }
    return trackFollowJob(id, job.id);
  }

  function trackFollowJob(id, jobId) {
    cache.followJobs.set(id, jobId);
    renderSources();
    if (isCurrent('follow', id)) renderFollowHead();
    return watch(jobId, (job) => {
      if (isCurrent('follow', id) && job.state === 'running') setStatus(progressText(job, '刷新'));
    }).promise
      .then(async (job) => {
        if (job.state === 'cancelled') return;
        cache.followItems.set(id, job.items);
        if (isCurrent('follow', id)) list.setItems(job.items);
        await loadFollows();
      })
      .catch((err) => {
        if (isCurrent('follow', id)) setStatus(errorHtml(err), { bad: true, html: true });
        throw err;
      })
      .finally(() => {
        cache.followJobs.delete(id);
        renderSources();
        if (isCurrent('follow', id)) renderFollowHead();
      });
  }

  async function refreshAll() {
    const ids = (cache.follows || []).filter((f) => f.status === 'active').map((f) => f.id);
    cache.refreshingAll = true;
    renderSources();
    let done = 0;
    try {
      for (const id of ids) {
        refreshAllBtn.textContent = `刷新中 ${done + 1}/${ids.length}`;
        await refreshFollow(id);
        done++;
      }
      const fresh = (cache.follows || []).reduce((n, f) => n + f.undownloaded, 0);
      toast(`已刷新 ${done} 个追更中的，共 ${fresh} 部未下载`);
    } catch (err) {
      toast(`刷新到第 ${done + 1} 个时出错：${err.message}`);
    } finally {
      cache.refreshingAll = false;
      renderSources();
    }
  }

  /* ---------- 书架 ---------- */

  async function openShelf(id, reload = false) {
    if (reload) cache.shelfItems.delete(id);
    if (isCurrent('shelf', id)) {
      list.clear('读取中…');
      setStatus('读取中…');
    }
    const shelf = (cache.shelves || []).find((s) => s.id === id);
    let job;
    try {
      job = await api(`/api/shelves/${id}/fetch?name=${encodeURIComponent(shelf ? shelf.name : '')}`, { method: 'POST' });
    } catch (err) {
      if (isCurrent('shelf', id)) {
        list.clear('读取失败');
        setStatus(errorHtml(err), { bad: true, html: true });
      }
      return;
    }
    trackShelfJob(id, job.id);
  }

  function trackShelfJob(id, jobId) {
    cache.shelfJob = { id, jobId };
    if (isCurrent('shelf', id)) renderShelfHead();
    watch(jobId, (job) => {
      if (isCurrent('shelf', id) && job.state === 'running') setStatus(progressText(job, '读取'));
    }).promise
      .then((job) => {
        cache.shelfItems.set(id, job.items);
        if (isCurrent('shelf', id)) list.setItems(job.items);
      })
      .catch((err) => {
        if (isCurrent('shelf', id)) {
          list.clear('读取失败');
          setStatus(errorHtml(err), { bad: true, html: true });
        }
      })
      .finally(() => {
        if (cache.shelfJob && cache.shelfJob.jobId === jobId) cache.shelfJob = null;
        if (isCurrent('shelf', id)) renderShelfHead();
      });
  }

  /* ---------- 事件 ---------- */

  page.querySelector('.subnav').addEventListener('click', (e) => {
    const li = e.target.closest('li');
    if (!li) return;
    if (li.dataset.src === 'search') select({ kind: 'search' });
    else if (li.dataset.follow) select({ kind: 'follow', id: li.dataset.follow });
    else if (li.dataset.shelf !== undefined) select({ kind: 'shelf', id: Number(li.dataset.shelf) });
  });
  refreshAllBtn.addEventListener('click', refreshAll);
  $('.refresh-shelves').addEventListener('click', loadShelves);

  // 恢复上次的状态，并继续跟进切走时还在跑的任务
  renderSources();
  renderHead();
  showItems();
  if (cache.search.jobId && cache.search.running) followSearchJob(cache.search.jobId);
  for (const [id, jobId] of cache.followJobs) trackFollowJob(id, jobId).catch(() => {});
  if (cache.shelfJob) trackShelfJob(cache.shelfJob.id, cache.shelfJob.jobId);
  loadFollows();
  if (!cache.shelves) loadShelves();

  return () => {
    followers.forEach((f) => f.detach());
    list.destroy();
  };
}
