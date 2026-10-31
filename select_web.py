"""
JSON勾选下载网页
打开 search_results/ 下导出的书架/搜索JSON，勾选后导出为新JSON或直接下载

用法:
    python select_web.py              # 默认端口 8787，可用 WNACG_WEB_PORT 覆盖
    python select_web.py --port 9000 --no-browser
"""
import argparse
import asyncio
import json
import logging
import os
import re
import threading
import webbrowser
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from batch_download import BatchDownloadError, download_comic_list, setup_logging
from config import API_DOMAIN, USER_AGENT
from download_history import downloaded_ids, scan_local_zip_keys, title_key
from search_id import extract_chapter_info

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEARCH_DIR = os.path.join(BASE_DIR, "search_results")
INDEX_HTML = os.path.join(BASE_DIR, "web", "index.html")

DEFAULT_PORT = 8787
HOST = "127.0.0.1"

# 只允许 search_results 下这几类导出文件，避免路径穿越
JSON_NAME_RE = re.compile(r'^(shelf|search|selected)_[^/\\]+\.json$')
# 封面代理只放行站点图床域名（如 t4.wnimg1.ru / t4.wnimg2.cfd）
COVER_HOST_RE = re.compile(r'(^|\.)wnimg\d*\.[a-z]+$')

logger = logging.getLogger("select_web")
app = FastAPI(title="WNACG 勾选下载")


class IdsBody(BaseModel):
    ids: List[int]


class DownloadBody(BaseModel):
    file: str
    ids: List[int]


def _json_path(name: str) -> str:
    """校验文件名并返回search_results下的绝对路径"""
    if not JSON_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="不支持的文件名")
    path = os.path.join(SEARCH_DIR, name)
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
    info = search_info.get('additional_info') or ''
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


def build_file_view(name: str, data: dict) -> dict:
    """组装前端需要的漫画列表，附带已下载标记"""
    history = downloaded_ids()
    local_keys = scan_local_zip_keys()

    comics = []
    for comic in data['comics']:
        comic_id = comic.get('id')
        if not isinstance(comic_id, int):
            continue
        title = comic.get('title') or f"Comic_{comic_id}"
        chapter_start, chapter_end = _chapter_range(title)
        comics.append({
            "id": comic_id,
            "title": title,
            "cover": comic.get('cover') or '',
            "info": _comic_info(comic),
            "chapter_start": chapter_start,
            "chapter_end": chapter_end,
            "downloaded": comic_id in history or title_key(title) in local_keys,
        })

    return {
        "name": name,
        "label": _file_label(data),
        "comics": comics,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})


@app.get("/api/files")
def list_files() -> List[dict]:
    """列出可勾选的JSON文件，最新的在前"""
    if not os.path.isdir(SEARCH_DIR):
        return []

    files = []
    for name in os.listdir(SEARCH_DIR):
        if not JSON_NAME_RE.match(name):
            continue
        path = os.path.join(SEARCH_DIR, name)
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


@app.get("/api/files/{name}")
def get_file(name: str) -> dict:
    return build_file_view(name, _load_json(_json_path(name)))


@app.post("/api/files/{name}/export")
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
    with open(os.path.join(SEARCH_DIR, out_name), 'w', encoding='utf-8') as f:
        json.dump(exported, f, ensure_ascii=False, indent=2)
    return {"name": out_name, "count": len(comics)}


@app.get("/api/cover")
def cover(url: str) -> Response:
    """带Referer代理封面图，避免图床拦截外链"""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not COVER_HOST_RE.search(parsed.hostname or ''):
        raise HTTPException(status_code=400, detail="不支持的图片地址")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Referer": f"https://{API_DOMAIN}/"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"封面获取失败: {e}")
    return Response(
        content=resp.content,
        media_type=resp.headers.get('Content-Type', 'image/jpeg'),
        headers={"Cache-Control": "public, max-age=604800"},
    )


class DownloadJob:
    """网页触发的批量下载任务；同一时间只运行一个（共用 .playwright_profile）"""

    def __init__(self) -> None:
        self.running = False
        self.stop_requested = False
        self.file = ""
        self.items: List[dict] = []
        self.message = ""
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._logger: Optional[logging.Logger] = None

    def snapshot(self) -> dict:
        counts: Dict[str, int] = {}
        for item in self.items:
            counts[item['status']] = counts.get(item['status'], 0) + 1
        return {
            "running": self.running,
            "stop_requested": self.stop_requested,
            "file": self.file,
            "items": self.items,
            "counts": counts,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def start(self, file: str, comics: List[dict]) -> None:
        if self._logger is None:
            self._logger, _log_file = setup_logging()
        self.running = True
        self.stop_requested = False
        self.file = file
        self.items = [{"id": c['id'], "title": c.get('title', ''), "status": "pending"} for c in comics]
        self.message = f"开始下载 {len(comics)} 部，浏览器窗口如出现Cloudflare验证请手动完成"
        self.started_at = datetime.now().isoformat(timespec='seconds')
        self.finished_at = None
        self._task = asyncio.create_task(self._run(comics))

    def _set_status(self, comic_id: int, status: str) -> None:
        for item in self.items:
            if item['id'] == comic_id:
                item['status'] = status
                break

    async def _run(self, comics: List[dict]) -> None:
        try:
            await download_comic_list(
                comics,
                self._logger,
                on_status=self._set_status,
                should_stop=lambda: self.stop_requested,
                # 网页里是明确勾选的，不按下载记录跳过
                skip_downloaded=False,
            )
            done = sum(1 for i in self.items if i['status'] in ('done', 'skipped'))
            failed = sum(1 for i in self.items if i['status'] == 'failed')
            self.message = f"{'已停止' if self.stop_requested else '下载完成'}：成功 {done}，失败 {failed}"
        except BatchDownloadError as e:
            self.message = f"下载失败：{e}"
        except Exception as e:
            logger.exception("download job crashed")
            self.message = f"下载出错：{e}"
        finally:
            for item in self.items:
                if item['status'] in ('pending', 'downloading'):
                    item['status'] = 'cancelled'
            self.running = False
            self.finished_at = datetime.now().isoformat(timespec='seconds')


job = DownloadJob()


@app.get("/api/download")
async def download_status() -> dict:
    return job.snapshot()


@app.post("/api/download")
async def start_download(body: DownloadBody) -> dict:
    if job.running:
        raise HTTPException(status_code=409, detail="已有下载任务在运行")
    data = _load_json(_json_path(body.file))
    wanted = set(body.ids)
    comics = [c for c in data['comics'] if c.get('id') in wanted]
    if not comics:
        raise HTTPException(status_code=400, detail="没有勾选任何漫画")
    job.start(body.file, comics)
    return job.snapshot()


@app.post("/api/download/stop")
async def stop_download() -> dict:
    if job.running:
        job.stop_requested = True
        job.message = "当前这部下载完后停止..."
    return job.snapshot()


def main() -> None:
    parser = argparse.ArgumentParser(description="WNACG JSON勾选下载网页")
    parser.add_argument('--port', type=int, default=int(os.environ.get('WNACG_WEB_PORT', DEFAULT_PORT)))
    parser.add_argument('--no-browser', action='store_true', help="不自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{HOST}:{args.port}"
    print(f"=== WNACG 勾选下载 ===\n打开 {url}  (Ctrl+C 退出)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    # Playwright 需要标准asyncio事件循环
    uvicorn.run(app, host=HOST, port=args.port, loop="asyncio", log_level="warning")


if __name__ == "__main__":
    main()
