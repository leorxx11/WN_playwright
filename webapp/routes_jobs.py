"""抓取任务：查看进度、取消、保存为JSON"""
import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from get_shelf_info import build_shelf_export, shelf_export_filename
from search_id import build_search_export, clean_filename
from webapp import common
from webapp.fetch_jobs import get_job
from webapp.routes_files import to_list_items

router = APIRouter(prefix="/api/jobs")


class SaveBody(BaseModel):
    ids: Optional[List[int]] = None   # 为空表示保存全部


@router.get("/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    # 结果只在完成后返回，进度轮询时不重复传输
    items = to_list_items(job.raw) if job.state in ("done", "cancelled") else None
    return job.snapshot(items)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = get_job(job_id)
    job.cancelled = True
    return job.snapshot()


@router.post("/{job_id}/save")
def save_job(job_id: str, body: SaveBody) -> dict:
    """把搜索结果或书架内容保存到 search_results/，格式与命令行版一致"""
    job = get_job(job_id)
    if job.state == "running":
        raise HTTPException(status_code=409, detail="还没读取完，请稍候")

    comics = job.raw
    if body.ids is not None:
        wanted = set(body.ids)
        comics = [c for c in job.raw if c.get('id') in wanted]
    if not comics:
        raise HTTPException(status_code=400, detail="没有可保存的漫画")

    if job.kind == "search":
        data = build_search_export(comics, job.meta['query'])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        name = f"search_{clean_filename(job.meta['query'])}_all_{timestamp}.json"
    else:
        data = build_shelf_export(comics, job.meta['shelf_id'])
        shelf_name = job.meta.get('name') or data['shelf_metadata']['shelf_name']
        data['shelf_metadata']['shelf_name'] = shelf_name
        name = shelf_export_filename(shelf_name)

    os.makedirs(common.SEARCH_DIR, exist_ok=True)
    with open(os.path.join(common.SEARCH_DIR, name), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"name": name, "count": len(comics)}
