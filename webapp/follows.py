"""追更：保存的搜索，记住上次的结果和整理到 class/ 的哪个文件夹

数据存在 follows.json；第一次读取时把 search_results/ 里旧的 search_*.json 导入进来（原文件保留）。
"""
import json
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from download_history import title_key
from webapp import common

_lock = threading.Lock()


def _path() -> str:
    return os.path.join(common.BASE_DIR, "follows.json")


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def new_follow(search_type: str, query: str, max_pages: int = 20, folder: str = "",
               items: Optional[List[dict]] = None, checked_at: Optional[str] = None) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "type": search_type,
        "query": query,
        "max_pages": max_pages,
        "folder": folder,
        "created_at": _now(),
        "checked_at": checked_at,
        "items": items or [],
    }


def _import_search_exports() -> List[dict]:
    """把旧的搜索导出转成追更；同一个搜索词有多个文件时取最新的"""
    if not os.path.isdir(common.SEARCH_DIR):
        return []
    names = [n for n in os.listdir(common.SEARCH_DIR) if n.startswith('search_') and n.endswith('.json')]
    names.sort(key=lambda n: os.path.getmtime(os.path.join(common.SEARCH_DIR, n)), reverse=True)

    follows, seen = [], set()
    for name in names:
        try:
            with open(os.path.join(common.SEARCH_DIR, name), 'r', encoding='utf-8') as f:
                data = json.load(f)
            meta = data.get('search_metadata') or {}
            query = (meta.get('search_query') or '').strip()
            comics = data.get('comics')
        except (json.JSONDecodeError, OSError, AttributeError):
            continue
        if not query or query in seen or not isinstance(comics, list):
            continue
        seen.add(query)
        # 旧导出没有记录是关键词还是标签，按关键词导入，可在页面上改
        follows.append(new_follow("keyword", query, items=comics, checked_at=meta.get('search_time', '')[:19] or None))
    return follows


def _read() -> List[dict]:
    if not os.path.exists(_path()):
        follows = _import_search_exports()
        _write(follows)
        return follows
    try:
        with open(_path(), 'r', encoding='utf-8') as f:
            follows = json.load(f).get('follows', [])
    except (json.JSONDecodeError, OSError, AttributeError):
        return []
    return [f for f in follows if isinstance(f, dict) and f.get('id')]


def _write(follows: List[dict]) -> None:
    tmp_path = f"{_path()}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump({"follows": follows}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, _path())


def load_follows() -> List[dict]:
    with _lock:
        return _read()


def get_follow(follow_id: str) -> Optional[dict]:
    return next((f for f in load_follows() if f['id'] == follow_id), None)


def add_follow(search_type: str, query: str, max_pages: int, folder: str,
               items: Optional[List[dict]]) -> dict:
    """新建追更；同类型同搜索词已存在时更新它（有结果时覆盖结果）"""
    with _lock:
        follows = _read()
        existing = next((f for f in follows if f['type'] == search_type and f['query'] == query), None)
        if existing:
            if items is not None:
                existing['items'] = items
                existing['checked_at'] = _now()
            follow = existing
        else:
            follow = new_follow(search_type, query, max_pages, folder, items, _now() if items is not None else None)
            follows.insert(0, follow)
        _write(follows)
        return follow


def update_follow(follow_id: str, **fields) -> Optional[dict]:
    with _lock:
        follows = _read()
        follow = next((f for f in follows if f['id'] == follow_id), None)
        if follow is None:
            return None
        follow.update({k: v for k, v in fields.items() if v is not None})
        _write(follows)
        return follow


def set_follow_items(follow_id: str, items: List[dict]) -> Optional[dict]:
    return update_follow(follow_id, items=items, checked_at=_now())


def delete_follow(follow_id: str) -> bool:
    with _lock:
        follows = _read()
        remaining = [f for f in follows if f['id'] != follow_id]
        if len(remaining) == len(follows):
            return False
        _write(remaining)
        return True


def folder_hints() -> Dict[str, Tuple[str, str]]:
    """设置了整理文件夹的追更：标题key -> (追更名, 文件夹)，分类时用来认出这些漫画"""
    hints = {}
    for follow in load_follows():
        folder = (follow.get('folder') or '').strip()
        if not folder:
            continue
        for comic in follow.get('items', []):
            key = title_key(comic.get('title') or '')
            if key:
                hints.setdefault(key, (follow['query'], folder))
    return hints
