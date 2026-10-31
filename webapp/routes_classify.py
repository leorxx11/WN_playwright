"""分类：预览 downloads 里的zip按作者归到哪里，确认后移动到 class/"""
import asyncio
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import classify_by_author as classifier
from download_history import title_key
from webapp import common, follows
from webapp.browser_worker import worker

router = APIRouter(prefix="/api/classify")


def _paths() -> tuple:
    base = Path(common.BASE_DIR)
    return base / "downloads", base / "class", base / "name.csv"


class Move(BaseModel):
    file: str
    folder: str


class RunRequest(BaseModel):
    moves: List[Move]
    add_authors: List[str] = []


def _preview() -> dict:
    url_dir, class_dir, csv_path = _paths()
    known_authors = classifier.load_known_authors(csv_path) if csv_path.exists() else []
    hints = follows.folder_hints()
    groups = classifier.plan_classification(
        url_dir, known_authors, lambda name: hints.get(title_key(Path(name).stem)),
    ) if url_dir.is_dir() else []
    return {
        "groups": groups,
        "total": sum(len(g["files"]) for g in groups),
        "authors_count": len(known_authors),
        "class_folders": classifier.list_class_folders(class_dir),
    }


def count_unsorted() -> int:
    url_dir = _paths()[0]
    return sum(1 for f in url_dir.iterdir() if f.suffix == '.zip') if url_dir.is_dir() else 0


@router.get("/count")
def unsorted_count() -> dict:
    """downloads 里待整理的zip数量，导航栏角标用"""
    return {"count": count_unsorted()}


@router.get("")
async def preview() -> dict:
    data = await asyncio.to_thread(_preview)
    return {**data, "downloading": worker.download.running}


def _run(body: RunRequest) -> dict:
    url_dir, class_dir, csv_path = _paths()
    moved, skipped = 0, []
    for move in body.moves:
        folder = classifier.safe_folder_name(move.folder)
        if os.path.basename(move.file) != move.file or not move.file.endswith('.zip') or not folder:
            skipped.append({"file": move.file, "reason": "invalid"})
            continue
        result = classifier.move_file(url_dir, class_dir, move.file, folder)
        if result == "moved":
            moved += 1
        else:
            skipped.append({"file": move.file, "reason": result})

    known = set(classifier.load_known_authors(csv_path)) if csv_path.exists() else set()
    new_authors = set()
    for name in body.add_authors:
        normalized = classifier.normalize_author_name(name)
        if normalized and normalized != classifier.OTHER_FOLDER and normalized not in known:
            new_authors.add(normalized)
    if new_authors and not classifier.update_name_csv(csv_path, new_authors):
        raise HTTPException(status_code=500, detail="更新 name.csv 失败")
    return {"moved": moved, "skipped": skipped, "added_authors": sorted(new_authors)}


@router.post("/run")
async def run(body: RunRequest) -> dict:
    # 下载中的zip可能还没写完，避免把它移走
    if worker.download.running:
        raise HTTPException(status_code=409, detail="正在下载，等下载结束或暂停后再分类")
    if not body.moves:
        raise HTTPException(status_code=400, detail="没有要移动的文件")
    return await asyncio.to_thread(_run, body)
