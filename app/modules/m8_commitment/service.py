from app.modules.m3_fingerprint.service import fingerprint


def commit(tasks, capacity):
    """按排程顺序（拓扑序再分区日）一趟决定今晚承诺。

    待写分区只有在其受影响上游全部承诺在今晚、且剩余容量足够时才写入承诺；
    容量不够的记 CAPACITY，上游被推迟的记 WAITING_UPSTREAM（依赖未齐优先于
    容量，因为先解决依赖才谈得上容量），阻断分区保留原原因码一并列入推迟范围。
    """
    remaining = capacity
    committed, deferred = {}, {}
    for task in tasks:
        if task["状态"] != "write":
            task["承诺"] = task["状态"]
            continue
        waiting = sorted(part for part in task["上游"] if part in deferred)
        if waiting:
            task["承诺"] = "defer"
            task["原因码"] = "WAITING_UPSTREAM"
            task["等待"] = waiting
            deferred[task["分区"]] = task
            continue
        cost = task["计划"]["rows"]
        if cost > remaining:
            task["承诺"] = "defer"
            task["原因码"] = "CAPACITY"
            deferred[task["分区"]] = task
            continue
        remaining -= cost
        task["承诺"] = "commit"
        committed[task["分区"]] = cost
    writes = [
        {"分区": task["分区"], "行数": committed[task["分区"]]}
        for task in tasks
        if task.get("承诺") == "commit"
    ]
    postponements = [
        {
            "分区": task["分区"],
            "原因码": task["原因码"],
            **({"等待": task["等待"]} if "等待" in task else {}),
        }
        for task in tasks
        if task["状态"] == "blocked" or task.get("承诺") == "defer"
    ]
    sealed = {"容量": capacity, "写入": writes, "推迟": postponements}
    return {
        "容量": capacity,
        "已用": capacity - remaining,
        "剩余": remaining,
        "承诺摘要": fingerprint(sealed),
        "写入": writes,
        "推迟": postponements,
    }
