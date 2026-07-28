"""按交易相关性、可操作性和阅读预算筛选文章。"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from models.article import Article

try:
    from rapidfuzz import fuzz, utils as fuzz_utils
except ImportError:
    fuzz = None
    fuzz_utils = None

log = logging.getLogger("infoCollector")


@dataclass
class FilterResult:
    # highlight = 今日交易信号；keep = 政经背景阅读。保留旧名称以兼容调用方。
    highlight: list[Article] = field(default_factory=list)
    keep: list[Article] = field(default_factory=list)
    discarded: list[Article] = field(default_factory=list)
    total_collected: int = 0
    prefilter_rejected: int = 0
    duplicate_count: int = 0


class ArticleFilter:
    """最终排序器：每日最多给用户固定数量的信息。"""

    def __init__(
        self,
        quality_threshold: int = 5,
        highlight_threshold: int = 8,
        relevance_threshold: int = 6,
        ranking_threshold: float = 6.2,
        actionability_threshold: int = 5,
        max_daily_items: int = 8,
        max_context_items: int = 2,
        event_dedupe_threshold: float = 84.0,
    ):
        self.quality_threshold = quality_threshold
        self.highlight_threshold = highlight_threshold
        self.relevance_threshold = relevance_threshold
        self.ranking_threshold = ranking_threshold
        self.actionability_threshold = actionability_threshold
        self.max_daily_items = max_daily_items
        self.max_context_items = min(max_context_items, max_daily_items)
        self.event_dedupe_threshold = event_dedupe_threshold

    def apply(self, articles: list[Article]) -> FilterResult:
        # 旧测试、旧缓存文章没有新评分时，仍按原来的 quality_score 分档。
        if not any(a.ranking_score or a.trading_relevance or a.actionability_score for a in articles):
            return self._apply_legacy(articles)

        result = FilterResult()
        ranked = sorted(
            articles,
            key=lambda a: (a.ranking_score, a.trading_relevance, a.market_impact_score, a.prefilter_score),
            reverse=True,
        )

        trading_slots = max(0, self.max_daily_items - self.max_context_items)
        event_keys: list[str] = []
        context_candidates: list[Article] = []

        for article in ranked:
            if self._is_duplicate_event(article, event_keys):
                article.quality_reason = self._append_reason(article.quality_reason, "同一事件已有更高排名报道")
                result.discarded.append(article)
                continue

            is_trade_signal = (
                article.trading_relevance >= self.relevance_threshold
                and article.actionability_score >= self.actionability_threshold
                and article.ranking_score >= self.ranking_threshold
            )
            if is_trade_signal and len(result.highlight) < trading_slots:
                result.highlight.append(article)
                event_keys.append(article.event_key or article.title)
                continue

            is_context = (
                article.trading_relevance >= max(4, self.relevance_threshold - 1)
                and bool(article.political_economy_lesson)
                and article.category in {"A", "D", "B"}
            )
            if is_context:
                context_candidates.append(article)
            else:
                result.discarded.append(article)

        for article in context_candidates:
            if len(result.keep) >= self.max_context_items:
                result.discarded.append(article)
                continue
            if self._is_duplicate_event(article, event_keys):
                result.discarded.append(article)
                continue
            result.keep.append(article)
            event_keys.append(article.event_key or article.title)

        # 若当天政经背景不足，把空余名额让给交易信号，而不是为了配额硬塞文章。
        remaining = self.max_daily_items - len(result.highlight) - len(result.keep)
        if remaining > 0:
            eligible = [
                a for a in result.discarded
                if a.trading_relevance >= self.relevance_threshold
                and a.actionability_score >= self.actionability_threshold
                and a.ranking_score >= self.ranking_threshold
                and not self._is_duplicate_event(a, event_keys)
            ][:remaining]
            for article in eligible:
                result.discarded.remove(article)
                result.highlight.append(article)
                event_keys.append(article.event_key or article.title)

        for article in result.highlight:
            log.info(f"SIGNAL  [{article.ranking_score:.1f}] {article.title[:60]}")
        for article in result.keep:
            log.info(f"CONTEXT [{article.ranking_score:.1f}] {article.title[:60]}")

        log.info(
            f"Filter summary: {len(result.highlight)} signals, {len(result.keep)} context, "
            f"{len(result.discarded)} analyzed but omitted"
        )
        return result

    def _apply_legacy(self, articles: list[Article]) -> FilterResult:
        result = FilterResult()
        for article in articles:
            if article.quality_score >= self.highlight_threshold:
                result.highlight.append(article)
            elif article.quality_score >= self.quality_threshold:
                result.keep.append(article)
            else:
                result.discarded.append(article)
        return result

    def _is_duplicate_event(self, article: Article, selected_keys: list[str]) -> bool:
        key = article.event_key or article.title
        if not key or not selected_keys:
            return False
        if fuzz is None:
            from difflib import SequenceMatcher
            return any(
                SequenceMatcher(None, key.lower(), other.lower()).ratio() * 100 >= self.event_dedupe_threshold
                for other in selected_keys
            )
        return any(
            max(
                fuzz.WRatio(key, other, processor=fuzz_utils.default_process),
                fuzz.token_set_ratio(key, other, processor=fuzz_utils.default_process),
            ) >= self.event_dedupe_threshold
            for other in selected_keys
        )

    @staticmethod
    def _append_reason(original: str, extra: str) -> str:
        return f"{original}；{extra}" if original else extra
