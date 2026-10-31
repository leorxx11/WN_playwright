"""FastAPI 应用：页面、静态文件、封面代理和各功能路由"""
import os
import re
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import config
from webapp import (
    common, routes_account, routes_download, routes_files, routes_jobs, routes_search, routes_shelf,
)

# 封面代理只放行站点图床域名（如 t4.wnimg1.ru / t4.wnimg2.cfd）
COVER_HOST_RE = re.compile(r'(^|\.)wnimg\d*\.[a-z]+$')

app = FastAPI(title="WNACG")
app.include_router(routes_files.router)
app.include_router(routes_files.flags_router)
app.include_router(routes_search.router)
app.include_router(routes_shelf.router)
app.include_router(routes_jobs.router)
app.include_router(routes_download.router)
app.include_router(routes_account.router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(common.WEB_DIR, "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/api/cover")
def cover(url: str) -> Response:
    """带Referer代理封面图，避免图床拦截外链"""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not COVER_HOST_RE.search(parsed.hostname or ''):
        raise HTTPException(status_code=400, detail="不支持的图片地址")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": config.USER_AGENT, "Referer": f"https://{config.API_DOMAIN}/"},
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


class NoCacheStaticFiles(StaticFiles):
    """前端是本地开发中的源码，避免浏览器缓存旧版本"""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", NoCacheStaticFiles(directory=common.WEB_DIR), name="static")
