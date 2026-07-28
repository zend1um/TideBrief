"""跨进程运行状态、任务心跳与可选的 Healthchecks.io 通知。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from filelock import FileLock


log = logging.getLogger("infoCollector")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStatusStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.path) + ".lock", timeout=5)

    def read(self) -> dict:
        if not self.path.exists():
            return {"updated_at": None, "scheduler": {}, "jobs": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"updated_at": None, "scheduler": {}, "jobs": {}}
        return value if isinstance(value, dict) else {"updated_at": None, "scheduler": {}, "jobs": {}}

    def scheduler_heartbeat(self, next_runs: dict[str, str | None] | None = None) -> None:
        now = utc_now()
        update: dict[str, Any] = {
            "heartbeat_at": now,
            "pid": os.getpid(),
        }
        if next_runs is not None:
            update["next_runs"] = next_runs
        with self.lock:
            value = self.read()
            current = value.setdefault("scheduler", {})
            current.setdefault("started_at", now)
            current.update(update)
            self._write(value)

    def job_started(self, job: str) -> None:
        now = utc_now()
        self._mutate_job(job, {"state": "running", "started_at": now, "last_error": ""})

    def job_succeeded(self, job: str, details: dict | None = None) -> None:
        now = utc_now()
        update = {
            "state": "success",
            "finished_at": now,
            "last_success_at": now,
            "last_error": "",
        }
        if details:
            update["details"] = details
        self._mutate_job(job, update)

    def job_failed(self, job: str, exc: Exception | str) -> None:
        self._mutate_job(
            job,
            {
                "state": "failed",
                "finished_at": utc_now(),
                "last_error": str(exc)[:1000],
            },
        )

    def job_skipped(self, job: str, reason: str) -> None:
        self._mutate_job(
            job,
            {
                "state": "skipped",
                "finished_at": utc_now(),
                "last_error": reason[:1000],
            },
        )

    def _mutate_job(self, job: str, update: dict) -> None:
        with self.lock:
            value = self.read()
            jobs = value.setdefault("jobs", {})
            current = jobs.setdefault(job, {})
            current.update(update)
            self._write(value)

    def _mutate(self, key: str, update: dict) -> None:
        with self.lock:
            value = self.read()
            current = value.setdefault(key, {})
            current.update(update)
            self._write(value)

    def _write(self, value: dict) -> None:
        value["updated_at"] = utc_now()
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def heartbeat_ping(state: str, body: str = "") -> None:
    """向 Healthchecks.io 或兼容服务发送 start/success/fail ping。"""
    base = os.environ.get("HEALTHCHECKS_PING_URL", "").strip().rstrip("/")
    if not base:
        return
    url = base
    if state in {"start", "fail"}:
        url = f"{base}/{state}"
    data = body.encode("utf-8") if body else None
    try:
        with request.urlopen(request.Request(url, data=data, method="POST"), timeout=10):
            return
    except (error.URLError, TimeoutError, OSError) as exc:
        log.warning("Healthchecks ping failed: %s", exc)
