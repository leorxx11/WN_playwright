import csv

import pytest
from fastapi.testclient import TestClient

import classify_by_author as classifier
from webapp import browser_worker, common, routes_classify
from webapp.app import app


# ---------- 纯函数 ----------

@pytest.mark.parametrize("filename, expected", [
    ("玩轉學姊 127-128話[完結].zip", "玩轉學姊"),
    ("玩轉學姊 第124話.zip", "玩轉學姊"),
    ("(C101) 作品名 3.zip", "作品名"),
])
def test_series_key(filename, expected):
    assert classifier.series_key(filename) == expected


@pytest.mark.parametrize("name, expected", [
    ("たにし", "たにし"),
    ("a/b:c", "a_b_c"),
    ("..", ""),
    (" ../x ", "_x"),
])
def test_safe_folder_name(name, expected):
    assert classifier.safe_folder_name(name) == expected


def make_zips(directory, names):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"zip")


def test_plan_groups_known_new_and_other(tmp_path):
    downloads = tmp_path / "downloads"
    make_zips(downloads, [
        "[たにし] 潤愛.zip",
        "[篆儀通文書坊漢化][たにし] 淫毛.zip",      # 多个括号块时匹配已知作者
        "[新人] 作品A.zip",
        "[新人] 作品B.zip",
        "[单本] 作品C.zip",
        "玩轉學姊 100-101話.zip",
        "玩轉學姊 102話.zip",
    ])
    groups = classifier.plan_classification(downloads, ["たにし"])
    summary = [(g["kind"], g["label"], g["folder"], len(g["files"])) for g in groups]

    assert summary == [
        ("known", "たにし", "たにし", 2),
        ("new", "新人", "新人", 2),
        ("other", "玩轉學姊", "other", 2),   # other 里按文件数排在前
        ("other", "单本", "other", 1),
    ]
    assert groups[3]["author"] == "单本"
    assert groups[2]["author"] is None


def test_move_file_reports_status(tmp_path):
    downloads, class_dir = tmp_path / "downloads", tmp_path / "class"
    make_zips(downloads, ["a.zip", "b.zip"])
    make_zips(class_dir / "x", ["b.zip"])

    assert classifier.move_file(downloads, class_dir, "a.zip", "x") == "moved"
    assert (class_dir / "x" / "a.zip").exists()
    assert classifier.move_file(downloads, class_dir, "b.zip", "x") == "exists"
    assert (downloads / "b.zip").exists()                # 目标已存在时不覆盖
    assert classifier.move_file(downloads, class_dir, "nope.zip", "x") == "missing"
    assert classifier.list_class_folders(class_dir) == [{"name": "x", "count": 2}]


# ---------- 接口 ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    make_zips(tmp_path / "downloads", ["[新人] 作品A.zip", "[新人] 作品B.zip", "玩轉學姊 1話.zip"])
    with open(tmp_path / "name.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([["ID", "Name"], ["1", "たにし"], ["2", "other"]])

    monkeypatch.setattr(common, "BASE_DIR", str(tmp_path))
    fresh = browser_worker.BrowserWorker(queue_path=str(tmp_path / "queue.json"))
    monkeypatch.setattr(routes_classify, "worker", fresh)
    with TestClient(app) as test_client:
        yield test_client


def test_preview(client):
    data = client.get("/api/classify").json()
    assert data["total"] == 3
    assert data["authors_count"] == 1
    assert data["downloading"] is False
    assert [(g["kind"], g["label"]) for g in data["groups"]] == [("new", "新人"), ("other", "玩轉學姊")]


def test_run_moves_files_and_adds_authors(client, tmp_path):
    res = client.post("/api/classify/run", json={
        "moves": [
            {"file": "[新人] 作品A.zip", "folder": "新人"},
            {"file": "[新人] 作品B.zip", "folder": "新人"},
            {"file": "玩轉學姊 1話.zip", "folder": "玩轉學姊"},
        ],
        "add_authors": ["新人", "たにし", "other"],   # 已有的和 other 不重复加
    }).json()

    assert res == {"moved": 3, "skipped": [], "added_authors": ["新人"]}
    assert sorted(p.name for p in (tmp_path / "class" / "新人").iterdir()) == ["[新人] 作品A.zip", "[新人] 作品B.zip"]
    assert (tmp_path / "class" / "玩轉學姊" / "玩轉學姊 1話.zip").exists()
    with open(tmp_path / "name.csv", encoding="utf-8") as f:
        assert [row["Name"] for row in csv.DictReader(f)] == ["たにし", "other", "新人"]

    after = client.get("/api/classify").json()
    assert after["total"] == 0
    assert {f["name"]: f["count"] for f in after["class_folders"]} == {"新人": 2, "玩轉學姊": 1}


def test_run_rejects_paths_outside_downloads(client, tmp_path):
    res = client.post("/api/classify/run", json={"moves": [
        {"file": "../name.csv", "folder": "x"},
        {"file": "玩轉學姊 1話.zip", "folder": ".."},
        {"file": "玩轉學姊 1話.zip", "folder": "../escape"},
    ]}).json()

    assert [s["reason"] for s in res["skipped"]] == ["invalid", "invalid"]
    assert res["moved"] == 1
    assert (tmp_path / "class" / "_escape" / "玩轉學姊 1話.zip").exists()   # 路径分隔符被替换，留在 class/ 里
    assert (tmp_path / "name.csv").exists()


def test_run_refused_while_downloading(client):
    routes_classify.worker.download.running = True
    res = client.post("/api/classify/run", json={"moves": [{"file": "玩轉學姊 1話.zip", "folder": "x"}]})
    assert res.status_code == 409


def test_run_requires_moves(client):
    assert client.post("/api/classify/run", json={"moves": []}).status_code == 400
