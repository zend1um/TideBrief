"""本地 Web UI 与仪表盘快照测试。"""

from datetime import datetime, timezone
import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from models.article import Article
from pipeline.filter import FilterResult
from pipeline.market import MarketMove, MarketSnapshot
from pipeline.review_store import ThesisReviewStore
from ui.server import app
from utils.dashboard import write_dashboard_snapshot


client = TestClient(app)


def test_ui_serves_dashboard_and_page():
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json()["signals"]
    assert response.json()["demo"] is True

    page = client.get("/")
    assert page.status_code == 200
    assert "知潮 TideBrief" in page.text
    assert "今日交易信号" in page.text
    assert "全球财经日历" in page.text
    assert "观点账本" in page.text


def test_economic_calendar_api_and_ics_export():
    response = client.get("/api/calendar")
    assert response.status_code == 200
    payload = response.json()
    assert payload["timezone"] == "Asia/Shanghai"
    assert len(payload["events"]) >= 30
    assert payload["events"] == sorted(payload["events"], key=lambda item: item["starts_at"])
    assert any(event["id"] == "2026-07-30-fomc" for event in payload["events"])

    calendar = client.get("/api/calendar.ics")
    assert calendar.status_code == 200
    assert calendar.headers["content-type"].startswith("text/calendar")
    assert "tidebrief-economic-calendar.ics" in calendar.headers["content-disposition"]
    assert "BEGIN:VCALENDAR" in calendar.text
    assert "知潮 TideBrief 全球财经日历" in calendar.text
    assert "美联储FOMC利率决议" in calendar.text


def test_runtime_status_endpoint():
    health = client.get("/api/health")
    assert health.json() == {"status": "ok", "service": "tidebrief-web"}

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}
    assert "scheduler_live" in response.json()
    assert "dashboard" in response.json()


def test_optional_basic_auth_keeps_healthcheck_public(monkeypatch):
    monkeypatch.setenv("TIDEBRIEF_USERNAME", "trader")
    monkeypatch.setenv("TIDEBRIEF_PASSWORD", "secret")

    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("trader", "secret")).status_code == 200


def test_settings_update_preserves_read_only_config(tmp_path, monkeypatch):
    original = Path("config.yaml").read_text(encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr("ui.server._config_path", lambda: config_path)

    response = client.put("/api/settings", json={
        "focus_keywords": [" 铜 ", "NVDA", "铜"],
        "max_daily_items": 7,
        "max_context_items": 1,
    })

    assert response.status_code == 200
    content = config_path.read_text(encoding="utf-8")
    assert content == original
    assert "硬阅读预算" in content
    settings = json.loads((tmp_path / "data" / "runtime-settings.json").read_text(encoding="utf-8"))
    assert settings["focus_keywords"] == ["铜", "NVDA"]
    assert settings["max_daily_items"] == 7


def test_writes_real_dashboard_snapshot(tmp_path):
    article = Article(
        id="signal", source="test", category="B", url="https://example.com",
        title="测试交易信号", raw_content="",
    )
    article.ranking_score = 8.2
    article.summary = "新增事实"
    article.counter_argument = "最强反方观点"
    article.review_symbol = "GC=F"
    article.expected_direction = "up"
    result = FilterResult(highlight=[article])
    market = MarketSnapshot(moves=[MarketMove("黄金", "GC=F", 2400, 1.2, 2.3)])
    output = tmp_path / "dashboard.json"

    write_dashboard_snapshot(
        output, datetime(2026, 7, 20, 8, 0), result,
        {"market_regime": "测试主线"}, market,
        {"total_collected": 10, "analyzed": 2, "displayed": 1},
    )

    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "测试交易信号" in text
    assert "测试主线" in text
    assert "最强反方观点" in text
    assert '"review_symbol": "GC=F"' in text


def test_review_api_persists_manual_outcome(tmp_path, monkeypatch):
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    database = tmp_path / "reviews.db"
    config["output"]["review_database"] = str(database)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr("ui.server._config_path", lambda: config_path)

    article = Article(
        id="api-review", source="test", category="B", url="",
        title="API 复盘测试", raw_content="",
    )
    article.review_metric = "黄金"
    article.review_symbol = "GC=F"
    article.expected_direction = "up"
    article.review_horizon_days = 3
    at = datetime(2026, 7, 21, 8, tzinfo=timezone.utc)
    ThesisReviewStore(database).capture_and_evaluate(
        [article], MarketSnapshot(as_of=at, moves=[MarketMove("黄金", "GC=F", 100)]), at,
    )
    review_id = ThesisReviewStore(database).list_records()[0]["id"]

    response = client.patch(
        f"/api/reviews/{review_id}",
        json={"outcome": "contradicted", "note": "人工复核"},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "contradicted"
    assert response.json()["outcome_source"] == "manual"
