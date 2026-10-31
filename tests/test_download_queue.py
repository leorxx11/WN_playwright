import asyncio
import json

import pytest

from webapp import browser_worker
from webapp.browser_worker import DownloadQueue


@pytest.fixture(autouse=True)
def no_log_file(monkeypatch):
    monkeypatch.setattr(browser_worker, "setup_logging", lambda: (browser_worker.logger, ""))


def make_queue(tmp_path):
    return DownloadQueue(asyncio.Lock(), str(tmp_path / "queue.json"))


def statuses(queue):
    return {item["id"]: item["status"] for item in queue.items}


def test_add_dedupes_pending_and_requeues_finished(tmp_path):
    queue = make_queue(tmp_path)
    assert queue.add([{"id": 1, "title": "a"}, {"id": 2, "title": ""}]) == 2
    # 等待中的不重复加入，但会补上标题
    assert queue.add([{"id": 2, "title": "b"}]) == 0
    assert queue.items[1]["title"] == "b"

    queue.items[0]["status"] = "failed"
    assert queue.add([{"id": 1, "title": ""}]) == 1
    assert [i["id"] for i in queue.items] == [2, 1]   # 结束的重新排到队尾
    assert queue.items[1]["title"] == "a"             # 保留原标题
    assert statuses(queue) == {2: "pending", 1: "pending"}


def test_queue_persists_and_restores_interrupted_as_pending(tmp_path):
    queue = make_queue(tmp_path)
    queue.add([{"id": 1, "title": "a"}, {"id": 2, "title": "b"}])
    queue.items[0]["status"] = "downloading"
    queue.items[1]["status"] = "done"
    queue._save()

    restored = make_queue(tmp_path)
    assert statuses(restored) == {1: "pending", 2: "done"}
    assert restored.running is False          # 不自动开始
    assert "继续" in restored.message


def test_corrupt_queue_file_is_ignored(tmp_path):
    (tmp_path / "queue.json").write_text("{oops", encoding="utf-8")
    assert make_queue(tmp_path).items == []


def test_retry_remove_and_clear(tmp_path):
    queue = make_queue(tmp_path)
    queue.add([{"id": i, "title": str(i)} for i in range(1, 6)])
    for item, status in zip(queue.items, ["done", "skipped", "failed", "cancelled", "downloading"]):
        item["status"] = status

    assert queue.retry([3]) == 1
    assert statuses(queue)[3] == "pending"
    assert queue.retry() == 1                 # 剩下的已取消
    assert statuses(queue)[4] == "pending"

    assert queue.remove([3, 5]) == 1          # 正在下载的不能移除
    assert 5 in statuses(queue)

    assert queue.clear_finished() == 2
    assert statuses(queue) == {4: "pending", 5: "downloading"}

    with open(tmp_path / "queue.json", encoding="utf-8") as f:
        assert [i["id"] for i in json.load(f)["items"]] == [4, 5]


def test_items_added_while_running_are_downloaded_in_same_session(tmp_path, monkeypatch):
    queue = make_queue(tmp_path)
    sessions = []

    async def fake_download(comics, logger, on_status=None, should_stop=None, skip_downloaded=True, has_more=None):
        session = []
        sessions.append(session)
        for comic in comics:
            session.append(comic["id"])
            if comic["id"] == 1:
                queue.add([{"id": 3, "title": "c"}])   # 下载第一部时追加
            await asyncio.sleep(0)
            on_status(comic["id"], "done")

    monkeypatch.setattr(browser_worker, "download_comic_list", fake_download)

    async def scenario():
        queue.add([{"id": 1, "title": "a"}, {"id": 2, "title": "b"}])
        queue.start()
        await queue._task

    asyncio.run(scenario())
    assert sessions == [[1, 2, 3]]            # 同一次浏览器会话里接着下
    assert statuses(queue) == {1: "done", 2: "done", 3: "done"}
    assert all(item.get("finished_at") for item in queue.items)


def test_stop_pauses_and_keeps_rest_pending(tmp_path, monkeypatch):
    queue = make_queue(tmp_path)

    async def fake_download(comics, logger, on_status=None, should_stop=None, skip_downloaded=True, has_more=None):
        for comic in comics:
            on_status(comic["id"], "done")
            queue.stop()                          # 下完第一部就暂停

    monkeypatch.setattr(browser_worker, "download_comic_list", fake_download)

    async def scenario():
        queue.add([{"id": 1, "title": "a"}, {"id": 2, "title": "b"}, {"id": 3, "title": "c"}])
        queue.start()
        await queue._task

    asyncio.run(scenario())
    assert statuses(queue) == {1: "done", 2: "pending", 3: "pending"}
    assert queue.running is False
    assert queue.message == "已暂停，还有 2 部等待下载"


def test_crash_puts_current_item_back_to_pending(tmp_path, monkeypatch):
    queue = make_queue(tmp_path)

    async def crashing(comics, logger, on_status=None, should_stop=None, skip_downloaded=True, has_more=None):
        for _comic in comics:
            raise RuntimeError("Target page, context or browser has been closed")

    monkeypatch.setattr(browser_worker, "download_comic_list", crashing)

    async def scenario():
        queue.add([{"id": 1, "title": "a"}])
        queue.start()
        await queue._task

    asyncio.run(scenario())
    assert statuses(queue) == {1: "pending"}
    assert "browser has been closed" in queue.message
