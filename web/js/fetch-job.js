// 轮询后台抓取任务（搜索、读取书架）直到结束

import { api } from './util.js';

const POLL_MS = 600;

// 返回 { promise, cancel }；promise 结束时得到带 items 的任务快照
export function followJob(jobId, onProgress) {
  let stopped = false;
  let timer = null;

  const promise = new Promise((resolve, reject) => {
    async function tick() {
      if (stopped) return;
      let job;
      try {
        job = await api(`/api/jobs/${jobId}`);
      } catch (err) {
        reject(err);
        return;
      }
      if (stopped) return;
      onProgress(job);
      if (job.state === 'running') {
        timer = setTimeout(tick, POLL_MS);
      } else if (job.state === 'failed') {
        reject(Object.assign(new Error(job.message || '读取失败'), { status: job.message.includes('账号') ? 401 : 0 }));
      } else {
        resolve(job);
      }
    }
    tick();
  });

  return {
    promise,
    // 只停止本页轮询，不取消后台任务（切换页面后回来可以继续看结果）
    detach() {
      stopped = true;
      clearTimeout(timer);
    },
    async cancel() {
      await api(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
    },
  };
}

export function progressText(job, noun) {
  if (job.state !== 'running') return '';
  const pages = job.total_pages ? `第 ${job.done_pages}/${job.total_pages} 页` : '正在读取第一页';
  return `${noun}中… ${pages} · 已找到 ${job.count} 部`;
}
