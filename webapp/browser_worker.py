"""
浏览器任务调度
下载和重新登录都要独占 .playwright_profile/，用同一把锁排队执行
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Iterator, List, Optional

import config
from batch_download import BatchDownloadError, download_comic_list, setup_logging
from comic_downloader import DownloadQuotaExceeded
from download_history import download_quota
from webapp import common

logger = logging.getLogger("webapp")

# 下载队列持久化文件（不提交）
QUEUE_FILE = os.path.join(common.BASE_DIR, "download_queue.json")


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


class DownloadQueue:
    """下载队列：随时可以追加；队列持久化到文件，服务重启后未完成的还在"""

    def __init__(self, browser_lock: asyncio.Lock, path: str = QUEUE_FILE) -> None:
        self._lock = browser_lock
        self._path = path
        self.items: List[dict] = []
        self.running = False
        self.stop_requested = False
        self.quota_blocked = False   # 站点提示额度用完而暂停
        self.message = ""
        self._task: Optional[asyncio.Task] = None
        self._logger: Optional[logging.Logger] = None
        self._load()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                items = json.load(f).get('items', [])
        except (json.JSONDecodeError, OSError, AttributeError):
            return
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), int):
                continue
            # 上次没下完的恢复成等待，需要手动点继续
            if item.get('status') == 'downloading':
                item['status'] = 'pending'
            self.items.append(item)
        if self.pending_count:
            self.message = f"上次还有 {self.pending_count} 部没下载，点「开始下载」继续"

    def _save(self) -> None:
        tmp_path = f"{self._path}.tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump({"items": self.items}, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except OSError as e:
            logger.warning(f"保存下载队列失败: {e}")

    # ---------- 查询 ----------

    def _find(self, comic_id: int) -> Optional[dict]:
        return next((item for item in self.items if item['id'] == comic_id), None)

    def _next_pending(self) -> Optional[dict]:
        return next((item for item in self.items if item['status'] == 'pending'), None)

    @property
    def pending_count(self) -> int:
        return sum(1 for item in self.items if item['status'] == 'pending')

    def snapshot(self) -> dict:
        counts: Dict[str, int] = {}
        for item in self.items:
            counts[item['status']] = counts.get(item['status'], 0) + 1
        return {
            "running": self.running,
            "stop_requested": self.stop_requested,
            "items": self.items,
            "counts": counts,
            "pending": self.pending_count,
            "message": self.message,
            "quota_blocked": self.quota_blocked,
            "quota": download_quota(),
        }

    # ---------- 操作 ----------

    def add(self, comics: List[dict]) -> int:
        """加入队列；已在等待/下载中的跳过，已结束的重新排到队尾"""
        added = 0
        for comic in comics:
            existing = self._find(comic['id'])
            if existing and existing['status'] in ('pending', 'downloading'):
                for key in ('title', 'source'):
                    if comic.get(key) and not existing.get(key):
                        existing[key] = comic[key]
                continue
            if existing:
                self.items.remove(existing)
            self.items.append({
                "id": comic['id'],
                "title": comic.get('title') or (existing or {}).get('title', ''),
                "source": comic.get('source') or (existing or {}).get('source', ''),
                "status": "pending",
                "added_at": _now(),
            })
            added += 1
        self._save()
        return added

    def start(self) -> None:
        if self.running or not self.pending_count:
            return
        if self._logger is None:
            self._logger, _log_file = setup_logging()
        self.running = True
        self.stop_requested = False
        self.quota_blocked = False
        self.message = "等待浏览器空闲（正在登录）..." if self._lock.locked() else self._downloading_message()
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self.running:
            self.stop_requested = True
            self.message = "当前这部下载完后暂停..."

    def retry(self, ids: Optional[List[int]] = None) -> int:
        """失败或取消的重新排队"""
        wanted = set(ids) if ids is not None else None
        count = 0
        for item in self.items:
            if item['status'] in ('failed', 'cancelled') and (wanted is None or item['id'] in wanted):
                item['status'] = 'pending'
                item.pop('finished_at', None)
                count += 1
        self._save()
        return count

    def remove(self, ids: List[int]) -> int:
        """移除指定漫画（正在下载的那部不能移除）"""
        wanted = set(ids)
        before = len(self.items)
        self.items = [i for i in self.items if i['id'] not in wanted or i['status'] == 'downloading']
        self._save()
        return before - len(self.items)

    def clear_finished(self) -> int:
        """清除已完成（成功和已存在）的记录"""
        before = len(self.items)
        self.items = [i for i in self.items if i['status'] not in ('done', 'skipped')]
        self._save()
        return before - len(self.items)

    # ---------- 执行 ----------

    @staticmethod
    def _downloading_message() -> str:
        return "正在下载，浏览器窗口如出现Cloudflare验证请手动完成"

    def _feed(self) -> Iterator[dict]:
        """边下载边从队列取下一部，下载中追加的也会被取到"""
        while not self.stop_requested:
            item = self._next_pending()
            if item is None:
                return
            item['status'] = 'downloading'
            self._save()
            yield {"id": item['id'], "title": item.get('title', '')}

    def _set_status(self, comic_id: int, status: str) -> None:
        item = self._find(comic_id)
        if item is None:
            return
        item['status'] = status
        if status in ('done', 'skipped', 'failed'):
            item['finished_at'] = _now()
        self._save()

    async def _run(self) -> None:
        error = ""
        try:
            while not self.stop_requested and self._next_pending():
                async with self._lock:
                    if self.stop_requested:
                        break
                    self.message = self._downloading_message()
                    await download_comic_list(
                        self._feed(),
                        self._logger,
                        on_status=self._set_status,
                        should_stop=lambda: self.stop_requested,
                        # 网页里是明确加入队列的，不按下载记录跳过
                        skip_downloaded=False,
                        has_more=lambda: self._next_pending() is not None,
                    )
        except DownloadQuotaExceeded as e:
            self.quota_blocked = True
            error = (f"站点提示下载额度已用完（{e}），队列已暂停，还有 {self.pending_count} 部等待。"
                     "额度恢复后点「开始下载」继续")
        except BatchDownloadError as e:
            error = f"下载失败：{e}"
        except Exception as e:
            logger.exception("download queue crashed")
            error = f"下载出错：{e}"
        finally:
            # 中途中断（浏览器被关闭等）的那部放回等待
            for item in self.items:
                if item['status'] == 'downloading':
                    item['status'] = 'pending'
            failed = sum(1 for i in self.items if i['status'] == 'failed')
            if error:
                self.message = error
            elif self.stop_requested and self.pending_count:
                self.message = f"已暂停，还有 {self.pending_count} 部等待下载"
            else:
                self.message = f"队列已完成{f'，失败 {failed} 部' if failed else ''}"
            self.running = False
            self.stop_requested = False
            self._save()


class LoginTask:
    """重新登录：打开浏览器登录并刷新 cookie.json"""

    def __init__(self, browser_lock: asyncio.Lock) -> None:
        self._lock = browser_lock
        self.state = "idle"   # idle / waiting / running / success / failed
        self.message = ""
        self.finished_at: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    @property
    def busy(self) -> bool:
        return self.state in ("waiting", "running")

    def snapshot(self) -> dict:
        return {"state": self.state, "message": self.message, "finished_at": self.finished_at}

    def start(self) -> None:
        self.state = "waiting" if self._lock.locked() else "running"
        self.message = "等待当前下载结束后登录..." if self.state == "waiting" else ""
        self.finished_at = None
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            async with self._lock:
                self.state = "running"
                self.message = "浏览器已打开，如出现Cloudflare验证请手动完成"
                # login_and_get_cookie 使用同步Playwright，不能在事件循环线程里运行
                await asyncio.to_thread(config.refresh_cookie)
            self.state = "success"
            self.message = "登录成功，cookie已更新"
        except Exception as e:
            logger.exception("login failed")
            self.state = "failed"
            self.message = f"登录失败：{e}"
        finally:
            self.finished_at = _now()


class BrowserWorker:
    def __init__(self, queue_path: str = QUEUE_FILE) -> None:
        self.lock = asyncio.Lock()
        self.download = DownloadQueue(self.lock, queue_path)
        self.login = LoginTask(self.lock)


worker = BrowserWorker()
