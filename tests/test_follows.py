import json
import os
import time

import pytest
from fastapi.testclient import TestClient

import config
from webapp import comic_items, common, follows, routes_search
from webapp.app import app

OLD_EXPORT = {
    "comics": [
        {"id": 1, "title": "玩轉學姊 127-128話[完結]", "cover": ""},
        {"id": 2, "title": "玩轉學姊 124話", "cover": ""},
    ],
    "search_metadata": {"search_query": "玩轉學姊", "search_time": "2026-10-31T17:30:31.421621"},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    search_dir = tmp_path / "search_results"
    search_dir.mkdir()
    older = search_dir / "search_玩轉學姊_all_20261030_100000.json"
    older.write_text(json.dumps({**OLD_EXPORT, "comics": OLD_EXPORT["comics"][:1]}, ensure_ascii=False), encoding="utf-8")
    os.utime(older, (1, 1))
    (search_dir / "search_玩轉學姊_all_20261031_173031.json").write_text(json.dumps(OLD_EXPORT, ensure_ascii=False), encoding="utf-8")
    (search_dir / "shelf_12-17_20260402_101644.json").write_text('{"comics": []}', encoding="utf-8")

    monkeypatch.setattr(common, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(common, "SEARCH_DIR", str(search_dir))
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


def fake_search(ids):
    def search(query, page_num, cookie=None):
        return {"comics": [{"id": i, "title": f"{query} {i}話", "cover": ""} for i in ids],
                "current_page": page_num, "total_page": 1}
    return search


def test_old_search_exports_imported_once(client, tmp_path):
    data = client.get("/api/follows").json()
    # 只导入搜索导出，同一个搜索词取最新的文件
    assert [(f["query"], f["type"], f["total"], f["undownloaded"]) for f in data] == [("玩轉學姊", "keyword", 2, 1)]
    assert data[0]["checked_at"] == "2026-10-31T17:30:31"

    client.delete(f"/api/follows/{data[0]['id']}")
    assert client.get("/api/follows").json() == []   # 删除后不会再导入
    assert (tmp_path / "search_results" / "search_玩轉學姊_all_20261031_173031.json").exists()


def test_follow_from_finished_search(client, monkeypatch):
    monkeypatch.setattr(routes_search, "search_by_tag", fake_search([5, 6]))
    job = client.post("/api/search", json={"query": "新作", "type": "tag"}).json()
    wait_job(client, job["id"])

    created = client.post("/api/follows", json={"query": "新作", "type": "tag", "job_id": job["id"]}).json()
    assert (created["total"], created["undownloaded"]) == (2, 2)
    # 同类型同搜索词不会重复创建
    again = client.post("/api/follows", json={"query": "新作", "type": "tag"}).json()
    assert again["id"] == created["id"]
    assert [f["query"] for f in client.get("/api/follows").json()] == ["新作", "玩轉學姊"]

    detail = client.get(f"/api/follows/{created['id']}").json()
    assert [c["id"] for c in detail["items"]] == [5, 6]


def test_refresh_replaces_items(client, monkeypatch):
    follow = client.get("/api/follows").json()[0]
    monkeypatch.setattr(routes_search, "search_by_keyword", fake_search([1, 2, 3]))

    job = client.post(f"/api/follows/{follow['id']}/refresh").json()
    assert wait_job(client, job["id"])["state"] == "done"
    time.sleep(0.05)
    after = client.get(f"/api/follows/{follow['id']}").json()
    assert [c["id"] for c in after["items"]] == [1, 2, 3]
    assert after["undownloaded"] == 2
    assert after["checked_at"] != follow["checked_at"]


def test_patch_folder_and_type(client):
    follow = client.get("/api/follows").json()[0]
    res = client.patch(f"/api/follows/{follow['id']}", json={"folder": " 玩轉學姊 ", "type": "tag"}).json()
    assert (res["folder"], res["type"]) == ("玩轉學姊", "tag")
    assert follows.folder_hints()["玩轉學姊124話"] == ("玩轉學姊", "玩轉學姊")
    assert client.patch("/api/follows/missing", json={"folder": "x"}).status_code == 404


def test_classify_uses_follow_folder(client, tmp_path):
    follow = client.get("/api/follows").json()[0]
    client.patch(f"/api/follows/{follow['id']}", json={"folder": "玩轉學姊"})
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "玩轉學姊 124話.zip").write_bytes(b"zip")
    (downloads / "玩轉學姊 999話.zip").write_bytes(b"zip")   # 不在追更结果里

    groups = client.get("/api/classify").json()["groups"]
    assert [(g["kind"], g["label"], g["folder"], [f["name"] for f in g["files"]]) for g in groups] == [
        ("follow", "玩轉學姊", "玩轉學姊", ["玩轉學姊 124話.zip"]),
        ("other", "玩轉學姊", "other", ["玩轉學姊 999話.zip"]),
    ]
    assert client.get("/api/classify/count").json() == {"count": 2}
