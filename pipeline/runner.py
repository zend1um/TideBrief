"""管道编排器：串联采集 → 清洗 → 分析 → 过滤 → 写入 → 报告"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from collectors.base import BaseCollector
from pipeline.fetcher import Fetcher
from pipeline.cleaner import Cleaner
from pipeline.analyzer import Analyzer
from pipeline.filter import ArticleFilter, FilterResult
from pipeline.prefilter import SignalPrefilter, PrefilterResult
from pipeline.market import MarketDataProvider
from pipeline.review_store import ThesisReviewStore
from pipeline.reporter import Reporter
from utils.obsidian import ObsidianWriter
from utils.dashboard import write_dashboard_snapshot
from models.article import Article, RawArticle

log = logging.getLogger("infoCollector")


class Runner:
    """信息采集管道编排器"""

    def __init__(
        self,
        collectors: list[BaseCollector],
        fetcher: Fetcher,
        cleaner: Cleaner,
        analyzer: Analyzer,
        article_filter: ArticleFilter,
        writer: ObsidianWriter,
        reporter: Reporter,
        vault_overrides: dict[str, str] | None = None,
        prefilter: SignalPrefilter | None = None,
        market_provider: MarketDataProvider | None = None,
        archive_raw: bool = False,
        write_single_articles: bool = True,
        generate_brief: bool = True,
        dashboard_snapshot_path: str | None = None,
        review_store: ThesisReviewStore | None = None,
    ):
        self.collectors = collectors
        self.fetcher = fetcher
        self.cleaner = cleaner
        self.analyzer = analyzer
        self.article_filter = article_filter
        self.writer = writer
        self.reporter = reporter
        self.vault_overrides = vault_overrides or {}
        self.prefilter = prefilter
        self.market_provider = market_provider
        self.archive_raw = archive_raw
        self.write_single_articles = write_single_articles
        self.generate_brief = generate_brief
        self.dashboard_snapshot_path = dashboard_snapshot_path
        self.review_store = review_store
        # 按需创建的路由 writer 缓存
        self._writers: dict[str, ObsidianWriter] = {}

    def _get_writer(self, article: Article) -> ObsidianWriter:
        """根据 article source 路由到对应 vault 的 writer"""
        vault = self.vault_overrides.get(article.source)
        if not vault:
            return self.writer
        if vault not in self._writers:
            self._writers[vault] = ObsidianWriter(vault)
        return self._writers[vault]

    async def run(self) -> FilterResult:
        """执行完整管道"""
        log.info(f"Pipeline started with {len(self.collectors)} collectors")

        # 阶段一：并行采集
        raw_articles = await self._collect_all()
        log.info(f"Collected {len(raw_articles)} raw articles")

        # 先按标题、摘要和来源做透明预筛，再下载全文和调用 LLM。
        if self.prefilter:
            prefilter_result = self.prefilter.apply(raw_articles)
        else:
            prefilter_result = PrefilterResult(selected=raw_articles)
        candidates = prefilter_result.selected
        log.info(
            f"Prefilter: {len(candidates)} candidates, {len(prefilter_result.rejected)} rejected, "
            f"{len(prefilter_result.duplicates)} duplicates"
        )

        # Fetch 完整内容
        articles: list[Article] = []
        for raw in candidates:
            try:
                article = await self.fetcher.fetch(raw)
                article.prefilter_score = prefilter_result.scores.get(article.id, 0.0)
                articles.append(article)
            except Exception as e:
                log.error(f"Fetch failed for {raw.source}:{raw.title}: {e}")

        # 阶段二：串行处理
        # 清洗
        for a in articles:
            try:
                self.cleaner.clean(a)
            except Exception as e:
                log.error(f"Clean failed for {a.id}: {e}")

        # 原始全文默认不再全部落库，避免 Vault 再次成为信息垃圾场。
        if self.archive_raw:
            for a in articles:
                try:
                    if a.clean_content:
                        self._get_writer(a).write_raw(a)
                except Exception as e:
                    log.error(f"Write raw failed for {a.id}: {e}")

        # LLM 分析（逐个调用，避免并发限流）
        for a in articles:
            try:
                self.analyzer.analyze(a)
            except Exception as e:
                log.error(f"Analyze failed for {a.id}: {e}")
                a.quality_score = 3
                a.quality_reason = f"分析异常: {e}"

        # 过滤
        result = self.article_filter.apply(articles)
        result.total_collected = len(raw_articles)
        result.prefilter_rejected = len(prefilter_result.rejected)
        result.duplicate_count = len(prefilter_result.duplicates)

        # 写入 Obsidian Vault（按 source 路由到不同 vault）
        all_kept = result.highlight + result.keep
        if self.write_single_articles:
            for a in all_kept:
                try:
                    self._get_writer(a).write_article(a)
                except Exception as e:
                    log.error(f"Write article failed for {a.id}: {e}")

        market_snapshot = None
        if self.market_provider:
            try:
                market_snapshot = await asyncio.to_thread(self.market_provider.fetch)
            except Exception as e:
                log.error(f"Market snapshot failed: {e}")

        review_time = datetime.now().astimezone()
        if self.review_store:
            try:
                self.review_store.capture_and_evaluate(result.highlight, market_snapshot, review_time)
            except Exception as e:
                log.error(f"Thesis review update failed: {e}")

        # 无信号时也写一份明确的“空白日报”，避免用户误以为任务没运行。
        if self.generate_brief:
            try:
                synthesis = self.reporter.generate_daily_brief(all_kept, market_snapshot)
                overview = str(synthesis.get("market_regime", ""))
                questions = synthesis.get("calibration_questions", [])
                learning_points = (
                    "\n".join(f"{index}. {item}" for index, item in enumerate(questions, 1))
                    if isinstance(questions, list) else str(questions)
                )
                report_time = review_time
                stats = {
                    "total_collected": len(raw_articles),
                    "prefilter_rejected": len(prefilter_result.rejected),
                    "duplicates": len(prefilter_result.duplicates),
                    "analyzed": len(articles),
                    "displayed": len(all_kept),
                }
                self.writer.write_brief(
                    report_time, result.highlight, result.keep,
                    result.discarded, overview, learning_points,
                    market_snapshot=market_snapshot,
                    synthesis=synthesis,
                    stats=stats,
                )
                if self.dashboard_snapshot_path:
                    write_dashboard_snapshot(
                        self.dashboard_snapshot_path, report_time, result,
                        synthesis, market_snapshot, stats,
                    )
            except Exception as e:
                log.error(f"Report generation failed: {e}")

        log.info(
            f"Pipeline complete: {len(result.highlight)} signals / {len(result.keep)} context / "
            f"{len(result.discarded)} analyzed but omitted"
        )
        return result

    async def _collect_all(self) -> list[RawArticle]:
        """并行执行所有 Collector"""
        tasks = []
        for c in self.collectors:
            tasks.append(self._safe_collect(c))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_raw: list[RawArticle] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(f"Collector {self.collectors[i]} failed: {result}")
            elif isinstance(result, list):
                all_raw.extend(result)

        return all_raw

    async def _safe_collect(self, collector: BaseCollector) -> list[RawArticle]:
        """安全的 Collector 调用，异常隔离"""
        try:
            log.info(f"Collecting from {collector.name}...")
            articles = await collector.collect()
            log.info(f"  {collector.name}: {len(articles)} articles")
            return articles
        except Exception as e:
            log.error(f"Collector {collector.name} error: {e}")
            return []
