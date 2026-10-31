// 全局状态：下载任务和账号，顶栏和各页面共用

import { api, toast } from './util.js';

const jobListeners = new Set();
const accountListeners = new Set();

export const status = {
  job: null,
  account: null,
  verified: null,   // { logged_in, message } 最近一次验证结果
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
  if (prev && prev.running && !job.running) toast(job.message || '下载结束');
}

let jobTimer = null;
export async function pollJob() {
  clearTimeout(jobTimer);
  try {
    setJob(await api('/api/download'));
  } catch { /* 服务暂时不可用时继续轮询 */ }
  if (status.job && status.job.running) jobTimer = setTimeout(pollJob, 1500);
}

export async function startDownload(items) {
  setJob(await api('/api/download', { method: 'POST', body: JSON.stringify({ items }) }));
  pollJob();
}

export async function stopDownload() {
  setJob(await api('/api/download/stop', { method: 'POST' }));
}

export function jobStatusMap() {
  return new Map((status.job ? status.job.items : []).map((i) => [i.id, i.status]));
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
