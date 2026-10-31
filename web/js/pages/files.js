// 已导出：打开 search_results/ 里的 JSON，勾选后下载或导出

import { api, escapeHtml, storageGet, storageSet, toast } from '../util.js';
import { onJob } from '../status.js';
import { createComicList } from '../comic-list.js';

const KIND_NAME = { shelf: '书架', search: '搜索', selected: '勾选' };

export function mount(page) {
  page.innerHTML = `
    <div class="split">
      <aside class="subnav"><h2>导出的 JSON</h2><ul></ul></aside>
      <section></section>
    </div>`;
  const filesEl = page.querySelector('.subnav ul');

  let files = [];
  let current = null;

  const list = createComicList(page.querySelector('section'), {
    emptyText: '从左侧选择一个 JSON 文件',
    actions: [{ label: () => '导出选中为 JSON', onClick: exportSelected }],
  });

  async function loadFiles() {
    try {
      files = await api('/api/files');
    } catch (err) {
      toast(err.message);
      return;
    }
    renderFiles();
  }

  function renderFiles() {
    filesEl.innerHTML = files.map((f) => `
      <li data-name="${escapeHtml(f.name)}" class="${f.name === current ? 'active' : ''}" title="${escapeHtml(f.name)}">
        <div class="s-label"><span class="kind">${KIND_NAME[f.kind] || f.kind}</span>${escapeHtml(f.label.replace(/^.+?：/, '') || f.name)}</div>
        <div class="s-meta">${f.count} 部 · ${escapeHtml(f.name)}</div>
      </li>`).join('') || '<li class="s-meta">search_results/ 里没有 JSON 文件</li>';
  }

  async function openFile(name) {
    let data;
    try {
      data = await api(`/api/files/${encodeURIComponent(name)}`);
    } catch (err) {
      toast(err.message);
      return;
    }
    current = name;
    storageSet('wn.file', name);
    renderFiles();
    list.setItems(data.comics);
  }

  async function exportSelected(items) {
    try {
      const res = await api(`/api/files/${encodeURIComponent(current)}/export`, {
        method: 'POST', body: JSON.stringify({ ids: items.map((c) => c.id) }),
      });
      toast(`已导出 ${res.count} 部到 ${res.name}`);
      await loadFiles();
    } catch (err) {
      toast(err.message);
    }
  }

  filesEl.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-name]');
    if (li) openFile(li.dataset.name);
  });

  // 下载结束后刷新已下载标记
  const offJob = onJob((job, prev) => {
    if (current && prev && prev.running && !job.running) {
      api(`/api/files/${encodeURIComponent(current)}`)
        .then((data) => list.updateItems(data.comics))
        .catch(() => { /* 下次打开文件时会刷新 */ });
    }
  });

  (async () => {
    await loadFiles();
    const last = storageGet('wn.file');
    const initial = files.find((f) => f.name === last) || files[0];
    if (initial) await openFile(initial.name);
  })();

  return () => {
    offJob();
    list.destroy();
  };
}
