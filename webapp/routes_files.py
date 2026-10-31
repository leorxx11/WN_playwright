"""已导出JSON：列出、读取、导出选中"""
import json
import os
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from download_history import downloaded_ids, scan_local_zip_keys, title_key
from search_id import extract_chapter_info
from webapp import common

router = APIRouter(prefix="/api/files")

# 只允许 search_results 下这几类导出文件，避免路径穿越
JSON_NAME_RE = re.compile(r'^(shelf|search|selected)_[^/\\]+\.json$')


class IdsBody(BaseModel):
    ids: List[int]


def _json_path(name: str) -> str:
    """校验文件名并返回search_results下的绝对路径"""
    if not JSON_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="不支持的文件名")
    path = os.path.join(common.SEARCH_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return path


def _load_json(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get('comics'), list):
        raise HTTPException(status_code=422, detail="JSON格式不正确：缺少comics列表")
    return data


def _file_label(data: dict) -> str:
    """书架名或搜索词，用于页面显示"""
    if data.get('shelf_metadata'):
        return f"书架：{data['shelf_metadata'].get('shelf_name', '')}"
    if data.get('selection_metadata'):
        return f"勾选：{data['selection_metadata'].get('source_label', '')}"
    if data.get('search_metadata'):
        return f"搜索：{data['search_metadata'].get('search_query', '')}"
    return ""


def _comic_info(comic: dict) -> str:
    """附加信息：搜索结果的图片数/创建时间，或书架的收藏时间"""
    search_info = comic.get('search_info') or {}
    info = search_info.get('additional_info') or comic.get('additional_info') or ''
    if not info and comic.get('favorite_time'):
        info = f"收藏于 {comic['favorite_time']}"
    return re.sub(r'\s+', ' ', info).strip()


def _chapter_range(title: str) -> tuple[Optional[int], Optional[int]]:
    """从标题解析话数范围，如 '127-128話' -> (127, 128)"""
    chapter = extract_chapter_info(title)
    if not chapter:
        return None, None
    parts = [int(p) for p in chapter.split('-')]
    return parts[0], parts[-1]


def to_list_items(raw_comics: List[dict]) -> List[dict]:
    """把漫画数据转成前端列表需要的格式，附带已下载标记（搜索、书架页也会用）"""
    history = downloaded_ids()
    local_keys = scan_local_zip_keys()

    items = []
    for comic in raw_comics:
        comic_id = comic.get('id')
        if not isinstance(comic_id, int):
            continue
        title = comic.get('title') or f"Comic_{comic_id}"
        chapter_start, chapter_end = _chapter_range(title)
        items.append({
            "id": comic_id,
            "title": title,
            "cover": comic.get('cover') or '',
            "info": _comic_info(comic),
            "chapter_start": chapter_start,
            "chapter_end": chapter_end,
            "downloaded": comic_id in history or title_key(title) in local_keys,
        })
    return items


@router.get("")
def list_files() -> List[dict]:
    """列出可勾选的JSON文件，最新的在前"""
    if not os.path.isdir(common.SEARCH_DIR):
        return []

    files = []
    for name in os.listdir(common.SEARCH_DIR):
        if not JSON_NAME_RE.match(name):
            continue
        path = os.path.join(common.SEARCH_DIR, name)
        try:
            data = _load_json(path)
        except (HTTPException, json.JSONDecodeError, OSError):
            continue
        files.append({
            "name": name,
            "kind": name.split('_', 1)[0],
            "label": _file_label(data),
            "count": len(data['comics']),
            "mtime": os.path.getmtime(path),
        })

    files.sort(key=lambda f: f['mtime'], reverse=True)
    return files


@router.get("/{name}")
def get_file(name: str) -> dict:
    data = _load_json(_json_path(name))
    return {"name": name, "label": _file_label(data), "comics": to_list_items(data['comics'])}


@router.post("/{name}/export")
def export_selection(name: str, body: IdsBody) -> dict:
    """把勾选的漫画导出为新的 selected_*.json，可用于 batch_download.py"""
    data = _load_json(_json_path(name))
    wanted = set(body.ids)
    comics = [c for c in data['comics'] if c.get('id') in wanted]
    if not comics:
        raise HTTPException(status_code=400, detail="没有勾选任何漫画")

    stem = re.sub(r'^(shelf|search|selected)_', '', name[:-5])
    stem = re.sub(r'_\d{8}_\d{6}$', '', stem)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_name = f"selected_{stem}_{timestamp}.json"

    exported = {key: value for key, value in data.items() if key != 'comics'}
    exported.update({
        "comics": comics,
        "total_comics": len(comics),
        "selection_metadata": {
            "source_file": name,
            "source_label": _file_label(data),
            "export_time": datetime.now().isoformat(),
        },
    })
    with open(os.path.join(common.SEARCH_DIR, out_name), 'w', encoding='utf-8') as f:
        json.dump(exported, f, ensure_ascii=False, indent=2)
    return {"name": out_name, "count": len(comics)}
