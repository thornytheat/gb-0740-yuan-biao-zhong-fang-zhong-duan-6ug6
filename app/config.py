import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "replay-1.1"
MAX_BYTES = 300 * 1024
SAMPLES = {"nightly": "华东夜班回填", "clean": "两分区演练"}
CAPACITY = int(os.environ.get("REPLAY_CAPACITY", "1500"))
