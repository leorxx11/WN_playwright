"""书架：列出书架、后台读取书架内全部漫画"""
from dataclasses import asdict
from typing import List

import aiohttp
from aiohttp import ClientTimeout, TCPConnector
from fastapi import APIRouter, HTTPException

from get_shelf_info import get_all_comics_from_shelf, get_shelves
from webapp.fetch_jobs import LOGIN_REQUIRED, FetchJob, LoginRequired, current_cookie, start_job

router = APIRouter(prefix="/api/shelves")


def _session() -> aiohttp.ClientSession:
    # 与 get_shelf_info.py 命令行版保持一致：限制并发、使用系统代理
    return aiohttp.ClientSession(
        timeout=ClientTimeout(total=30, connect=10, sock_read=10),
        connector=TCPConnector(limit=10, ttl_dns_cache=300, ssl=False),
        trust_env=True,
    )


@router.get("")
async def list_shelves() -> List[dict]:
    cookie = current_cookie()
    try:
        async with _session() as session:
            shelves = await get_shelves(session, cookie)
    except ValueError:
        raise HTTPException(status_code=401, detail=LOGIN_REQUIRED)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return [asdict(shelf) for shelf in shelves]


@router.post("/{shelf_id}/fetch")
async def fetch_shelf(shelf_id: int, name: str = "") -> dict:
    cookie = current_cookie()

    async def runner(job: FetchJob) -> None:
        async with _session() as session:
            comics = await get_all_comics_from_shelf(session, cookie, shelf_id, on_progress=job.progress)
        if not comics and job.total_pages <= 1:
            # 空书架和登录失效都会返回0本，未登录时收藏页没有书架导航
            async with _session() as session:
                try:
                    await get_shelves(session, cookie)
                except ValueError:
                    raise LoginRequired()
        job.add([asdict(comic) for comic in comics])

    job = start_job("shelf", {"shelf_id": shelf_id, "name": name}, runner)
    return job.snapshot()
