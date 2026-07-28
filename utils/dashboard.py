"""将一次管道结果导出为本地 Web UI 可直接读取的 JSON 快照。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

from models.article import Article

if TYPE_CHECKING:
    from pipeline.filter import FilterResult
    from pipeline.market import MarketSnapshot


def write_dashboard_snapshot(
    path: str | Path,
    date: datetime,
    result: FilterResult,
    synthesis: dict,
    market_snapshot: MarketSnapshot | None,
    stats: dict,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": date.astimezone().isoformat(),
        "demo": False,
        "stats": stats,
        "synthesis": synthesis,
        "market": [asdict(move) for move in market_snapshot.moves] if market_snapshot else [],
        "market_error": market_snapshot.error if market_snapshot else "未启用行情快照",
        "signals": [_article_payload(article) for article in result.highlight],
        "context": [_article_payload(article) for article in result.keep],
    }
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output_path)
    return output_path


def _article_payload(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "source": article.source,
        "url": article.url,
        "event_key": article.event_key,
        "event_type": article.event_type,
        "ranking_score": article.ranking_score,
        "trading_relevance": article.trading_relevance,
        "market_impact_score": article.market_impact_score,
        "actionability_score": article.actionability_score,
        "novelty_score": article.novelty_score,
        "confidence_score": article.confidence_score,
        "summary": article.summary,
        "affected_assets": article.affected_assets,
        "asset_impact": article.asset_impact,
        "time_horizon": article.time_horizon,
        "trading_logic": article.trading_logic,
        "priced_in": article.priced_in,
        "counter_argument": article.counter_argument,
        "invalidation": article.invalidation,
        "watch_signals": article.watch_signals,
        "review_metric": article.review_metric,
        "review_symbol": article.review_symbol,
        "expected_direction": article.expected_direction,
        "review_horizon_days": article.review_horizon_days,
        "political_economy_lesson": article.political_economy_lesson,
        "consensus_gap": article.consensus_gap,
    }
