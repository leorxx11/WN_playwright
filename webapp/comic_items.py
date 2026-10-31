"""漫画列表数据：转成前端列表格式、标记已下载"""
import re
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from download_history import downloaded_ids, scan_local_zip_keys, title_key
from search_id import extract_chapter_info

router = APIRouter(prefix="/api/downloaded")


class FlagItem(BaseModel):
    id: int
    title: str = ""


class FlagsBody(BaseModel):
    items: List[FlagItem]


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


def downloaded_checker():
    """返回判断是否已下载的函数：下载记录里有ID，或本地有同名zip"""
    history = downloaded_ids()
    local_keys = scan_local_zip_keys()
    return lambda comic_id, title: comic_id in history or title_key(title) in local_keys


def to_list_items(raw_comics: List[dict]) -> List[dict]:
    """把漫画数据转成前端列表需要的格式，附带已下载标记"""
    is_downloaded = downloaded_checker()

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
            "downloaded": is_downloaded(comic_id, title),
        })
    return items


@router.post("")
def downloaded_flags(body: FlagsBody) -> dict:
    """批量查询是否已下载，下载结束后前端用它刷新标记"""
    is_downloaded = downloaded_checker()
    return {str(item.id): is_downloaded(item.id, item.title) for item in body.items}
