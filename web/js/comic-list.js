// 共用的漫画勾选列表：找漫画页的搜索、追更、书架都用它
//
// const list = createComicList(host, { source, onAuthor })
//   list.setItems(comics)        替换列表并清空勾选
//   list.updateItems(comics)     按id更新已下载等字段，保留勾选
//   list.selectedItems()         按列表顺序返回勾选的漫画
//   list.refreshDownloaded()     重新查询已下载标记
//   list.clear(text)             清空列表并显示提示
//   list.destroy()               页面卸载时调用
// source: () => string            加入下载队列时记录来源，如「追更：玩轉學姊」
// onAuthor: (name) => void        标题以 [作者] 开头时显示「搜作者」，点击时调用

import { api, escapeHtml, normalize, storageGet, storageSet, toast } from './util.js';
import { jobStatusMap, onJob, quotaWarning, startDownload, status as globalStatus, stopDownload } from './status.js';

const STATUS_LABEL = {
  pending: '等待', downloading: '下载中', done: '完成',
  skipped: '已存在', failed: '失败', cancelled: '未下载',
};

// 标题开头的 [作者]（可带 (C102) 这类前缀）；有多个方括号时取最后一个，如 [汉化组][作者]
export function titleAuthor(title) {
  let rest = title.trim().replace(/^\([^)]*\)\s*/, '');
  let author = '';
  let m;
  while ((m = rest.match(/^\[([^\]]+)\]\s*/))) {
    author = m[1].trim();
    rest = rest.slice(m[0].length);
  }
  return author;
}

