"""追更：保存的搜索，刷新后看有哪些还没下载"""
import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from webapp import follows
from webapp.comic_items import downloaded_checker, to_list_items
from webapp.fetch_jobs import FetchJob, current_cookie, get_job, start_job
from webapp.routes_search import run_search

router = APIRouter(prefix="/api/follows")


class FollowBody(BaseModel):
    type: Literal["keyword", "tag"] = "keyword"
    query: str
    max_pages: int = Field(default=20, ge=1, le=100)
    folder: str = ""
    job_id: Optional[str] = None   # 从刚完成的搜索创建时带上，直接用它的结果


class FollowPatch(BaseModel):
    type: Optional[Literal["keyword", "tag"]] = None
    max_pages: Optional[int] = Field(default=None, ge=1, le=100)
    folder: Optional[str] = None


def _summary(follow: dict, is_downloaded=None) -> dict:
    is_downloaded = is_downloaded or downloaded_checker()
    raw = follow.get('items', [])
    undownloaded = sum(
        1 for c in raw
        if isinstance(c.get('id'), int) and not is_downloaded(c['id'], c.get('title') or '')
    )
    return {
        "id": follow['id'],
        "type": follow['type'],
        "query": follow['query'],
        "max_pages": follow.get('max_pages', 20),
        "folder": follow.get('folder', ''),
        "checked_at": follow.get('checked_at'),
        "total": len(raw),
        "undownloaded": undownloaded,
    }


def _get_or_404(follow_id: str) -> dict:
    follow = follows.get_follow(follow_id)
    if follow is None:
        raise HTTPException(status_code=404, detail="追更不存在")
    return follow


@router.get("")
def list_follows() -> list:
    is_downloaded = downloaded_checker()
    return [_summary(f, is_downloaded) for f in follows.load_follows()]


@router.post("")
def create_follow(body: FollowBody) -> dict:
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入搜索内容")
    items = None
    if body.job_id:
        job = get_job(body.job_id)
        if job.state == "running":
            raise HTTPException(status_code=409, detail="还没搜索完，请稍候")
        items = job.raw
    follow = follows.add_follow(body.type, query, body.max_pages, body.folder.strip(), items)
    return _summary(follow)


@router.get("/{follow_id}")
def follow_detail(follow_id: str) -> dict:
    follow = _get_or_404(follow_id)
    return {**_summary(follow), "items": to_list_items(follow.get('items', []))}


@router.patch("/{follow_id}")
def patch_follow(follow_id: str, body: FollowPatch) -> dict:
    folder = body.folder.strip() if body.folder is not None else None
    follow = follows.update_follow(follow_id, type=body.type, max_pages=body.max_pages, folder=folder)
    if follow is None:
        raise HTTPException(status_code=404, detail="追更不存在")
    return _summary(follow)


@router.delete("/{follow_id}")
def remove_follow(follow_id: str) -> dict:
    if not follows.delete_follow(follow_id):
        raise HTTPException(status_code=404, detail="追更不存在")
    return {"deleted": follow_id}


@router.post("/{follow_id}/refresh")
async def refresh_follow(follow_id: str) -> dict:
    """重新搜索；搜索完整结束才覆盖保存的结果，中途取消不保存"""
    follow = _get_or_404(follow_id)
    cookie = current_cookie()

    async def runner(job: FetchJob) -> None:
        await asyncio.to_thread(run_search, job, follow['query'], follow['type'], follow.get('max_pages', 20), cookie)
        if not job.cancelled:
            follows.set_follow_items(follow_id, job.raw)

    job = start_job(f"follow:{follow_id}", {"query": follow['query'], "type": follow['type'], "follow_id": follow_id}, runner)
    return job.snapshot()
