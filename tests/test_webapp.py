import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

import config
from webapp import browser_worker, common, routes_account, routes_download, routes_files
from webapp.app import app

NAME = "search_玩轉學姊_all_20261031_173031.json"
SEARCH_DATA = {
    "comics": [
        {
            "id": 1,
            "title": "玩轉學姊 127-128話[完結]",
            "cover": "https://t4.wnimg2.cfd/data/t/1.jpg",
            "favorite_time": "",
            "search_info": {"additional_info": "35張圖片，\n\t\t創建於2026-10-19"},
        },
        {"id": 2, "title": "玩轉學姊 124話", "cover": "", "favorite_time": ""},
        {"id": 3, "title": "Local Copy", "cover": "", "favorite_time": "2026-03-30 23:54:45"},
    ],
    "total_comics": 3,
    "search_metadata": {"search_query": "玩轉學姊"},
}


@pytest.fixture
def worker(monkeypatch, tmp_path):
    fresh = browser_worker.BrowserWorker(queue_path=str(tmp_path / "queue.json"))
    monkeypatch.setattr(routes_download, "worker", fresh)
    monkeypatch.setattr(routes_account, "worker", fresh)
    monkeypatch.setattr(browser_worker, "setup_logging", lambda: (browser_worker.logger, ""))
    return fresh


