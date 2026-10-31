import time

import pytest
from fastapi.testclient import TestClient

import config
from get_shelf_info import ComicInFavorite, Shelf
from webapp import comic_items, common, routes_search, routes_shelf
from webapp.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(common, "SEARCH_DIR", str(tmp_path / "search_results"))
    monkeypatch.setattr(config, "load_cookie_from_file", lambda: "a=b")
    monkeypatch.setattr(comic_items, "downloaded_ids", lambda: {2})
    monkeypatch.setattr(comic_items, "scan_local_zip_keys", lambda: set())
    monkeypatch.setattr(routes_search, "PAGE_INTERVAL_SECONDS", 0)
    with TestClient(app) as test_client:
        yield test_client


def wait_job(client, job_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def fake_search_pages(pages):
    """pages: 每页的漫画ID列表"""
    calls = []

    def search(query, page_num, cookie=None):
        calls.append((query, page_num, cookie))
        ids = pages[page_num - 1] if page_num <= len(pages) else []
        return {
            "comics": [{"id": i, "title": f"{query} {i}話", "cover": "", "title_html": "", "additional_info": "10張圖片"}
                       for i in ids],
            "current_page": page_num,
            "total_page": len(pages),
        }

    return search, calls


# ---------- 搜索 ----------

def test_search_collects_pages_dedupes_and_marks_downloaded(client, monkeypatch):
    search, calls = fake_search_pages([[1, 2], [2, 3]])
    monkeypatch.setattr(routes_search, "search_by_tag", search)

    job = client.post("/api/search", json={"query": "玩轉學姊", "type": "tag", "max_pages": 5}).json()
    result = wait_job(client, job["id"])

    assert result["state"] == "done"
    assert [c["id"] for c in result["items"]] == [1, 2, 3]
    assert [c["downloaded"] for c in result["items"]] == [False, True, False]
    assert result["items"][0]["chapter_start"] == 1
    assert calls == [("玩轉學姊", 1, "a=b"), ("玩轉學姊", 2, "a=b")]


def test_search_respects_max_pages(client, monkeypatch):
    search, calls = fake_search_pages([[1], [2], [3]])
    monkeypatch.setattr(routes_search, "search_by_keyword", search)

    job = client.post("/api/search", json={"query": "x", "max_pages": 2}).json()
    result = wait_job(client, job["id"])
    assert [c["id"] for c in result["items"]] == [1, 2]
    assert len(calls) == 2


def test_search_requires_cookie(client, monkeypatch):
    monkeypatch.setattr(config, "load_cookie_from_file", lambda: None)
    resp = client.post("/api/search", json={"query": "x"})
    assert resp.status_code == 401
    assert "账号" in resp.json()["detail"]


def test_search_rejects_empty_query(client):
    assert client.post("/api/search", json={"query": "  "}).status_code == 400


def test_search_error_is_reported(client, monkeypatch):
    def broken(query, page_num, cookie=None):
        raise RuntimeError("请求失败: timeout")

    monkeypatch.setattr(routes_search, "search_by_keyword", broken)
    job = client.post("/api/search", json={"query": "x"}).json()
    result = wait_job(client, job["id"])
    assert result["state"] == "failed"
    assert "timeout" in result["message"]


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/missing").status_code == 404


# ---------- 书架 ----------

def test_list_shelves(client, monkeypatch):
    async def fake_get_shelves(session, cookie):
        return [Shelf(0, "全部"), Shelf(1725968, "12-17")]

    monkeypatch.setattr(routes_shelf, "get_shelves", fake_get_shelves)
    assert client.get("/api/shelves").json() == [{"id": 0, "name": "全部"}, {"id": 1725968, "name": "12-17"}]


def test_list_shelves_login_required(client, monkeypatch):
    async def fake_get_shelves(session, cookie):
        raise ValueError("Cookie已过期或无效")

    monkeypatch.setattr(routes_shelf, "get_shelves", fake_get_shelves)
    assert client.get("/api/shelves").status_code == 401


def test_fetch_shelf(client, monkeypatch):
    shelf = Shelf(1725968, "12-17")

    async def fake_all(session, cookie, shelf_id, on_progress=None):
        on_progress(1, 2)
        on_progress(2, 2)
        return [
            ComicInFavorite(1, "A", "https://t4.wnimg1.ru/a.jpg", "2026-03-30 23:54:45", shelf),
            ComicInFavorite(2, "B", "", "2026-03-30 23:53:54", shelf),
        ]

    monkeypatch.setattr(routes_shelf, "get_all_comics_from_shelf", fake_all)

    job = client.post("/api/shelves/1725968/fetch", params={"name": "12-17"}).json()
    result = wait_job(client, job["id"])
    assert result["state"] == "done"
    assert (result["done_pages"], result["total_pages"]) == (2, 2)
    assert [c["info"] for c in result["items"]] == ["收藏于 2026-03-30 23:54:45", "收藏于 2026-03-30 23:53:54"]


def test_empty_shelf_with_expired_login_fails(client, monkeypatch):
    async def fake_all(session, cookie, shelf_id, on_progress=None):
        return []

    async def fake_get_shelves(session, cookie):
        raise ValueError("Cookie已过期或无效")

    monkeypatch.setattr(routes_shelf, "get_all_comics_from_shelf", fake_all)
    monkeypatch.setattr(routes_shelf, "get_shelves", fake_get_shelves)

    job = client.post("/api/shelves/0/fetch").json()
    result = wait_job(client, job["id"])
    assert result["state"] == "failed"
    assert "账号" in result["message"]


# ---------- 已下载标记 ----------

def test_downloaded_flags(client):
    resp = client.post("/api/downloaded", json={"items": [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]})
    assert resp.json() == {"1": False, "2": True}
