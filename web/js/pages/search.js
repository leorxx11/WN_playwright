// 搜索：关键词/标签搜索，结果直接勾选下载或保存为JSON

import { api, escapeHtml, toast } from '../util.js';
import { createComicList } from '../comic-list.js';
import { followJob, progressText } from '../fetch-job.js';

// 切换页面后回来保留上次的搜索
const cache = {
  type: 'keyword',
  query: '',
  maxPages: 20,
  jobId: null,
  items: null,
};

export function mount(page) {
  page.innerHTML = `
    <div class="pagebar">
      <div class="seg" role="group" aria-label="搜索类型">
        <button data-type="keyword">关键词</button><button data-type="tag">标签</button>
      </div>
      <input class="q" type="text" autocomplete="off">
      <label>最多 <input class="pages" type="number" min="1" max="100"> 页</label>
      <button class="go primary">搜索</button>
      <button class="cancel" hidden>取消</button>
      <div class="pb-status"></div>
    </div>
    <section class="list-host"></section>`;

  const $ = (sel) => page.querySelector(sel);
  const queryEl = $('.q');
  const pagesEl = $('.pages');
  const goBtn = $('.go');
  const cancelBtn = $('.cancel');
  const statusEl = $('.pb-status');

  let follower = null;

  const list = createComicList($('.list-host'), {
    emptyText: '输入关键词或标签开始搜索',
    noItemsText: '没有搜到结果',
    actions: [
      { label: () => '保存全部为 JSON', whole: true, onClick: () => save(null) },
      { label: () => '保存选中为 JSON', onClick: (items) => save(items.map((c) => c.id)) },
    ],
  });

  function setType(type) {
    cache.type = type;
    page.querySelectorAll('[data-type]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.type === type)));
    queryEl.placeholder = type === 'tag' ? '输入标签（需与站点标签完全一致），回车搜索' : '输入关键词，回车搜索';
  }

  function setStatus(text, { bad = false, html = false } = {}) {
    statusEl.className = `pb-status${bad ? ' bad' : ''}`;
    if (html) statusEl.innerHTML = text; else statusEl.textContent = text;
  }

  function showError(err) {
    if (err.status === 401) {
      setStatus(`${escapeHtml(err.message)} <a href="#/account">去账号页</a>`, { bad: true, html: true });
    } else {
      setStatus(err.message, { bad: true });
    }
  }

  function setRunning(running) {
    goBtn.disabled = running;
    cancelBtn.hidden = !running;
  }

  function follow(jobId) {
    follower?.detach();
    setRunning(true);
    follower = followJob(jobId, (job) => {
      if (job.state === 'running') setStatus(progressText(job, '搜索'));
    });
    follower.promise
      .then((job) => {
        cache.items = job.items;
        list.setItems(job.items);
        const note = job.state === 'cancelled' ? '（已取消，显示已读取的部分）' : '';
        setStatus(`「${cache.query}」共 ${job.items.length} 部${note}`);
      })
      .catch((err) => {
        cache.jobId = null;
        showError(err);
      })
      .finally(() => setRunning(false));
  }

  async function search() {
    const query = queryEl.value.trim();
    if (!query) {
      queryEl.focus();
      return;
    }
    cache.query = query;
    cache.maxPages = Math.min(100, Math.max(1, Number(pagesEl.value) || 20));
    pagesEl.value = cache.maxPages;
    cache.items = null;
    list.clear('搜索中…');
    setStatus('搜索中…');
    try {
      const job = await api('/api/search', {
        method: 'POST',
        body: JSON.stringify({ query, type: cache.type, max_pages: cache.maxPages }),
      });
      cache.jobId = job.id;
      follow(job.id);
    } catch (err) {
      list.clear('输入关键词或标签开始搜索');
      showError(err);
    }
  }

  async function save(ids) {
    try {
      const res = await api(`/api/jobs/${cache.jobId}/save`, { method: 'POST', body: JSON.stringify({ ids }) });
      toast(`已保存 ${res.count} 部到 ${res.name}，可在「已导出」里打开`);
    } catch (err) {
      toast(err.message);
    }
  }

  page.querySelectorAll('[data-type]').forEach((b) => b.addEventListener('click', () => setType(b.dataset.type)));
  goBtn.addEventListener('click', search);
  queryEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      search();
    }
  });
  cancelBtn.addEventListener('click', () => follower?.cancel().catch((err) => toast(err.message)));

  // 恢复上次的搜索
  setType(cache.type);
  queryEl.value = cache.query;
  pagesEl.value = cache.maxPages;
  if (cache.items) {
    list.setItems(cache.items);
    list.refreshDownloaded();
    setStatus(`「${cache.query}」共 ${cache.items.length} 部`);
  } else if (cache.jobId) {
    list.clear('搜索中…');
    follow(cache.jobId);
  } else {
    queryEl.focus();
  }

  return () => {
    follower?.detach();
    list.destroy();
  };
}
