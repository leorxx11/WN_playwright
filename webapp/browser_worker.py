"""
浏览器任务调度
下载和重新登录都要独占 .playwright_profile/，用同一把锁排队执行
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import config
from batch_download import BatchDownloadError, download_comic_list, setup_logging

logger = logging.getLogger("webapp")


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


class DownloadJob:
    """批量下载任务；同一时间只运行一批"""

    def __init__(self, browser_lock: asyncio.Lock) -> None:
        self._lock = browser_lock
        self.running = False
        self.stop_requested = False
        self.items: List[dict] = []
        self.message = ""
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._logger: Optional[logging.Logger] = None

    def snapshot(self) -> dict:
        counts: Dict[str, int] = {}
        for item in self.items:
            counts[item['status']] = counts.get(item['status'], 0) + 1
        return {
            "running": self.running,
            "stop_requested": self.stop_requested,
            "items": self.items,
            "counts": counts,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def start(self, comics: List[dict]) -> None:
        if self._logger is None:
            self._logger, _log_file = setup_logging()
        self.running = True
        self.stop_requested = False
        self.items = [{"id": c['id'], "title": c.get('title', ''), "status": "pending"} for c in comics]
        self.message = "等待浏览器空闲..." if self._lock.locked() else self._started_message(len(comics))
        self.started_at = _now()
        self.finished_at = None
        self._task = asyncio.create_task(self._run(comics))

    def stop(self) -> None:
        if self.running:
            self.stop_requested = True
            self.message = "当前这部下载完后停止..."

    @staticmethod
    def _started_message(count: int) -> str:
        return f"开始下载 {count} 部，浏览器窗口如出现Cloudflare验证请手动完成"

    def _set_status(self, comic_id: int, status: str) -> None:
        for item in self.items:
            if item['id'] == comic_id:
                item['status'] = status
                break

    async def _run(self, comics: List[dict]) -> None:
        try:
            async with self._lock:
                if self.stop_requested:
                    self.message = "已停止"
                    return
                self.message = self._started_message(len(comics))
                await download_comic_list(
                    comics,
                    self._logger,
                    on_status=self._set_status,
                    should_stop=lambda: self.stop_requested,
                    # 网页里是明确勾选的，不按下载记录跳过
                    skip_downloaded=False,
                )
            done = sum(1 for i in self.items if i['status'] in ('done', 'skipped'))
            failed = sum(1 for i in self.items if i['status'] == 'failed')
            self.message = f"{'已停止' if self.stop_requested else '下载完成'}：成功 {done}，失败 {failed}"
        except BatchDownloadError as e:
            self.message = f"下载失败：{e}"
        except Exception as e:
            logger.exception("download job crashed")
            self.message = f"下载出错：{e}"
        finally:
            for item in self.items:
                if item['status'] in ('pending', 'downloading'):
                    item['status'] = 'cancelled'
            self.running = False
            self.finished_at = _now()


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
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.download = DownloadJob(self.lock)
        self.login = LoginTask(self.lock)


worker = BrowserWorker()
