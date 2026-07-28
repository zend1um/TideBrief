"""交易信号筛选链路的纯本地测试。"""

from datetime import datetime, timezone

from models.article import Article, RawArticle
from pipeline.analyzer import Analyzer
from pipeline.filter import ArticleFilter
from pipeline.market import MarketMove, MarketSnapshot, MarketDataProvider
from pipeline.prefilter import SignalPrefilter
from utils.obsidian import ObsidianWriter


def raw(title: str, source: str = "cnbc", category: str = "B", url: str = "") -> RawArticle:
    return RawArticle(
        source=source,
        category=category,
        url=url or f"https://example.com/{abs(hash(title))}",
        title=title,
        raw_content=title,
        pub_date=datetime.now(timezone.utc),
    )


def analyzed(title: str, event: str, ranking: float, actionability: int = 7, category: str = "B") -> Article:
    article = Article(
        id=str(abs(hash(title))), source="cnbc", category=category,
        url="https://example.com", title=title, raw_content="",
    )
    article.event_key = event
    article.ranking_score = ranking
    article.trading_relevance = 8
    article.market_impact_score = 7
    article.actionability_score = actionability
    article.novelty_score = 7
    article.confidence_score = 7
    article.political_economy_lesson = "政策约束会通过风险溢价影响资产。"
    article.summary = "新增事实"
    article.asset_impact = "美债收益率上行，美元偏强"
    article.time_horizon = "1-5天"
    article.priced_in = "市场只计入一次降息"
    article.invalidation = "通胀快速回落"
    article.watch_signals = ["美国10年期收益率", "美元指数"]
    return article


class TestSignalPrefilter:
    def test_rejects_noise_and_merges_near_duplicate_titles(self):
        prefilter = SignalPrefilter(min_score=3.5, max_candidates=10, max_per_source=10)
        result = prefilter.apply([
            raw("Fed signals rate cut as inflation cools", url="https://a/1"),
            raw("Federal Reserve signals rate cuts as inflation cools", source="bloomberg", url="https://a/2"),
            raw("Show HN: a new open source programming language", source="hackernews", category="C"),
        ])

        assert len(result.selected) == 1
        assert len(result.duplicates) == 1
        assert len(result.rejected) == 1

    def test_focus_keyword_overrides_generic_source_score(self):
        article = raw("宁德时代发布新产品", source="peopledaily", category="A")
        prefilter = SignalPrefilter(focus_keywords=["宁德时代"])
        assert prefilter.score(article) >= prefilter.min_score


class TestTradingFilter:
    def test_enforces_reading_budget_and_event_deduplication(self):
        filter_ = ArticleFilter(max_daily_items=3, max_context_items=1)
        articles = [
            analyzed("Fed decision A", "美联储7月利率决议", 8.5),
            analyzed("Fed decision B", "美联储七月利率决议", 8.1),
            analyzed("Oil supply shock", "霍尔木兹原油供应中断", 7.8),
            analyzed("Fiscal constraint", "美国财政赤字约束", 6.7, actionability=2, category="A"),
        ]

        result = filter_.apply(articles)

        assert len(result.highlight) == 2
        assert len(result.keep) == 1
        assert len(result.highlight) + len(result.keep) <= 3
        assert sum("Fed decision" in a.title for a in result.highlight) == 1


class TestStructuredAnalysis:
    def test_computes_composite_ranking(self):
        article = Article(id="1", source="x", category="B", url="", title="x", raw_content="")
        Analyzer._apply_result(article, {
            "summary": "事实",
            "event_key": "事件",
            "trading_relevance": 8,
            "market_impact_score": 7,
            "actionability_score": 6,
            "novelty_score": 5,
            "confidence_score": 9,
            "counter_argument": "增长改善可能抵消估值压力",
            "review_metric": "美国10年期收益率",
            "review_symbol": "^TNX",
            "expected_direction": "上涨",
            "review_horizon_days": 5,
            "watch_signals": ["a", "b", "c", "d"],
        })

        assert article.ranking_score == 6.95
        assert article.quality_score == 7
        assert article.watch_signals == ["a", "b", "c"]
        assert article.counter_argument == "增长改善可能抵消估值压力"
        assert article.expected_direction == "up"
        assert article.review_horizon_days == 5

    def test_repairs_common_llm_json_error(self):
        result = Analyzer._parse_json('{"summary":"ok", "tags":["macro",],}')
        assert result["summary"] == "ok"


class TestMarketSnapshot:
    def test_formats_cross_asset_table(self):
        snapshot = MarketSnapshot(moves=[MarketMove("黄金", "GC=F", 2400.0, 1.25, -0.5)])
        text = snapshot.to_markdown()
        assert "黄金" in text
        assert "+1.25%" in text
        assert MarketDataProvider._change([100, 101, 102], 1) == (102 / 101 - 1) * 100


class TestTradingBriefWriter:
    def test_brief_omits_discarded_article_titles(self, tmp_path):
        writer = ObsidianWriter(str(tmp_path))
        signal = analyzed("必须阅读", "央行决议", 8.0)
        signal.id = "signal"
        discarded = analyzed("不应出现在日报", "噪声", 3.0)
        path = writer.write_brief(
            datetime(2026, 7, 19), [signal], [], [discarded],
            "通胀交易主导", "1. 明日观察收益率",
            synthesis={"market_regime": "通胀交易主导", "calibration_questions": ["收益率是否继续上行？"]},
            stats={"total_collected": 316, "analyzed": 24, "prefilter_rejected": 280, "duplicates": 12},
        )
        content = path.read_text(encoding="utf-8")
        assert "必须阅读" in content
        assert "不应出现在日报" not in content
        assert "采集 316 条" in content
        assert "收益率是否继续上行" in content
