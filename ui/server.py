"""本地 Web UI 服务：读取仪表盘快照并管理少量筛选设置。"""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Literal

import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from filelock import FileLock
from pydantic import BaseModel, Field, field_validator

from pipeline.review_store import ThesisReviewStore
from utils.config import (
    load_config as load_project_config,
    settings_path as project_settings_path,
    write_runtime_settings,
)
from utils.runtime_status import RuntimeStatusStore


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEMO_PATH = Path(__file__).resolve().parent / "demo-dashboard.json"


def _config_path() -> Path:
    value = os.environ.get("INFOCOLLECTOR_CONFIG", "")
    return Path(value).resolve() if value else ROOT_DIR / "config.yaml"


def _settings_path() -> Path:
    return project_settings_path(_config_path())


def _snapshot_path(config: dict) -> Path:
    configured = config.get("output", {}).get("dashboard_snapshot", "data/dashboard.json")
    path = Path(configured)
    return path if path.is_absolute() else ROOT_DIR / path


def _calendar_path(config: dict) -> Path:
    configured = config.get("calendar", {}).get("path", "ui/economic-calendar.json")
    path = Path(configured)
    return path if path.is_absolute() else ROOT_DIR / path


def _runtime_status_path(config: dict) -> Path:
    configured = config.get("output", {}).get("runtime_status", "data/runtime-status.json")
    path = Path(configured)
    return path if path.is_absolute() else ROOT_DIR / path


def _review_path(config: dict) -> Path:
    configured = config.get("output", {}).get("review_database", "data/thesis_reviews.db")
    path = Path(configured)
    return path if path.is_absolute() else ROOT_DIR / path


def _review_store(config: dict) -> ThesisReviewStore:
    threshold = config.get("output", {}).get("review_move_threshold_pct", 0.3)
    return ThesisReviewStore(_review_path(config), move_threshold_pct=threshold)


def _load_config() -> dict:
    try:
        return load_project_config(_config_path(), runtime_settings_path=_settings_path())
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=500, detail=f"无法读取配置：{exc}") from exc


def _load_calendar() -> dict:
    path = _calendar_path(_load_config())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"无法读取财经日历：{exc}") from exc
    payload["events"] = sorted(payload.get("events", []), key=lambda item: item.get("starts_at", ""))
    return payload