export function createComicList(host, {
  emptyText = '没有漫画', noItemsText = '列表是空的', source = () => '', onAuthor = null,
} = {}) {
  host.innerHTML = `
    <div class="cl">
      <div class="cl-toolbar">
        <input class="cl-filter" type="text" placeholder="筛选：空格分隔都要包含，-开头排除，如  學姊 -漢化" autocomplete="off">
        <input class="cl-chapter" type="text" placeholder="话数 100-128" autocomplete="off">
        <span class="sep"></span>
        <div class="group">
          <button data-bulk="all" title="快捷键 a">全选</button>
          <button data-bulk="none">全不选</button>
          <button data-bulk="invert" title="快捷键 i">反选</button>
          <button data-bulk="undownloaded" title="快捷键 u">只选未下载</button>
        </div>
        <span class="sep"></span>
        <div class="group">
          <button class="toggle" data-toggle="hideDl" aria-pressed="false">隐藏已下载</button>
          <button class="toggle" data-toggle="cover" aria-pressed="true">封面</button>
        </div>
      </div>
      <div class="cl-hint">
        点行切换 · 按住拖动连续切换 · <kbd>Shift</kbd>+点击选一段 ·
        <kbd>j</kbd>/<kbd>k</kbd> 移动 <kbd>空格</kbd> 切换 <kbd>a</kbd> 全选 <kbd>i</kbd> 反选 <kbd>u</kbd> 只选未下载 <kbd>/</kbd> 筛选 ·
        批量按钮只作用于当前显示的行
      </div>
      <div class="cl-list"></div>
      <div class="cl-foot">
        <div class="cl-counts"></div>
        <div class="cl-actions"></div>
      </div>
    </div>`;

  const $ = (sel) => host.querySelector(sel);
  const listEl = $('.cl-list');
  const filterEl = $('.cl-filter');
  const chapterEl = $('.cl-chapter');

  const state = {
    items: [],
    byId: new Map(),
    selected: new Set(),
    visible: [],      // 当前显示的漫画ID（按列表顺序）
    cursor: -1,       // visible中的下标
    anchorId: null,   // Shift范围选择的起点
    drag: null,       // { on, lastIdx }
    hideDownloaded: storageGet('wn.hideDl') === '1',
    showCover: storageGet('wn.cover') !== '0',
    loaded: false,
    jobStatus: jobStatusMap(),
  };

  /* ---------- 底栏按钮 ---------- */

  const builtinActions = [
    { key: 'selectFailed', label: () => '勾选失败项', onClick: selectFailed, always: true },
    { key: 'stop', label: () => '停止下载', onClick: () => stopDownload().catch((e) => toast(e.message)), always: true },
    { key: 'download', label: (n) => (globalStatus.job && globalStatus.job.running ? `加入下载 (${n})` : `下载选中 (${n})`), primary: true, onClick: downloadSelected },
  ];
  $('.cl-actions').innerHTML = builtinActions
    .map((a, i) => `<button data-action="${i}" class="${a.primary ? 'primary' : ''}"></button>`).join('');
  const actionButtons = [...host.querySelectorAll('[data-action]')];
  actionButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = builtinActions[Number(btn.dataset.action)];
      action.onClick(selectedItems());
    });
  });

  async function downloadSelected(items) {
    if (!items.length) return;
    const visibleSet = new Set(state.visible);
    const hidden = items.filter((c) => !visibleSet.has(c.id)).length;
    const note = hidden ? `\n其中 ${hidden} 部被筛选隐藏，也会一起下载。` : '';
    const running = !!(globalStatus.job && globalStatus.job.running);
    const quota = quotaWarning(items.length);
    const question = (running
      ? `把 ${items.length} 部加入下载队列？会排在当前任务后面。${note}`
      : `开始下载 ${items.length} 部？下载时会打开浏览器窗口。${note}`)
      + (quota ? `\n\n⚠ ${quota}` : '');
    if (!confirm(question)) return;
    try {
      const from = source();
      const added = await startDownload(items.map((c) => ({ id: c.id, title: c.title, source: from })));
      const skipped = items.length - added;
      toast(`已加入下载队列 ${added} 部${skipped ? `（${skipped} 部已在队列中）` : ''}`);
    } catch (err) {
      toast(err.message);
    }
  }

  function failedIdsInList() {
    const job = globalStatus.job;
    if (!job || job.running) return [];
    return job.items.filter((i) => i.status === 'failed' && state.byId.has(i.id)).map((i) => i.id);
  }

  function selectFailed() {
    const failed = new Set(failedIdsInList());
    for (const c of state.items) setSelected(c.id, failed.has(c.id));
    updateFooter();
    toast(`已勾选 ${failed.size} 个失败项`);
  }

  /* ---------- 筛选与渲染 ---------- */

  function parseChapterRange() {
    const text = chapterEl.value.trim();
    chapterEl.classList.remove('invalid');
    if (!text) return null;
    const m = text.match(/^(\d+)\s*(?:[-~～]\s*(\d+))?$/);
    if (!m) {
      chapterEl.classList.add('invalid');
      return null;
    }
    const lo = Number(m[1]);
    const hi = m[2] ? Number(m[2]) : lo;
    return [Math.min(lo, hi), Math.max(lo, hi)];
  }

  function applyFilter() {
    const tokens = normalize(filterEl.value).split(/\s+/).filter(Boolean);
    const include = tokens.filter((t) => !t.startsWith('-'));
    const exclude = tokens.filter((t) => t.startsWith('-') && t.length > 1).map((t) => t.slice(1));
    const range = parseChapterRange();

    state.visible = state.items.filter((c) => {
      if (state.hideDownloaded && c.downloaded) return false;
      if (range) {
        if (c.chapter_start == null || c.chapter_end < range[0] || c.chapter_start > range[1]) return false;
      }
      if (include.length || exclude.length) {
        const hay = normalize(`${c.title} ${c.id} ${c.info}`);
        if (!include.every((t) => hay.includes(t))) return false;
        if (exclude.some((t) => hay.includes(t))) return false;
      }
      return true;
    }).map((c) => c.id);

    if (state.cursor >= state.visible.length) state.cursor = state.visible.length - 1;
    renderList();
  }

  function badgesHtml(c) {
    let html = c.downloaded ? '<span class="badge b-dl">已下载</span>' : '';
    const s = state.jobStatus.get(c.id);
    if (s) html += `<span class="badge s-${s}">${STATUS_LABEL[s] || s}</span>`;
    return html;
  }

  function rowHtml(c, idx) {
    const classes = ['row'];
    const on = state.selected.has(c.id);
    if (on) classes.push('sel');
    if (c.downloaded) classes.push('dl');
    if (idx === state.cursor) classes.push('cursor');
    const chapter = c.chapter_start == null ? ''
      : `<span class="b-chapter">${c.chapter_start === c.chapter_end ? c.chapter_start : `${c.chapter_start}-${c.chapter_end}`} 话</span>`;
    const author = onAuthor ? titleAuthor(c.title) : '';
    const authorLink = author
      ? `<span class="author-link" data-author="${escapeHtml(author)}" title="搜索这个作者的其他作品">搜作者：${escapeHtml(author)}</span>`
      : '';
    const cover = state.showCover && c.cover
      ? `<img class="cover" loading="lazy" alt="" src="/api/cover?url=${encodeURIComponent(c.cover)}">`
      : '';
    return `
      <div class="${classes.join(' ')}" data-id="${c.id}" role="checkbox" aria-checked="${on}">
        <span class="cb"></span>
        ${cover}
        <div class="main-col">
          <div class="title" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</div>
          <div class="meta"><span>#${c.id}</span>${chapter}<span>${escapeHtml(c.info)}</span>${authorLink}</div>
        </div>
        <div class="badges">${badgesHtml(c)}</div>
      </div>`;
  }

  function renderList() {
    if (!state.loaded) {
      listEl.innerHTML = `<div class="cl-empty">${escapeHtml(emptyText)}</div>`;
    } else if (!state.items.length) {
      listEl.innerHTML = `<div class="cl-empty">${escapeHtml(noItemsText)}</div>`;
    } else if (!state.visible.length) {
      listEl.innerHTML = '<div class="cl-empty">没有符合筛选条件的漫画</div>';
    } else {
      listEl.innerHTML = state.visible.map((id, idx) => rowHtml(state.byId.get(id), idx)).join('');
    }
    updateFooter();
  }

  function rowEl(id) {
    return listEl.querySelector(`.row[data-id="${id}"]`);
  }

  function updateFooter() {
    const total = state.items.length;
    const sel = state.selected.size;
    const visibleSet = new Set(state.visible);
    let hiddenSel = 0;
    for (const id of state.selected) if (!visibleSet.has(id)) hiddenSel++;
    const downloaded = state.items.filter((c) => c.downloaded).length;

    $('.cl-counts').innerHTML = state.loaded
      ? `已选 <b>${sel}</b> / ${total} · 显示 ${state.visible.length} · 已下载 ${downloaded}`
        + (hiddenSel ? ` <span class="note">（${hiddenSel} 项已选但被筛选隐藏）</span>` : '')
      : '';

    const job = globalStatus.job;
    const running = !!(job && job.running);
    actionButtons.forEach((btn) => {
      const action = builtinActions[Number(btn.dataset.action)];
      btn.textContent = action.label(sel);
      if (action.key === 'selectFailed') {
        btn.hidden = !failedIdsInList().length;
      } else if (action.key === 'stop') {
        btn.hidden = !running;
        btn.disabled = !!(job && job.stop_requested);
      } else {
        btn.disabled = !sel;
      }
    });
  }

  /* ---------- 勾选 ---------- */

  function setSelected(id, on) {
    if (on) state.selected.add(id); else state.selected.delete(id);
    const el = rowEl(id);
    if (el) {
      el.classList.toggle('sel', on);
      el.setAttribute('aria-checked', String(on));
    }
  }

  function setRange(fromIdx, toIdx, on) {
    const [a, b] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx];
    for (let i = a; i <= b; i++) setSelected(state.visible[i], on);
  }

  function setCursor(idx, scroll = true) {
    const prev = state.visible[state.cursor];
    if (prev != null) rowEl(prev)?.classList.remove('cursor');
    state.cursor = idx;
    const el = rowEl(state.visible[idx]);
    if (el) {
      el.classList.add('cursor');
      if (scroll) el.scrollIntoView({ block: 'nearest' });
    }
  }

  function bulk(kind) {
    for (const id of state.visible) {
      const c = state.byId.get(id);
      if (kind === 'all') setSelected(id, true);
      else if (kind === 'none') setSelected(id, false);
      else if (kind === 'invert') setSelected(id, !state.selected.has(id));
      else if (kind === 'undownloaded') setSelected(id, !c.downloaded);
    }
    updateFooter();
  }

  listEl.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    const authorEl = e.target.closest('.author-link');
    if (authorEl) {
      // 点作者名去搜索，不切换勾选
      e.preventDefault();
      onAuthor(authorEl.dataset.author);
      return;
    }
    const row = e.target.closest('.row');
    if (!row) return;
    e.preventDefault();
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();

    const id = Number(row.dataset.id);
    const idx = state.visible.indexOf(id);
    const anchorIdx = state.anchorId == null ? -1 : state.visible.indexOf(state.anchorId);

    if (e.shiftKey && anchorIdx >= 0) {
      setRange(anchorIdx, idx, state.selected.has(state.anchorId));
    } else {
      const on = !state.selected.has(id);
      setSelected(id, on);
      state.anchorId = id;
      state.drag = { on, lastIdx: idx };
    }
    setCursor(idx, false);
    updateFooter();
  });

  listEl.addEventListener('mouseover', (e) => {
    if (!state.drag) return;
    const row = e.target.closest('.row');
    if (!row) return;
    const idx = state.visible.indexOf(Number(row.dataset.id));
    if (idx < 0 || idx === state.drag.lastIdx) return;
    // 鼠标移动过快会跳过中间行，按区间补齐
    setRange(state.drag.lastIdx, idx, state.drag.on);
    state.drag.lastIdx = idx;
    setCursor(idx, false);
    updateFooter();
  });

  const onMouseUp = () => { state.drag = null; };
  window.addEventListener('mouseup', onMouseUp);

  listEl.addEventListener('error', (e) => {
    if (e.target.tagName === 'IMG') e.target.classList.add('broken');
  }, true);

  host.querySelectorAll('[data-bulk]').forEach((btn) => {
    btn.addEventListener('click', () => bulk(btn.dataset.bulk));
  });

  const onKeyDown = (e) => {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      if (e.key === 'Escape' || (e.key === 'Enter' && host.contains(e.target))) e.target.blur();
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey || !state.loaded) return;

    const n = state.visible.length;
    switch (e.key) {
      case 'j':
      case 'ArrowDown':
        if (n) setCursor(Math.min(n - 1, state.cursor + 1));
        break;
      case 'k':
      case 'ArrowUp':
        if (n) setCursor(Math.max(0, state.cursor - 1));
        break;
      case ' ':
      case 'x':
        if (state.cursor >= 0) {
          const id = state.visible[state.cursor];
          setSelected(id, !state.selected.has(id));
          state.anchorId = id;
          updateFooter();
        }
        break;
      case 'a': bulk('all'); break;
      case 'i': bulk('invert'); break;
      case 'u': bulk('undownloaded'); break;
      case '/': filterEl.focus(); break;
      default: return;
    }
    e.preventDefault();
  };
  document.addEventListener('keydown', onKeyDown);

  /* ---------- 开关 ---------- */

  filterEl.addEventListener('input', applyFilter);
  chapterEl.addEventListener('input', applyFilter);

  const hideBtn = $('[data-toggle="hideDl"]');
  const coverBtn = $('[data-toggle="cover"]');
  hideBtn.setAttribute('aria-pressed', String(state.hideDownloaded));
  coverBtn.setAttribute('aria-pressed', String(state.showCover));

  hideBtn.addEventListener('click', () => {
    state.hideDownloaded = !state.hideDownloaded;
    hideBtn.setAttribute('aria-pressed', String(state.hideDownloaded));
    storageSet('wn.hideDl', state.hideDownloaded ? '1' : '0');
    applyFilter();
  });

  coverBtn.addEventListener('click', () => {
    state.showCover = !state.showCover;
    coverBtn.setAttribute('aria-pressed', String(state.showCover));
    storageSet('wn.cover', state.showCover ? '1' : '0');
    renderList();
  });

  /* ---------- 下载状态 ---------- */

  async function refreshDownloaded() {
    if (!state.items.length) return;
    try {
      const flags = await api('/api/downloaded', {
        method: 'POST',
        body: JSON.stringify({ items: state.items.map((c) => ({ id: c.id, title: c.title })) }),
      });
      updateItems(state.items.map((c) => ({ id: c.id, downloaded: !!flags[c.id] })));
    } catch { /* 下次加载列表时会刷新 */ }
  }

  const offJob = onJob((job, prev) => {
    if (prev && prev.running && !job.running) refreshDownloaded();
    state.jobStatus = jobStatusMap();
    // 只更新状态徽标，不重绘整个列表
    for (const id of state.visible) {
      const el = rowEl(id);
      if (el) el.querySelector('.badges').innerHTML = badgesHtml(state.byId.get(id));
    }
    updateFooter();
  });

  /* ---------- 对外接口 ---------- */

  function selectedItems() {
    return state.items.filter((c) => state.selected.has(c.id));
  }

  function setItems(items) {
    state.items = items;
    state.byId = new Map(items.map((c) => [c.id, c]));
    state.selected = new Set();
    state.cursor = -1;
    state.anchorId = null;
    state.loaded = true;
    listEl.scrollTop = 0;
    applyFilter();
  }

  function updateItems(items) {
    for (const c of items) {
      const mine = state.byId.get(c.id);
      if (mine) Object.assign(mine, c);
    }
    applyFilter();
  }

  function clear(text) {
    state.items = [];
    state.byId = new Map();
    state.selected = new Set();
    state.visible = [];
    state.loaded = false;
    if (text) listEl.innerHTML = `<div class="cl-empty">${escapeHtml(text)}</div>`;
    updateFooter();
  }

  function destroy() {
    document.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('mouseup', onMouseUp);
    offJob();
  }

  renderList();
  return { setItems, updateItems, selectedItems, refreshDownloaded, clear, destroy };
}
