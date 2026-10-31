import json
import time

import pytest
from fastapi.testclient import TestClient

import select_web

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
def client(tmp_path, monkeypatch):
    search_dir = tmp_path / "search_results"
    search_dir.mkdir()
    (search_dir / "search_玩轉學姊_all_20261031_173031.json").write_text(
        json.dumps(SEARCH_DATA, ensure_ascii=False), encoding="utf-8")
    (search_dir / "notes.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(select_web, "SEARCH_DIR", str(search_dir))
    monkeypatch.setattr(select_web, "downloaded_ids", lambda: {2})
    monkeypatch.setattr(select_web, "scan_local_zip_keys", lambda: {select_web.title_key("Local Copy")})
    monkeypatch.setattr(select_web, "job", select_web.DownloadJob())

    with TestClient(select_web.app) as test_client:
        yield test_client


NAME = "search_玩轉學姊_all_20261031_173031.json"


def test_list_files_only_includes_export_files(client):
    files = client.get("/api/files").json()
    assert [f["name"] for f in files] == [NAME]
    assert files[0]["count"] == 3
    assert files[0]["label"] == "搜索：玩轉學姊"


def test_get_file_marks_downloaded_and_parses_chapters(client):
    data = client.get(f"/api/files/{NAME}").json()
    comics = {c["id"]: c for c in data["comics"]}

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

    with open(f"{select_web.SEARCH_DIR}/{res['name']}", encoding="utf-8") as f:
        exported = json.load(f)
    assert [c["id"] for c in exported["comics"]] == [1, 3]
    assert exported["total_comics"] == 2
    assert exported["search_metadata"]["search_query"] == "玩轉學姊"
    assert exported["selection_metadata"]["source_file"] == NAME


def test_export_requires_selection(client):
    assert client.post(f"/api/files/{NAME}/export", json={"ids": []}).status_code == 400


def test_cover_proxy_only_allows_image_hosts(client):
    assert client.get("/api/cover", params={"url": "https://evil.example.com/a.jpg"}).status_code == 400
    assert client.get("/api/cover", params={"url": "file:///etc/passwd"}).status_code == 400


def test_download_job_reports_statuses(client, monkeypatch):
    calls = {}

    async def fake_download(comics, logger, on_status=None, should_stop=None, skip_downloaded=True):
        calls["ids"] = [c["id"] for c in comics]
        calls["skip_downloaded"] = skip_downloaded
        on_status(comics[0]["id"], "done")
        on_status(comics[1]["id"], "failed")

    monkeypatch.setattr(select_web, "download_comic_list", fake_download)
    monkeypatch.setattr(select_web.DownloadJob, "start", _start_without_log_file(select_web.DownloadJob.start))

    started = client.post("/api/download", json={"file": NAME, "ids": [2, 1]})
    assert started.status_code == 200

    for _ in range(50):
        status = client.get("/api/download").json()
        if not status["running"]:
            break
        time.sleep(0.02)

    assert calls == {"ids": [1, 2], "skip_downloaded": False}
    assert {i["id"]: i["status"] for i in status["items"]} == {1: "done", 2: "failed"}
    assert status["message"] == "下载完成：成功 1，失败 1"


def _start_without_log_file(original):
    def start(self, file, comics):
        self._logger = select_web.logger
        original(self, file, comics)
    return start


def test_download_requires_selection(client):
    assert client.post("/api/download", json={"file": NAME, "ids": []}).status_code == 400