def _ics_escape(value: object) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _calendar_ics(payload: dict) -> str:
    sources = {item["id"]: item for item in payload.get("sources", [])}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TideBrief//Global Economic Calendar//ZH-CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:知潮 TideBrief 全球财经日历",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    for event in payload.get("events", []):
        start = datetime.fromisoformat(event["starts_at"])
        source = sources.get(event.get("source_id"), {})
        description = "\n".join(
            filter(
                None,
                [
                    f"为什么重要：{event.get('why', '')}",
                    f"观察重点：{event.get('watch', '')}",
                    f"影响资产：{'、'.join(event.get('assets', []))}",
                    f"官方来源：{source.get('name', '')}",
                ],
            )
        )
        lines.extend(["BEGIN:VEVENT", f"UID:{_ics_escape(event['id'])}@tidebrief.local", f"DTSTAMP:{stamp}"])
        if event.get("time_tbd"):
            lines.extend(
                [
                    f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{(start + timedelta(days=1)).strftime('%Y%m%d')}",
                ]
            )
        else:
            utc_start = start.astimezone(timezone.utc)
            lines.extend(
                [
                    f"DTSTART:{utc_start.strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTEND:{(utc_start + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}",
                ]
            )
        lines.extend(
            [
                f"SUMMARY:{_ics_escape(event['title'])}",
                f"DESCRIPTION:{_ics_escape(description)}",
                f"CATEGORIES:{_ics_escape(event.get('category', '财经'))}",
                f"URL:{source.get('url', '')}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _settings_from_config(config: dict) -> dict:
    filter_config = config.get("filter", {})
    return {
        "focus_keywords": filter_config.get("prefilter", {}).get("focus_keywords", []),
        "max_daily_items": filter_config.get("max_daily_items", 8),
        "max_context_items": filter_config.get("max_context_items", 2),
        "max_candidates": filter_config.get("prefilter", {}).get("max_candidates", 24),
    }


class SettingsPayload(BaseModel):
    focus_keywords: list[str] = Field(default_factory=list, max_length=40)
    max_daily_items: int = Field(ge=3, le=12)
    max_context_items: int = Field(ge=0, le=4)

    @field_validator("focus_keywords")
    @classmethod
    def normalise_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = re.sub(r"\s+", " ", value).strip()[:40]
            key = cleaned.casefold()
            if cleaned and key not in seen:
                result.append(cleaned)
                seen.add(key)
        return result


class ReviewPayload(BaseModel):
    outcome: Literal["pending", "supported", "contradicted", "inconclusive"]
    note: str = Field(default="", max_length=500)


app = FastAPI(title="知潮 TideBrief", docs_url=None, redoc_url=None)


@app.middleware("http")
async def optional_basic_auth(request: Request, call_next):
    username = os.environ.get("TIDEBRIEF_USERNAME") or os.environ.get("EDGE_BRIEF_USERNAME", "")
    password = os.environ.get("TIDEBRIEF_PASSWORD") or os.environ.get("EDGE_BRIEF_PASSWORD", "")
    if not username or not password or request.url.path == "/api/health":
        return await call_next(request)
    supplied = request.headers.get("Authorization", "")
    try:
        scheme, encoded = supplied.split(" ", 1)
        decoded = base64.b64decode(encoded).decode("utf-8")
        candidate_user, candidate_password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        candidate_user = candidate_password = ""
        scheme = ""
    valid = (
        scheme.casefold() == "basic"
        and secrets.compare_digest(candidate_user, username)
        and secrets.compare_digest(candidate_password, password)
    )
    if not valid:
        return Response(
            content="Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="TideBrief", charset="UTF-8"'},
        )
    return await call_next(request)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "tidebrief-web"}


@app.get("/api/status")
async def runtime_status() -> dict:
    config = _load_config()
    runtime = RuntimeStatusStore(_runtime_status_path(config)).read()
    dashboard_info = _file_freshness(
        _snapshot_path(config),
        max_age_hours=max(1, int(config.get("schedule", {}).get("stale_after_hours", 26))),
    )
    calendar_info = _file_freshness(_calendar_path(config), max_age_hours=24 * 8)
    scheduler_heartbeat = runtime.get("scheduler", {}).get("heartbeat_at")
    scheduler_age = _hours_since(scheduler_heartbeat)
    scheduler_live = scheduler_age is not None and scheduler_age <= 3 / 60
    degraded = dashboard_info["stale"] or not scheduler_live
    return {
        "status": "degraded" if degraded else "ok",
        "dashboard": dashboard_info,
        "calendar": calendar_info,
        "scheduler_live": scheduler_live,
        "runtime": runtime,
    }


@app.get("/api/dashboard")
async def dashboard() -> dict:
    config = _load_config()
    path = _snapshot_path(config)
    source = path if path.exists() else DEMO_PATH
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"无法读取仪表盘数据：{exc}") from exc
    payload["demo"] = source == DEMO_PATH
    payload["settings"] = _settings_from_config(config)
    if source != DEMO_PATH:
        store = _review_store(config)
        payload["reviews"] = store.list_records(limit=12)
        payload["review_summary"] = store.summary()
    else:
        payload.setdefault("reviews", [])
        payload.setdefault("review_summary", {"total": 0, "pending": 0, "supported": 0, "contradicted": 0})
    return payload


@app.get("/api/calendar")
async def economic_calendar() -> dict:
    """返回已核对的官方高影响财经事件，时间统一为北京时间。"""
    return _load_calendar()


@app.get("/api/calendar.ics")
async def economic_calendar_ics() -> Response:
    """导出可被系统日历、Outlook 和 Google Calendar 导入的 iCalendar 文件。"""
    return Response(
        content=_calendar_ics(_load_calendar()),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tidebrief-economic-calendar.ics"'},
    )


@app.get("/api/reviews")
async def get_reviews(limit: int = 12) -> dict:
    store = _review_store(_load_config())
    return {"items": store.list_records(limit=limit), "summary": store.summary()}


@app.patch("/api/reviews/{review_id}")
async def update_review(review_id: str, payload: ReviewPayload) -> dict:
    store = _review_store(_load_config())
    try:
        record = store.update_manual(review_id, payload.outcome, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="复盘记录不存在")
    return record


@app.get("/api/settings")
async def get_settings() -> dict:
    return _settings_from_config(_load_config())


@app.put("/api/settings")
async def update_settings(payload: SettingsPayload) -> dict:
    if payload.max_context_items >= payload.max_daily_items:
        raise HTTPException(status_code=422, detail="背景阅读数量必须小于每日总量")

    path = _settings_path()
    lock = FileLock(str(path) + ".lock", timeout=3)
    try:
        with lock:
            write_runtime_settings(path, payload.model_dump())
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"无法保存配置：{exc}") from exc

    return {"saved": True, **payload.model_dump()}


def _file_freshness(path: Path, max_age_hours: int) -> dict:
    if not path.exists():
        return {"exists": False, "as_of": None, "age_hours": None, "stale": True}
    as_of = None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        as_of = payload.get("as_of")
    except (OSError, json.JSONDecodeError):
        pass
    if not as_of:
        as_of = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    age = _hours_since(as_of)
    return {
        "exists": True,
        "as_of": as_of,
        "age_hours": round(age, 2) if age is not None else None,
        "stale": age is None or age > max_age_hours,
    }


def _hours_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600)


# API 路由必须先注册，根路径最后交给静态站点。
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
