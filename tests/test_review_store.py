"""观点账本的本地持久化与自动复盘测试。"""

from datetime import datetime, timezone

from models.article import Article
from pipeline.market import MarketMove, MarketSnapshot
from pipeline.review_store import ThesisReviewStore


def signal() -> Article:
    article = Article(
        id="gold-thesis",
        source="test",
        category="B",
        url="https://example.com/gold",
        title="黄金验证实际利率拐点",
        raw_content="",
    )
    article.event_key = "实际利率回落"
    article.trading_logic = "实际利率回落 → 黄金上行"
    article.counter_argument = "美元走强可能抵消实际利率影响"
    article.invalidation = "黄金跌破事件前低点"
    article.affected_assets = ["黄金"]
    article.watch_signals = ["实际利率", "美元指数"]
    article.review_metric = "黄金"
    article.review_symbol = "GC=F"
    article.expected_direction = "up"
    article.review_horizon_days = 3
    return article


def snapshot(value: float, at: datetime) -> MarketSnapshot:
    return MarketSnapshot(as_of=at, moves=[MarketMove("黄金", "GC=F", value)])


def test_captures_baseline_and_evaluates_due_thesis(tmp_path):
    store = ThesisReviewStore(tmp_path / "reviews.db")
    start = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    store.capture_and_evaluate([signal()], snapshot(100, start), start)

    pending = store.list_records()[0]
    assert pending["baseline_value"] == 100
    assert pending["automatic_outcome"] == "pending"
    assert pending["counter_argument"]

    due = datetime(2026, 7, 24, 8, tzinfo=timezone.utc)
    store.evaluate(snapshot(105, due), due)
    reviewed = store.list_records()[0]

    assert reviewed["automatic_outcome"] == "supported"
    assert reviewed["price_change_pct"] == 5.0
    assert store.summary()["supported"] == 1


def test_manual_review_overrides_automatic_result(tmp_path):
    store = ThesisReviewStore(tmp_path / "reviews.db")
    start = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    store.capture_and_evaluate([signal()], snapshot(100, start), start)
    review_id = store.list_records()[0]["id"]

    updated = store.update_manual(review_id, "contradicted", "宏观数据没有同步验证")

    assert updated is not None
    assert updated["outcome"] == "contradicted"
    assert updated["outcome_source"] == "manual"
    assert store.summary()["contradicted"] == 1
