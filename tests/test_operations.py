"""小服务器运行状态、配置覆盖与官方日历同步测试。"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import httpx
import yaml

from pipeline.calendar_sync import _schedule_rows, sync_economic_calendar
from utils.config import load_config, write_runtime_settings
from utils.runtime_status import RuntimeStatusStore


def test_config_merges_runtime_settings_and_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "vault": {"path": "local"},
                "filter": {
                    "max_daily_items": 8,
                    "max_context_items": 2,
                    "prefilter": {"focus_keywords": []},
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    settings_path = tmp_path / "runtime-settings.json"
    write_runtime_settings(
        settings_path,
        {
            "focus_keywords": ["铜", "NVDA"],
            "max_daily_items": 6,
            "max_context_items": 1,
        },
    )
    monkeypatch.setenv("INFOCOLLECTOR_VAULT_PATH", "/vault")

    config = load_config(config_path, runtime_settings_path=settings_path)

    assert config["vault"]["path"] == "/vault"
    assert config["filter"]["max_daily_items"] == 6
    assert config["filter"]["prefilter"]["focus_keywords"] == ["铜", "NVDA"]


def test_runtime_status_tracks_success_and_scheduler_heartbeat(tmp_path):
    store = RuntimeStatusStore(tmp_path / "runtime-status.json")

    store.scheduler_heartbeat({"daily_collect": "2026-07-28T04:00:00+08:00"})
    store.job_started("daily_collect")
    store.job_succeeded("daily_collect", {"signals": 3})

    status = store.read()
    assert status["scheduler"]["heartbeat_at"]
    assert status["jobs"]["daily_collect"]["state"] == "success"
    assert status["jobs"]["daily_collect"]["details"]["signals"] == 3


def test_bls_calendar_sync_replaces_future_official_events(tmp_path, monkeypatch):
    calendar_path = tmp_path / "economic-calendar.json"
    calendar_path.write_text(
        json.dumps(
            {
                "as_of": "2026-07-01T00:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "sources": [
                    {
                        "id": "bls",
                        "name": "U.S. Bureau of Labor Statistics",
                        "url": "https://www.bls.gov/schedule/2026/home.htm",
                    }
                ],
                "events": [
                    {
                        "id": "2026-08-08-us-nfp",
                        "starts_at": "2026-08-08T20:30:00+08:00",
                        "region": "美国",
                        "country": "美国",
                        "title": "旧日期",
                        "category": "就业",
                        "importance": 3,
                        "why": "",
                        "watch": "",
                        "assets": [],
                        "source_id": "bls",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:nfp
SUMMARY:Employment Situation
DTSTART;TZID=America/New_York:20260807T083000
END:VEVENT
BEGIN:VEVENT
UID:cpi
SUMMARY:Consumer Price Index
DTSTART;TZID=America/New_York:20260812T083000
END:VEVENT
BEGIN:VEVENT
UID:ppi
SUMMARY:Producer Price Index
DTSTART;TZID=America/New_York:20260813T083000
END:VEVENT
END:VCALENDAR
"""

    class FakeResponse:
        content = fixture

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(httpx.Client, "get", lambda *_args, **_kwargs: FakeResponse())
    config = {
        "calendar": {
            "path": str(calendar_path),
            "bls_ics_url": "https://example.test/bls.ics",
            "horizon_days": 370,
        }
    }

    result = sync_economic_calendar(
        config,
        now=datetime.fromisoformat("2026-07-27T10:00:00+08:00"),
    )

    payload = json.loads(calendar_path.read_text(encoding="utf-8"))
    assert result.matched == 3
    assert result.replaced == 1
    assert [event["id"] for event in payload["events"]] == [
        "2026-08-07-us-nfp",
        "2026-08-12-us-cpi",
        "2026-08-13-us-ppi",
    ]
    assert payload["events"][0]["starts_at"] == "2026-08-07T20:30:00+08:00"


def test_bls_html_schedule_fallback_parser():
    rows = _schedule_rows(
        """
        <table>
          <tr><th>Date</th><th>Time</th><th>Release</th></tr>
          <tr>
            <td>Friday, August 7, 2026</td>
            <td>08:30 AM</td>
            <td>Employment Situation for July 2026</td>
          </tr>
        </table>
        """
    )

    assert len(rows) == 1
    assert rows[0][0].isoformat() == "2026-08-07T08:30:00-04:00"
    assert rows[0][1] == "Employment Situation for July 2026"
