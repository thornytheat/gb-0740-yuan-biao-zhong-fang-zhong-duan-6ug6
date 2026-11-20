import hashlib
from datetime import datetime, timezone
from time import perf_counter

from app.config import CAPACITY, VERSION
from app.keys import ReplayError
from app.modules.m1_inventory.reader import read_bundle
from app.modules.m1_inventory.service import changes, heads
from app.modules.m2_graph.registry import catalog
from app.modules.m2_graph.service import topology
from app.modules.m3_fingerprint.service import fingerprint
from app.modules.m4_schedule.expansion import impact
from app.modules.m4_schedule.service import assemble
from app.modules.m5_rollback.service import rehearse
from app.modules.m6_reconcile.service import compare
from app.modules.m8_commitment.service import commit


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(raw, capacity):
    token = VERSION.encode() + b":" + str(capacity).encode() + b":" + raw
    return digest(token)[:26]


def resolve_capacity(value):
    if value is None:
        return CAPACITY
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReplayError("CAPACITY", "夜间容量须为非负整数行数")
    return value


def safe_counts(value):
    if isinstance(value, dict):
        return {key: safe_counts(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_counts(item) for item in value]
    if type(value) is int and abs(value) > 2**53 - 1:
        return str(value)
    return value


def compute(raw, capacity=None):
    capacity = resolve_capacity(capacity)
    began = perf_counter()
    value = read_bundle(raw)
    registered = catalog(value["datasets"])
    order = topology(registered)
    current = heads(value["heads"])
    incoming, isolated, duplicates = changes(value["changes"])
    affected, valid, late = impact(registered, incoming, current, value["through"])
    tasks = assemble(registered, order, current, {key: incoming[key] for key in valid}, affected)
    rejected = sorted(isolated + late, key=lambda r: r["源行"])
    check = compare(tasks, len(value["changes"]), len(valid), len(rejected), len(duplicates))
    commitment = commit(tasks, capacity)
    simulation = rehearse(current, [task for task in tasks if task.get("承诺") == "commit"])
    summary = {
        "编号": identity(raw, capacity),
        "规则": VERSION,
        "文件摘要": digest(raw),
        "参数摘要": fingerprint(value["through"]),
        "承诺摘要": commitment["承诺摘要"],
        "时区": "UTC",
        "生成时间": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "截止分区日": value["through"],
        "容量": capacity,
        "处理毫秒": round((perf_counter() - began) * 1000),
    }
    return {
        "批次": summary,
        "分区勾稽": check,
        "承诺": safe_counts(commitment),
        "排程": safe_counts(tasks),
        "登记": [{"分区": key, **incoming[key]} for key in sorted(valid)],
        "隔离": rejected,
        "重复": duplicates,
        "回滚": simulation,
        "依赖": [
            {
                "数据集": name,
                "版本": registered[name]["revision"],
                "读取": [f"{parent} -{lag}d" for parent, lag in registered[name]["reads"]],
            }
            for name in order
        ],
        "指纹": [
            {"分区": r["分区"], "预期版本": r["计划"]["version"], "来源数": len(r["上游"])}
            for r in tasks
            if r["计划"]
        ],
    }


def execute(store, raw, capacity=None):
    capacity = resolve_capacity(capacity)
    key = identity(raw, capacity)
    previous = store.get(key)
    return (previous, True) if previous else store.save(key, compute(raw, capacity), raw)


def attest(store, key):
    document = store.get(key)
    if not document:
        return None
    raw = store.evidence(key)
    return {"在位": raw is not None, "摘要一致": raw is not None and digest(raw) == document["批次"]["文件摘要"]}