@pytest.fixture
def client(tmp_path, monkeypatch, worker):
    search_dir = tmp_path / "search_results"
    search_dir.mkdir()
    (search_dir / NAME).write_text(json.dumps(SEARCH_DATA, ensure_ascii=False), encoding="utf-8")
    (search_dir / "notes.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(common, "SEARCH_DIR", str(search_dir))
    monkeypatch.setattr(routes_files, "downloaded_ids", lambda: {2})
    monkeypatch.setattr(routes_files, "scan_local_zip_keys", lambda: {routes_files.title_key("Local Copy")})

    with TestClient(app) as test_client:
        yield test_client


def wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# ---------- 页面与静态文件 ----------

def test_index_and_static_files(client):
    assert "WNACG" in client.get("/").text
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


def test_cover_proxy_only_allows_image_hosts(client):
    assert client.get("/api/cover", params={"url": "https://evil.example.com/a.jpg"}).status_code == 400
    assert client.get("/api/cover", params={"url": "file:///etc/passwd"}).status_code == 400


# ---------- 已导出JSON ----------

def test_list_files_only_includes_export_files(client):
    files = client.get("/api/files").json()
    assert [f["name"] for f in files] == [NAME]
    assert files[0]["count"] == 3
    assert files[0]["label"] == "搜索：玩轉學姊"


def test_get_file_marks_downloaded_and_parses_chapters(client):
    comics = {c["id"]: c for c in client.get(f"/api/files/{NAME}").json()["comics"]}

    assert comics[1]["downloaded"] is False
    assert comics[2]["downloaded"] is True   # 在下载记录里
    assert comics[3]["downloaded"] is True   # 本地有同名zip
    assert (comics[1]["chapter_start"], comics[1]["chapter_end"]) == (127, 128)
    assert (comics[2]["chapter_start"], comics[2]["chapter_end"]) == (124, 124)
    assert comics[1]["info"] == "35張圖片， 創建於2026-10-19"
    assert comics[3]["info"] == "收藏于 2026-03-30 23:54:45"


def test_rejects_unknown_file_names(client):
    assert client.get("/api/files/notes.json").status_code == 400
    assert client.get("/api/files/search_missing.json").status_code == 404


def test_export_keeps_file_order_and_metadata(client):
    res = client.post(f"/api/files/{NAME}/export", json={"ids": [3, 1]}).json()
    assert res["count"] == 2
    assert res["name"].startswith("selected_玩轉學姊_all_")

    with open(f"{common.SEARCH_DIR}/{res['name']}", encoding="utf-8") as f:
        exported = json.load(f)
    assert [c["id"] for c in exported["comics"]] == [1, 3]
    assert exported["total_comics"] == 2
    assert exported["search_metadata"]["search_query"] == "玩轉學姊"
    assert exported["selection_metadata"]["source_file"] == NAME


def test_export_requires_selection(client):
    assert client.post(f"/api/files/{NAME}/export", json={"ids": []}).status_code == 400


# ---------- 下载（基本流程，队列细节见 test_download_queue.py） ----------

def test_download_reports_statuses(client, monkeypatch):
    calls = {}

    async def fake_download(comics, logger, on_status=None, should_stop=None, skip_downloaded=True, has_more=None):
        calls["skip_downloaded"] = skip_downloaded
        calls["ids"] = []
        for comic in comics:
            calls["ids"].append(comic["id"])
            on_status(comic["id"], "done" if comic["id"] == 2 else "failed")

    monkeypatch.setattr(browser_worker, "download_comic_list", fake_download)

    items = [{"id": 2, "title": "b"}, {"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
    assert client.post("/api/download", json={"items": items}).json()["added"] == 2
    assert wait_until(lambda: not client.get("/api/download").json()["running"])

    status = client.get("/api/download").json()
    assert calls == {"ids": [2, 1], "skip_downloaded": False}   # 去重并保持顺序
    assert {i["id"]: i["status"] for i in status["items"]} == {2: "done", 1: "failed"}
    assert status["message"] == "队列已完成，失败 1 部"


def test_download_with_no_items_does_nothing(client):
    data = client.post("/api/download", json={"items": []}).json()
    assert data["added"] == 0
    assert data["running"] is False


# ---------- 账号 ----------

def test_account_status(client, monkeypatch):
    monkeypatch.setenv("WNACG_USERNAME", "tester")
    monkeypatch.setattr(config, "read_cookie_info", lambda: {"created_at": "2026-10-31T17:26:02", "expired": False})

    data = client.get("/api/account").json()
    assert data["username"] == "tester"
    assert data["domain"] == config.API_DOMAIN
    assert data["cookie"]["expired"] is False
    assert data["login"]["state"] == "idle"


def test_verify_without_cookie(client, monkeypatch):
    monkeypatch.setattr(config, "read_cookie_info", lambda: None)
    assert client.post("/api/account/verify").json() == {"logged_in": False, "message": "还没有cookie，请先登录"}


def test_verify_with_cookie(client, monkeypatch):
    monkeypatch.setattr(config, "read_cookie_info", lambda: {"expired": False})
    monkeypatch.setattr(config, "load_cookie_from_file", lambda: "a=b")
    monkeypatch.setattr(config, "verify_cookie", lambda cookie: cookie == "a=b")
    assert client.post("/api/account/verify").json()["logged_in"] is True


def test_login_requires_credentials(client, monkeypatch):
    monkeypatch.delenv("WNACG_USERNAME", raising=False)
    assert client.post("/api/account/login").status_code == 400


def test_login_success(client, monkeypatch):
    monkeypatch.setenv("WNACG_USERNAME", "tester")
    monkeypatch.setenv("WNACG_PASSWORD", "secret")
    monkeypatch.setattr(config, "refresh_cookie", lambda: "new-cookie")

    assert client.post("/api/account/login").status_code == 200
    assert wait_until(lambda: client.get("/api/account").json()["login"]["state"] == "success")


def test_login_failure_is_reported(client, monkeypatch):
    monkeypatch.setenv("WNACG_USERNAME", "tester")
    monkeypatch.setenv("WNACG_PASSWORD", "secret")

    def fail():
        raise RuntimeError("未安装Playwright Chromium")

    monkeypatch.setattr(config, "refresh_cookie", fail)
    client.post("/api/account/login")
    assert wait_until(lambda: client.get("/api/account").json()["login"]["state"] == "failed")
    assert "未安装Playwright Chromium" in client.get("/api/account").json()["login"]["message"]


# ---------- 浏览器锁：登录要等下载结束 ----------

def test_login_waits_for_running_download(worker, monkeypatch):
    order = []

    async def scenario():
        release = asyncio.Event()

        async def slow_download(comics, logger, on_status=None, should_stop=None, skip_downloaded=True, has_more=None):
            for comic in comics:
                order.append("download-start")
                await release.wait()
                on_status(comic["id"], "done")
                order.append("download-end")

        def fake_login():
            order.append("login")
            return "cookie"

        monkeypatch.setattr(browser_worker, "download_comic_list", slow_download)
        monkeypatch.setattr(config, "refresh_cookie", fake_login)

        worker.download.add([{"id": 1, "title": "a"}])
        worker.download.start()
        await asyncio.sleep(0.01)
        worker.login.start()
        assert worker.login.state == "waiting"

        await asyncio.sleep(0.05)
        assert order == ["download-start"]   # 下载占着浏览器，登录还没开始

        release.set()
        await worker.login._task
        assert worker.login.state == "success"

    asyncio.run(scenario())
    assert order == ["download-start", "download-end", "login"]
