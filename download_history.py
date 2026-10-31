"""
下载记录
记录成功下载的漫画ID，并按标题匹配本地已有的zip文件，用于标记"已下载"
"""
import json
import os
import re
import unicodedata
from datetime import datetime
from typing import Dict, Iterable, Optional, Set

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "download_history.json")

# 下载目录和分类目录（classify_by_author.py 会把zip从downloads移到class）
LOCAL_ZIP_DIRS = [
    os.path.join(BASE_DIR, "downloads"),
    os.path.join(BASE_DIR, "class"),
]


def load_history(path: str = HISTORY_FILE) -> Dict[str, dict]:
    """读取下载记录，key为漫画ID字符串"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def record_download(comic_id: int, title: str = "", path: str = HISTORY_FILE) -> None:
    """记录一次成功下载"""
    history = load_history(path)
    history[str(comic_id)] = {
        "title": title,
        "downloaded_at": datetime.now().isoformat(timespec='seconds'),
    }
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def downloaded_ids(path: str = HISTORY_FILE) -> Set[int]:
    """返回下载记录中的所有漫画ID"""
    ids = set()
    for key in load_history(path):
        if key.isdigit():
            ids.add(int(key))
    return ids


def title_key(title: str) -> str:
    """把标题归一化为匹配用的key：统一全角半角、忽略大小写、去掉符号和空白"""
    normalized = unicodedata.normalize('NFKC', title).lower()
    return re.sub(r'[\W_]+', '', normalized)


def scan_local_zip_keys(dirs: Optional[Iterable[str]] = None) -> Set[str]:
    """扫描本地zip文件，返回文件名对应的标题key"""
    keys = set()
    for base in dirs if dirs is not None else LOCAL_ZIP_DIRS:
        if not os.path.isdir(base):
            continue
        for _root, _dirs, files in os.walk(base):
            for name in files:
                if name.lower().endswith('.zip'):
                    key = title_key(name[:-4])
                    if key:
                        keys.add(key)
    return keys
