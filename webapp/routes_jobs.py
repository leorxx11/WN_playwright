"""抓取任务：查看进度、取消"""
from fastapi import APIRouter

from webapp.comic_items import to_list_items
from webapp.fetch_jobs import get_job

router = APIRouter(prefix="/api/jobs")


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

