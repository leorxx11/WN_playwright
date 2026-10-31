import json
from datetime import datetime

import download_history


def test_record_and_load_ids(tmp_path):
    path = str(tmp_path / "history.json")
    assert download_history.downloaded_ids(path) == set()

    download_history.record_download(123, "标题A", path)
    download_history.record_download(456, path=path)

    assert download_history.downloaded_ids(path) == {123, 456}
    assert download_history.load_history(path)["123"]["title"] == "标题A"


def test_load_history_ignores_corrupt_file(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not json", encoding="utf-8")
    assert download_history.load_history(str(path)) == {}


def test_title_key_ignores_width_case_and_symbols():
    assert download_history.title_key("[作者] 標題 ＡＢＣ（1）") == download_history.title_key("[作者]標題_abc(1)")
    assert download_history.title_key("玩轉學姊 124話") != download_history.title_key("玩轉學姊 125話")


def test_scan_local_zip_keys_walks_subdirectories(tmp_path):
    (tmp_path / "downloads").mkdir()
    (tmp_path / "class" / "作者").mkdir(parents=True)
    (tmp_path / "downloads" / "Comic One.zip").write_bytes(b"")
    (tmp_path / "class" / "作者" / "Comic Two.ZIP").write_bytes(b"")
    (tmp_path / "downloads" / "notes.txt").write_bytes(b"")

    keys = download_history.scan_local_zip_keys([str(tmp_path / "downloads"), str(tmp_path / "class"), str(tmp_path / "missing")])

    assert keys == {download_history.title_key("Comic One"), download_history.title_key("Comic Two")}


def test_download_quota_counts_last_24_hours(tmp_path):
    download_quota = download_history.download_quota
    path = tmp_path / "history.json"
    now = datetime(2026, 11, 1, 12, 0, 0)
    records = {
        "1": {"title": "old", "downloaded_at": "2026-10-31T11:59:59"},   # 超过24小时
        "2": {"title": "a", "downloaded_at": "2026-10-31T13:00:00"},
        "3": {"title": "b", "downloaded_at": "2026-11-01T09:00:00"},
        "4": {"title": "bad", "downloaded_at": "oops"},
    }
    path.write_text(json.dumps(records), encoding="utf-8")

    assert download_quota(limit=3, path=str(path), now=now) == {
        "used": 2, "limit": 3, "remaining": 1, "next_free_at": None,
    }
    # 额度用完时，最早那次满24小时后空出额度
    assert download_quota(limit=2, path=str(path), now=now)["next_free_at"] == "2026-11-01T13:00:00"
    assert download_quota(limit=2, path=str(path), now=now)["remaining"] == 0
