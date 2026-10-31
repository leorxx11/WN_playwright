"""下载队列：加入、开始/暂停、重试、移除，以及最近下载记录"""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from download_history import load_history
from webapp.browser_worker import worker

router = APIRouter(prefix="/api/download")


class DownloadItem(BaseModel):
    id: int
    title: str = ""


class DownloadBody(BaseModel):
    items: List[DownloadItem]


class IdsBody(BaseModel):
    ids: Optional[List[int]] = None


def _snapshot(**extra) -> dict:
    return {**worker.download.snapshot(), **extra}


@router.get("")
async def queue_status() -> dict:
    return worker.download.snapshot()


@router.post("")
async def add_to_queue(body: DownloadBody) -> dict:
    """加入队列并开始下载；下载进行中也可以继续追加"""
    added = worker.download.add([{"id": item.id, "title": item.title} for item in body.items])
    worker.download.start()
    return _snapshot(added=added)


@router.post("/start")
async def start_queue() -> dict:
    worker.download.start()
    return worker.download.snapshot()


@router.post("/stop")
async def stop_queue() -> dict:
    worker.download.stop()
    return worker.download.snapshot()


@router.post("/retry")
async def retry_failed(body: IdsBody) -> dict:
    retried = worker.download.retry(body.ids)
    worker.download.start()
    return _snapshot(retried=retried)


@router.post("/remove")
async def remove_items(body: IdsBody) -> dict:
    removed = worker.download.remove(body.ids or [])
    return _snapshot(removed=removed)


@router.post("/clear")
async def clear_finished() -> dict:
    cleared = worker.download.clear_finished()
    return _snapshot(cleared=cleared)


@router.get("/history")
def download_history(limit: int = 50) -> List[dict]:
    """最近下载成功的漫画，最新的在前"""
    records = [
        {"id": int(key), "title": value.get("title", ""), "downloaded_at": value.get("downloaded_at", "")}
        for key, value in load_history().items()
        if key.isdigit() and isinstance(value, dict)
    ]
    records.sort(key=lambda r: r["downloaded_at"], reverse=True)
    return records[:max(1, min(limit, 500))]
