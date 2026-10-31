"""搜索：后台翻页抓取，前端轮询 /api/jobs/{id}"""
import asyncio
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from search_id import search_by_keyword, search_by_tag
from webapp.fetch_jobs import FetchJob, current_cookie, start_job

router = APIRouter(prefix="/api/search")

PAGE_INTERVAL_SECONDS = 0.5   # 翻页间隔，避免请求过于频繁


class SearchBody(BaseModel):
    query: str
    type: Literal["keyword", "tag"] = "keyword"
    max_pages: int = Field(default=20, ge=1, le=100)


def run_search(job: FetchJob, query: str, search_type: str, max_pages: int, cookie: str) -> None:
    search_func = search_by_tag if search_type == "tag" else search_by_keyword
    page = 1
    while page <= max_pages and not job.cancelled:
        result = search_func(query, page, cookie=cookie)
        if not result['comics']:
            break
        job.add(result['comics'])
        job.progress(page, min(result['total_page'], max_pages))
        if page >= result['total_page']:
            break
        page += 1
        time.sleep(PAGE_INTERVAL_SECONDS)


@router.post("")
async def start_search(body: SearchBody) -> dict:
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入搜索内容")
    cookie = current_cookie()

    async def runner(job: FetchJob) -> None:
        await asyncio.to_thread(run_search, job, query, body.type, body.max_pages, cookie)

    job = start_job("search", {"query": query, "type": body.type}, runner)
    return job.snapshot()
