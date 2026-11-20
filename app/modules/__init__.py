from importlib import import_module

VIEWS = {
    "inventory": ("分区登记", ["登记", "隔离", "重复"]),
    "graph": ("依赖求解", ["依赖"]),
    "fingerprint": ("清单指纹", ["指纹"]),
    "schedule": ("重放排程", ["排程"]),
    "commitment": ("回填承诺", ["承诺"]),
    "rollback": ("回滚校验", ["回滚"]),
    "reconcile": ("行数勾稽", ["分区勾稽"]),
    "release": ("版本签发", ["批次", "证据"]),
}

MODULES = [
    "m1_inventory",
    "m2_graph",
    "m3_fingerprint",
    "m4_schedule",
    "m5_rollback",
    "m6_reconcile",
    "m7_release",
    "m8_commitment",
]


def register(app):
    for name in MODULES:
        app.register_blueprint(import_module(f"app.modules.{name}.handler").api)
