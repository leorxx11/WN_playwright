"""
后台抓取任务（搜索、读取书架）
翻页较多时耗时较长，后台执行并让前端轮询进度
"""
import asyncio
import logging
import uuid
from typing import Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException

import config

logger = logging.getLogger("webapp")

MAX_JOBS = 20
LOGIN_REQUIRED = "cookie 已过期或不存在，请到「账号」页重新登录"


class LoginRequired(Exception):
    """站点提示需要登录"""


def current_cookie() -> str:
    """读取有效cookie；网页里不自动登录（登录要走浏览器队列），过期时提示去账号页"""
    cookie = config.load_cookie_from_file()
    if not cookie:
        raise HTTPException(status_code=401, detail=LOGIN_REQUIRED)
    return cookie


class FetchJob:
    def __init__(self, kind: str, meta: dict) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind          # search / shelf
        self.meta = meta          # 搜索词、书架ID等，保存JSON时使用
        self.state = "running"    # running / done / failed / cancelled
        self.done_pages = 0
        self.total_pages = 0
        self.raw: List[dict] = []
        self.message = ""
        self.cancelled = False
        self.task: Optional[asyncio.Task] = None
        self._seen_ids = set()

    def add(self, comics: List[dict]) -> None:
        """追加结果并按ID去重（翻页时站点可能返回重复项）"""
        for comic in comics:
            if comic.get('id') not in self._seen_ids:
                self._seen_ids.add(comic.get('id'))
                self.raw.append(comic)

    def progress(self, done_pages: int, total_pages: int) -> None:
        self.done_pages = done_pages
        self.total_pages = total_pages

    def snapshot(self, items: Optional[List[dict]] = None) -> dict:
        data = {
            "id": self.id,
            "kind": self.kind,
            "meta": self.meta,
            "state": self.state,
            "done_pages": self.done_pages,
            "total_pages": self.total_pages,
            "count": len(self.raw),
            "message": self.message,
        }
        if items is not None:
            data["items"] = items
        return data


_jobs: Dict[str, FetchJob] = {}


def start_job(kind: str, meta: dict, runner: Callable[[FetchJob], Awaitable[None]]) -> FetchJob:
    """启动任务；同类的旧任务会被取消"""
    for old in _jobs.values():
        if old.kind == kind and old.state == "running":
            old.cancelled = True

    job = FetchJob(kind, meta)
    _jobs[job.id] = job
    while len(_jobs) > MAX_JOBS:
        _jobs.pop(next(iter(_jobs)))

    async def run() -> None:
        try:
            await runner(job)
            if job.cancelled:
                job.state = "cancelled"
                job.message = "已取消"
            else:
                job.state = "done"
        except LoginRequired:
            job.state = "failed"
            job.message = LOGIN_REQUIRED
        except Exception as e:
            logger.exception("fetch job failed")
            job.state = "failed"
            job.message = str(e)

    job.task = asyncio.create_task(run())
    return job


def get_job(job_id: str) -> FetchJob:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期，请重新搜索")
    return job
