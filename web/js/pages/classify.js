// 分类：预览 downloads 里的zip按作者归到 class/ 的哪个文件夹，可调整后执行

import { api, escapeHtml, toast } from '../util.js';
import { onJob } from '../status.js';

const OTHER = 'other';
const KIND = {
  known: { label: '已知作者', cls: 's-done' },
  new: { label: '新作者', cls: 's-downloading' },
  other: { label: 'other', cls: 's-pending' },
};

function formatSize(bytes) {
  return bytes >= 1 << 30 ? `${(bytes / (1 << 30)).toFixed(1)} GB` : `${(bytes / (1 << 20)).toFixed(1)} MB`;
}

export function mount(page) {
  page.innerHTML = `
    <div class="cards wide">
      <div class="card">
        <div class="card-head">
          <h2>整理 downloads</h2>
          <div class="actions">
            <button data-act="expand">全部展开</button>
            <button data-act="reload">刷新</button>
            <button data-act="run" class="primary" disabled>执行分类</button>
          </div>
        </div>
        <div class="q-summary"></div>
        <div class="c-groups q-list"></div>
      </div>
      <div class="card">
        <h2>class 目录</h2>
        <div class="c-folders"></div>
      </div>
    </div>`;

  const summaryEl = page.querySelector('.q-summary');
  const groupsEl = page.querySelector('.c-groups');
  const foldersEl = page.querySelector('.c-folders');
  const runBtn = page.querySelector('[data-act="run"]');
  const expandBtn = page.querySelector('[data-act="expand"]');

  let data = null;
  let groups = [];      // 预览分组 + 页面上的调整（include / folder / addCsv / open / 每个文件的 checked）
  let busy = false;

  const groupOf = (el) => groups.find((g) => g.key === el.closest('.cg').dataset.key);
  const folderOf = (g) => g.folder.trim();
  const csvVisible = (g) => g.kind !== 'known' && !!g.author && folderOf(g) !== OTHER && folderOf(g) !== '';

  function plan() {
    const moves = [];
    const addAuthors = [];
    for (const g of groups) {
      if (!g.include || !folderOf(g)) continue;
      const files = g.files.filter((f) => f.checked);
      files.forEach((f) => moves.push({ file: f.name, folder: folderOf(g) }));
      if (files.length && csvVisible(g) && g.addCsv) addAuthors.push(folderOf(g));
    }
    return { moves, addAuthors };
  }

  function renderSummary() {
    if (!data) return;
    const { moves, addAuthors } = plan();
    const folders = new Set(moves.map((m) => m.folder));
    const count = (kind) => groups.filter((g) => g.kind === kind).length;
    let text = data.total
      ? `downloads 里有 ${data.total} 个 zip：已知作者 ${count('known')} 组，新作者 ${count('new')} 组，`
        + `other ${groups.filter((g) => g.kind === OTHER).reduce((n, g) => n + g.files.length, 0)} 个。`
        + `name.csv 里有 ${data.authors_count} 个作者。`
      : 'downloads 里没有 zip 文件。';
    if (data.downloading) text += ' 正在下载，下载结束或暂停后才能分类。';
    summaryEl.textContent = text;
    runBtn.disabled = busy || data.downloading || !moves.length;
    runBtn.textContent = moves.length
      ? `执行分类（${moves.length} 个 → ${folders.size} 个文件夹${addAuthors.length ? `，新增 ${addAuthors.length} 个作者` : ''}）`
      : '执行分类';
  }

  function renderGroupHead(g) {
    const kind = KIND[g.kind];
    const checked = g.files.filter((f) => f.checked).length;
    const countText = checked === g.files.length ? `${g.files.length} 个` : `${checked}/${g.files.length} 个`;
    const label = g.label || '无法识别';
    const useBtn = g.label && folderOf(g) === OTHER
      ? `<button class="cg-use" title="改为 class/${escapeHtml(g.label)}/">用作文件夹</button>` : '';
    const csv = csvVisible(g)
      ? `<label class="cg-csv"><input type="checkbox" ${g.addCsv ? 'checked' : ''}> 加入 name.csv</label>` : '';
    return `
      <input type="checkbox" class="cg-include" ${g.include ? 'checked' : ''} title="是否移动这一组">
      <button class="cg-toggle" title="展开文件">${g.open ? '▾' : '▸'}</button>
      <span class="badge ${kind.cls}">${kind.label}</span>
      <span class="cg-label${g.label ? '' : ' unknown'}" title="${escapeHtml(label)}">${escapeHtml(label)}<span class="cg-count">${countText}</span></span>
      <span class="cg-target">→ class/<input type="text" class="cg-folder" value="${escapeHtml(g.folder)}" spellcheck="false"></span>
      <span class="cg-extra">${useBtn}${csv}</span>`;
  }

  function renderFiles(g) {
    return g.files.map((f, i) => `
      <label class="cg-file">
        <input type="checkbox" data-file="${i}" ${f.checked ? 'checked' : ''}>
        <span class="cg-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
        <span class="cg-size">${formatSize(f.size)}</span>
      </label>`).join('');
  }

  function renderGroups() {
    if (!groups.length) {
      groupsEl.innerHTML = '<div class="q-empty">没有需要整理的文件。</div>';
      return;
    }
    groupsEl.innerHTML = groups.map((g) => `
      <div class="cg${g.include ? '' : ' off'}" data-key="${escapeHtml(g.key)}">
        <div class="cg-head">${renderGroupHead(g)}</div>
        <div class="cg-files"${g.open ? '' : ' hidden'}>${g.open ? renderFiles(g) : ''}</div>
      </div>`).join('');
  }

  // 只刷新一组的头部（保留输入框以外的状态），避免重绘整个列表
  function refreshHead(g, keepFocus) {
    const el = groupsEl.querySelector(`.cg[data-key="${CSS.escape(g.key)}"]`);
    if (!el) return;
    el.classList.toggle('off', !g.include);
    if (keepFocus) {
      // 正在输入文件夹名：只更新输入框之外的部分
      const head = el.querySelector('.cg-head');
      const tmp = document.createElement('div');
      tmp.innerHTML = renderGroupHead(g);
      head.querySelector('.cg-extra').replaceWith(tmp.querySelector('.cg-extra'));
      head.querySelector('.cg-count').replaceWith(tmp.querySelector('.cg-count'));
    } else {
      el.querySelector('.cg-head').innerHTML = renderGroupHead(g);
    }
    renderSummary();
  }

  function renderFolders() {
    const folders = data ? data.class_folders : [];
    foldersEl.innerHTML = folders.length
      ? `<div class="c-folder-list">${folders.map((f) => `
          <span class="c-folder"><span>${escapeHtml(f.name)}</span><span class="cg-count">${f.count}</span></span>`).join('')}</div>`
      : '<div class="q-empty">class 目录还是空的。</div>';
  }

  async function load() {
    try {
      data = await api('/api/classify');
    } catch (err) {
      summaryEl.textContent = err.message;
      return;
    }
    groups = data.groups.map((g) => ({
      ...g,
      include: true,
      addCsv: g.kind === 'new',
      open: false,
      files: g.files.map((f) => ({ ...f, checked: true })),
    }));
    renderGroups();
    renderFolders();
    renderSummary();
  }

  async function run() {
    const { moves, addAuthors } = plan();
    if (!moves.length) return;
    const folders = new Set(moves.map((m) => m.folder));
    const lines = [`将把 ${moves.length} 个文件移动到 class/ 下的 ${folders.size} 个文件夹。`];
    if (addAuthors.length) lines.push(`name.csv 新增作者：${addAuthors.join('、')}`);
    if (!confirm(`${lines.join('\n')}\n\n继续？`)) return;

    busy = true;
    renderSummary();
    try {
      const res = await api('/api/classify/run', {
        method: 'POST',
        body: JSON.stringify({ moves, add_authors: addAuthors }),
      });
      const parts = [`已移动 ${res.moved} 个文件`];
      const exists = res.skipped.filter((s) => s.reason === 'exists').length;
      if (exists) parts.push(`${exists} 个目标已存在未移动`);
      if (res.skipped.length - exists) parts.push(`${res.skipped.length - exists} 个找不到`);
      if (res.added_authors.length) parts.push(`name.csv 新增 ${res.added_authors.length} 个作者`);
      toast(parts.join('，'));
    } catch (err) {
      toast(err.message);
    } finally {
      busy = false;
    }
    load();
  }

  groupsEl.addEventListener('click', (e) => {
    const toggle = e.target.closest('.cg-toggle');
    const use = e.target.closest('.cg-use');
    if (toggle) {
      const g = groupOf(toggle);
      g.open = !g.open;
      const files = toggle.closest('.cg').querySelector('.cg-files');
      files.hidden = !g.open;
      files.innerHTML = g.open ? renderFiles(g) : '';
      toggle.textContent = g.open ? '▾' : '▸';
    } else if (use) {
      const g = groupOf(use);
      g.folder = g.label;
      g.include = true;
      refreshHead(g);
    }
  });

  groupsEl.addEventListener('change', (e) => {
    const t = e.target;
    const g = groupOf(t);
    if (t.classList.contains('cg-include')) {
      g.include = t.checked;
      refreshHead(g);
    } else if (t.closest('.cg-csv')) {
      g.addCsv = t.checked;
      renderSummary();
    } else if (t.dataset.file !== undefined) {
      g.files[Number(t.dataset.file)].checked = t.checked;
      refreshHead(g);
    }
  });

  groupsEl.addEventListener('input', (e) => {
    if (!e.target.classList.contains('cg-folder')) return;
    const g = groupOf(e.target);
    g.folder = e.target.value;
    refreshHead(g, true);
  });

  expandBtn.addEventListener('click', () => {
    const open = !groups.every((g) => g.open);
    groups.forEach((g) => { g.open = open; });
    expandBtn.textContent = open ? '全部收起' : '全部展开';
    renderGroups();
  });
  page.querySelector('[data-act="reload"]').addEventListener('click', load);
  runBtn.addEventListener('click', run);

  // 下载开始/结束时刷新：新下完的zip出现在列表里，下载中禁止分类
  const offJob = onJob((job, prev) => {
    if (data && prev && prev.running !== job.running) load();
  });

  load();
  return offJob;
}
