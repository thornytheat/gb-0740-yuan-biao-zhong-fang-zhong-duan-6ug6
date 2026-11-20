import json

from app.config import CAPACITY
from app.modules.m1_inventory.reader import read_bundle
from app.modules.m7_release.service import compute, execute
from app.modules.m7_release.store import Catalog


def committed(result):
    return {item["分区"] for item in result["承诺"]["写入"]}


def tasks_by_key(result):
    return {task["分区"]: task for task in result["排程"]}


def test_default_capacity_covers_only_part(nightly):
    promise = nightly["承诺"]
    assert promise["容量"] == CAPACITY
    assert promise["已用"] + promise["剩余"] == promise["容量"]
    assert 0 < len(promise["写入"]) < nightly["分区勾稽"]["待写"]


def test_commit_set_is_dependency_closed(nightly):
    writes = {task["分区"] for task in nightly["排程"] if task["状态"] == "write"}
    for task in nightly["排程"]:
        if task.get("承诺") != "commit":
            continue
        for upstream in task["上游"]:
            if upstream in writes:
                assert upstream in committed(nightly)


# TRAP-27：只挑行数小的先做会把依赖未齐的下游提前发布
def test_downstream_waits_with_deferred_upstream(night):
    result = compute(night, 1500)
    tasks = tasks_by_key(result)
    assert tasks["facts@2026-11-19"]["原因码"] == "CAPACITY"
    assert tasks["day1@2026-11-20"]["原因码"] == "WAITING_UPSTREAM"
    assert tasks["day1@2026-11-20"]["等待"] == ["facts@2026-11-19"]
    assert tasks["ops@2026-11-20"]["等待"] == ["day1@2026-11-20"]
    assert not committed(result) & {"facts@2026-11-19", "day1@2026-11-20", "ops@2026-11-20"}


def test_ready_partitions_not_idled_by_deferral(night):
    result = compute(night, 1500)
    assert "day0@2026-11-16" not in committed(result)
    assert {"day0@2026-11-17", "day1@2026-11-18"} <= committed(result)


def test_zero_capacity_defers_every_write(small):
    result = compute(small, 0)
    assert result["承诺"]["写入"] == [] and result["承诺"]["剩余"] == 0
    first, second = result["排程"]
    assert (first["承诺"], first["原因码"]) == ("defer", "CAPACITY")
    assert (second["承诺"], second["原因码"]) == ("defer", "WAITING_UPSTREAM")
    assert second["等待"] == ["orders@2026-11-17"]
    assert result["回滚"]["演练写入"] == 0 and result["回滚"]["恢复一致"]


def test_full_capacity_commits_everything_ready(night):
    result = compute(night, 100000)
    assert len(result["承诺"]["写入"]) == result["分区勾稽"]["待写"]
    assert {item["原因码"] for item in result["承诺"]["推迟"]} <= {"STALE_HEAD", "MISSING_INPUT"}
    assert result["回滚"]["演练写入"] == result["分区勾稽"]["待写"]


def test_deferral_scope_completes_affected_count(night):
    result = compute(night, 1500)
    blocked = {item["分区"]: item for item in result["承诺"]["推迟"]}
    assert blocked["orders@2026-11-18"]["原因码"] == "STALE_HEAD"
    total = len(result["承诺"]["写入"]) + len(result["承诺"]["推迟"])
    assert total + result["分区勾稽"]["复用"] == result["分区勾稽"]["受影响"]


def test_rollback_rehearses_exactly_the_commitment(night):
    result = compute(night, 1500)
    assert result["回滚"]["演练写入"] == len(result["承诺"]["写入"])
    assert result["回滚"]["恢复一致"] and result["回滚"]["影响外变动"] == []


def test_same_commitment_read_by_schedule_and_release(night):
    result = compute(night, 1500)
    for task in result["排程"]:
        if task["状态"] == "write":
            assert (task["承诺"] == "commit") == (task["分区"] in committed(result))
    assert result["批次"]["承诺摘要"] == result["承诺"]["承诺摘要"]
    assert result["批次"]["容量"] == result["承诺"]["容量"] == 1500


# TRAP-28：同日迟到修订不能改写已签发内容，重试也不会新增第二份
def test_retry_reuses_and_late_revision_appends(tmp_path, small):
    store = Catalog(tmp_path / "archive.sqlite")
    first, reused = execute(store, small, 1500)
    again, again_reused = execute(store, small, 1500)
    assert (reused, again_reused) == (False, True)
    assert first["批次"]["编号"] == again["批次"]["编号"]
    revised = read_bundle(small)
    revised["changes"][0]["rows"] = 13
    second, second_reused = execute(store, json.dumps(revised).encode(), 1500)
    assert not second_reused and second["批次"]["编号"] != first["批次"]["编号"]
    kept = store.get(first["批次"]["编号"])
    assert kept["批次"] == first["批次"] and kept["承诺"] == first["承诺"]
    assert len(store.latest()) == 2


def test_capacity_adjustment_issues_new_commitment(tmp_path, night):
    store = Catalog(tmp_path / "archive.sqlite")
    tight, _ = execute(store, night, 1500)
    ample, reused = execute(store, night, 100000)
    assert not reused and tight["批次"]["编号"] != ample["批次"]["编号"]
    assert len(store.get(tight["批次"]["编号"])["承诺"]["写入"]) < len(ample["承诺"]["写入"])


# TRAP-29：原批证据随批次留存，误删即无法回查
def test_evidence_kept_with_batch(tmp_path, small):
    store = Catalog(tmp_path / "archive.sqlite")
    result, _ = execute(store, small, 1500)
    assert store.evidence(result["批次"]["编号"]) == small


def test_commitment_api_and_page(client):
    run = client.post("/api/plans", json={"sample": "nightly", "capacity": 1500}).json
    assert run["commitment"]["已用"] + run["commitment"]["剩余"] == 1500
    api = client.get(f"/api/commitment/{run['id']}")
    assert api.status_code == 200 and set(api.json) == {"承诺"}
    assert api.json["承诺"]["承诺摘要"] == run["commitment"]["承诺摘要"]
    assert client.get(f"/console/commitment?plan={run['id']}").status_code == 200


def test_release_attests_same_commitment_and_evidence(client):
    run = client.post("/api/plans", json={"sample": "nightly"}).json
    api = client.get(f"/api/release/{run['id']}").json
    assert set(api) == {"批次", "证据"}
    assert api["批次"]["承诺摘要"] == run["commitment"]["承诺摘要"]
    assert api["证据"] == {"在位": True, "摘要一致": True}


def test_capacity_validation(client):
    for offered in ("abc", -5, 1.5, True):
        response = client.post("/api/plans", json={"sample": "clean", "capacity": offered})
        assert response.status_code == 422 and response.json["code"] == "CAPACITY"
    assert client.get("/api/plans").json == []


def test_blank_capacity_falls_back_to_default(client):
    response = client.post("/api/plans", data={"sample": "clean", "capacity": ""})
    assert response.status_code == 201
    assert response.json["commitment"]["容量"] == CAPACITY
