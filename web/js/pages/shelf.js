// 书架：选择书架，读取全部漫画后直接勾选下载或导出为JSON

import { api, escapeHtml, toast } from '../util.js';
import { createComicList } from '../comic-list.js';
import { followJob, progressText } from '../fetch-job.js';

// 切换页面后回来保留书架列表和上次打开的书架
const cache = {
  shelves: null,
  current: null,   // { id, name }
  jobId: null,
  items: null,
};

export function mount(page) {
  page.innerHTML = `
    <div class="split">
      <aside class="subnav">
        <div class="subnav-head"><h2>书架</h2><button class="refresh" title="重新读取书架列表">刷新</button></div>
        <ul></ul>
      </aside>
      <section>
        <div class="pagebar"><div class="pb-status"></div><button class="cancel" hidden>取消</button></div>
        <div class="list-host"></div>
      </section>
    </div>`;

  const $ = (sel) => page.querySelector(sel);
  const shelvesEl = $('.subnav ul');
  const statusEl = $('.pb-status');
  const cancelBtn = $('.cancel');

  let follower = null;

  const list = createComicList($('.list-host'), {
    emptyText: '从左侧选择一个书架',
    noItemsText: '这个书架是空的',
    actions: [
      { label: () => '导出全部为 JSON', whole: true, onClick: () => save(null) },
      { label: () => '导出选中为 JSON', onClick: (items) => save(items.map((c) => c.id)) },
    ],
  });

  function setStatus(text, { bad = false, html = false } = {}) {
    statusEl.className = `pb-status${bad ? ' bad' : ''}`;
    if (html) statusEl.innerHTML = text; else statusEl.textContent = text;
  }

  function errorHtml(err) {
    const link = err.status === 401 ? ' <a href="#/account">去账号页</a>' : '';
    return `${escapeHtml(err.message)}${link}`;
  }

  function renderShelves() {
    if (!cache.shelves) {
      shelvesEl.innerHTML = '<li class="s-empty">读取中…</li>';
      return;
    }
    shelvesEl.innerHTML = cache.shelves.map((s) => `
      <li data-id="${s.id}" class="${cache.current && cache.current.id === s.id ? 'active' : ''}">
        <div class="s-label">${escapeHtml(s.name || `书架 ${s.id}`)}</div>
        <div class="s-meta">${s.id === 0 ? '所有收藏' : `ID ${s.id}`}</div>
      </li>`).join('') || '<li class="s-empty">没有书架</li>';
  }

  async function loadShelves() {
    cache.shelves = null;
    renderShelves();
    try {
      cache.shelves = await api('/api/shelves');
      renderShelves();
    } catch (err) {
      shelvesEl.innerHTML = `<li class="s-empty">${errorHtml(err)}</li>`;
    }
  }

  function follow(jobId) {
    follower?.detach();
    cancelBtn.hidden = false;
    follower = followJob(jobId, (job) => {
      if (job.state === 'running') setStatus(progressText(job, '读取'));
    });
    follower.promise
      .then((job) => {
        cache.items = job.items;
        list.setItems(job.items);
        const note = job.state === 'cancelled' ? '（已取消，显示已读取的部分）' : '';
        setStatus(`「${cache.current.name}」共 ${job.items.length} 部${note}`);
      })
      .catch((err) => {
        cache.jobId = null;
        list.clear('读取失败');
        setStatus(errorHtml(err), { bad: true, html: true });
      })
      .finally(() => { cancelBtn.hidden = true; });
  }

  async function openShelf(id) {
    const shelf = cache.shelves.find((s) => s.id === id);
    cache.current = { id, name: shelf ? shelf.name : `书架 ${id}` };
    cache.items = null;
    renderShelves();
    list.clear('读取中…');
    setStatus('读取中…');
    try {
      const job = await api(`/api/shelves/${id}/fetch?name=${encodeURIComponent(cache.current.name)}`, { method: 'POST' });
      cache.jobId = job.id;
      follow(job.id);
    } catch (err) {
      list.clear('读取失败');
      setStatus(errorHtml(err), { bad: true, html: true });
    }
  }

  async function save(ids) {
    try {
      const res = await api(`/api/jobs/${cache.jobId}/save`, { method: 'POST', body: JSON.stringify({ ids }) });
      toast(`已导出 ${res.count} 部到 ${res.name}，可在「已导出」里打开`);
    } catch (err) {
      toast(err.message);
    }
  }

  shelvesEl.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-id]');
    if (li) openShelf(Number(li.dataset.id));
  });
  $('.refresh').addEventListener('click', loadShelves);
  cancelBtn.addEventListener('click', () => follower?.cancel().catch((err) => toast(err.message)));

  // 恢复上次打开的书架
  if (cache.shelves) renderShelves(); else loadShelves();
  if (cache.items) {
    list.setItems(cache.items);
    list.refreshDownloaded();
    setStatus(`「${cache.current.name}」共 ${cache.items.length} 部`);
  } else if (cache.jobId) {
    list.clear('读取中…');
    follow(cache.jobId);
  }

  return () => {
    follower?.detach();
    list.destroy();
  };
}
