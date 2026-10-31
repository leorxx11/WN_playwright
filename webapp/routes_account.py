"""账号：登录状态、验证cookie、重新登录"""
import asyncio
import os

import requests
from fastapi import APIRouter, HTTPException

import config
from webapp.browser_worker import worker

router = APIRouter(prefix="/api/account")


def _username() -> str:
    return os.environ.get('WNACG_USERNAME', '')


@router.get("")
async def account_status() -> dict:
    return {
        "username": _username(),
        "domain": config.API_DOMAIN,
        "cookie": config.read_cookie_info(),
        "login": worker.login.snapshot(),
    }


@router.post("/verify")
async def verify_account() -> dict:
    """用当前cookie访问收藏页，确认是否仍处于登录状态"""
    info = config.read_cookie_info()
    if info is None:
        return {"logged_in": False, "message": "还没有cookie，请先登录"}
    try:
        cookie = config.load_cookie_from_file()
        if cookie is None:
            return {"logged_in": False, "message": "cookie已过期，请重新登录"}
        logged_in = await asyncio.to_thread(config.verify_cookie, cookie)
    except requests.RequestException as e:
        return {"logged_in": False, "message": f"无法连接站点：{e}"}
    return {"logged_in": logged_in, "message": "登录有效" if logged_in else "cookie已失效，请重新登录"}


@router.post("/login")
async def start_login() -> dict:
    if not _username() or not os.environ.get('WNACG_PASSWORD'):
        raise HTTPException(status_code=400, detail="请先在 .env 里设置 WNACG_USERNAME 和 WNACG_PASSWORD")
    if worker.login.busy:
        raise HTTPException(status_code=409, detail="正在登录中")
    worker.login.start()
    return worker.login.snapshot()
