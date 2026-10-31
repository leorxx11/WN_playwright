// 全局状态：下载任务和账号，顶栏和各页面共用

import { api, toast } from './util.js';

const jobListeners = new Set();
const accountListeners = new Set();
const unsortedListeners = new Set();

export const status = {
  job: null,
  account: null,
  verified: null,   // { logged_in, message } 最近一次验证结果
  unsorted: null,   // downloads 里待整理的 zip 数量
};

/* ---------- 下载任务 ---------- */

export function onJob(fn) {
  jobListeners.add(fn);
  if (status.job) fn(status.job, null);
  return () => jobListeners.delete(fn);
}

function setJob(job) {
  const prev = status.job;
  status.job = job;
  jobListeners.forEach((fn) => fn(job, prev));
  if (prev && prev.running && !job.running) {
    toast(job.message || '下载结束');
    refreshUnsorted();
  }
}

let jobTimer = null;
export async function pollJob() {
  clearTimeout(jobTimer);
  try {
    setJob(await api('/api/download'));
  } catch { /* 服务暂时不可用时继续轮询 */ }
  if (status.job && status.job.running) jobTimer = setTimeout(pollJob, 1500);
}

// 加入下载队列前的额度提醒：返回提示文字，额度够用时返回空字符串
// （额度按本机下载记录估算；站点真的拒绝时队列会自动暂停）
export function quotaWarning(count) {
  const job = status.job;
  if (!job || !job.quota) return '';
  const { remaining, limit } = job.quota;
  const queued = job.pending || 0;
  if (queued + count <= remaining) return '';
  return `站点限制每个 IP 24 小时内只能下载 ${limit} 个文件，按下载记录估算还剩 ${remaining} 个`
    + `${queued ? `，队列里已有 ${queued} 部在等` : ''}。超出的部分会在站点提示额度用完时自动暂停，等额度恢复后再继续。`;
}

// 加入下载队列（下载进行中也可以追加），返回新加入的数量
export async function startDownload(items) {
  const job = await api('/api/download', { method: 'POST', body: JSON.stringify({ items }) });
  setJob(job);
  pollJob();
  return job.added;
}

export async function stopDownload() {
  setJob(await api('/api/download/stop', { method: 'POST' }));
}

// 队列操作：start / retry / remove / clear，返回接口结果
export async function queueAction(action, body = {}) {
  const job = await api(`/api/download/${action}`, { method: 'POST', body: JSON.stringify(body) });
  setJob(job);
  if (job.running) pollJob();
  return job;
}

export function jobStatusMap() {
  return new Map((status.job ? status.job.items : []).map((i) => [i.id, i.status]));
}

/* ---------- 待整理数量 ---------- */

export function onUnsorted(fn) {
  unsortedListeners.add(fn);
  if (status.unsorted != null) fn(status.unsorted);
  return () => unsortedListeners.delete(fn);
}

export async function refreshUnsorted() {
  try {
    status.unsorted = (await api('/api/classify/count')).count;
  } catch {
    return;
  }
  unsortedListeners.forEach((fn) => fn(status.unsorted));
}

/* ---------- 账号 ---------- */

export function onAccount(fn) {
  accountListeners.add(fn);
  if (status.account) fn(status);
  return () => accountListeners.delete(fn);
}

function emitAccount() {
  accountListeners.forEach((fn) => fn(status));
}

let accountTimer = null;
export async function refreshAccount() {
  clearTimeout(accountTimer);
  const prevLogin = status.account && status.account.login;
  try {
    status.account = await api('/api/account');
  } catch {
    return;
  }
  const login = status.account.login;
  const wasBusy = prevLogin && ['waiting', 'running'].includes(prevLogin.state);
  const busy = ['waiting', 'running'].includes(login.state);
  if (wasBusy && !busy) {
    toast(login.message);
    status.verified = login.state === 'success' ? { logged_in: true, message: '登录有效' } : status.verified;
  }
  emitAccount();
  if (busy) accountTimer = setTimeout(refreshAccount, 1500);
}

export async function verifyAccount() {
  status.verified = await api('/api/account/verify', { method: 'POST' });
  emitAccount();
  return status.verified;
}

export async function startLogin() {
  await api('/api/account/login', { method: 'POST' });
  await refreshAccount();
}

// 顶栏和账号页共用的登录状态描述
export function accountSummary(s) {
  const a = s.account;
  if (!a) return { level: '', text: '读取登录状态...' };
  if (['waiting', 'running'].includes(a.login.state)) return { level: 'warn', text: '登录中...' };
  if (!a.cookie) return { level: 'bad', text: '未登录' };
  if (a.cookie.expired) return { level: 'warn', text: 'cookie 已过期' };
  if (s.verified && !s.verified.logged_in) return { level: 'bad', text: s.verified.message };
  if (s.verified && s.verified.logged_in) return { level: 'ok', text: '已登录' };
  return { level: 'ok', text: 'cookie 有效' };
}
