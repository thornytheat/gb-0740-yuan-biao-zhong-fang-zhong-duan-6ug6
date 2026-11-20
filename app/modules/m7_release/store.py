import json
import sqlite3
from contextlib import closing
from pathlib import Path


class Catalog:
    """承诺与原批证据的只增存储：只插不改不删，删除即无法回查。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connection()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, raw BLOB NOT NULL)")

    def connection(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key):
        with closing(self.connection()) as db:
            row = db.execute("SELECT document FROM plans WHERE id=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def save(self, key, result, raw):
        with closing(self.connection()) as db, db:
            op = db.execute(
                "INSERT OR IGNORE INTO plans VALUES (?,?)", (key, json.dumps(result, ensure_ascii=False))
            )
            db.execute("INSERT OR IGNORE INTO evidence VALUES (?,?)", (key, raw))
            record = db.execute("SELECT document FROM plans WHERE id=?", (key,)).fetchone()[0]
            return json.loads(record), not op.rowcount

    def evidence(self, key):
        with closing(self.connection()) as db:
            row = db.execute("SELECT raw FROM evidence WHERE id=?", (key,)).fetchone()
            return bytes(row[0]) if row else None

    def latest(self):
        with closing(self.connection()) as db:
            return [
                json.loads(row[0])["批次"]
                for row in db.execute("SELECT document FROM plans ORDER BY rowid DESC LIMIT 30")
            ]
