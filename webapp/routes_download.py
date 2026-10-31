"""下载任务：开始、查看进度、停止"""
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webapp.browser_worker import worker

router = APIRouter(prefix="/api/download")


class DownloadItem(BaseModel):
    id: int
    title: str = ""


class DownloadBody(BaseModel):
    items: List[DownloadItem]


@router.get("")
async def download_status() -> dict:
    return worker.download.snapshot()


@router.post("")
async def start_download(body: DownloadBody) -> dict:
    if worker.download.running:
        raise HTTPException(status_code=409, detail="已有下载任务在运行")
    # 去重并保持顺序
    seen = set()
    comics = []
    for item in body.items:
        if item.id not in seen:
            seen.add(item.id)
            comics.append({"id": item.id, "title": item.title})
    if not comics:
        raise HTTPException(status_code=400, detail="没有勾选任何漫画")
    worker.download.start(comics)
    return worker.download.snapshot()


@router.post("/stop")
async def stop_download() -> dict:
    worker.download.stop()
    return worker.download.snapshot()
