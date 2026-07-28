"""Docker 进程健康检查。"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import load_config
from utils.runtime_status import RuntimeStatusStore


def check_scheduler() -> int:
    config_path = os.environ.get("INFOCOLLECTOR_CONFIG", str(ROOT / "config.yaml"))
    config = load_config(config_path)
    status_path = config.get("output", {}).get("runtime_status", "data/runtime-status.json")
    heartbeat = RuntimeStatusStore(status_path).read().get("scheduler", {}).get("heartbeat_at")
    if not heartbeat:
        return 1
    parsed = datetime.fromisoformat(heartbeat)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    return 0 if 0 <= age <= 180 else 1


if __name__ == "__main__":
    component = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit(check_scheduler() if component == "scheduler" else 2)
