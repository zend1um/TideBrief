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
from pipeline.reporter import Reporter
from utils.obsidian import ObsidianWriter
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
    ):
        self.collectors = collectors
        self.fetcher = fetcher
        self.cleaner = cleaner
        self.analyzer = analyzer
        self.article_filter = article_filter
        self.writer = writer
        self.reporter = reporter

    async def run(self) -> FilterResult:
        """执行完整管道"""
        log.info(f"Pipeline started with {len(self.collectors)} collectors")

        # 阶段一：并行采集
        raw_articles = await self._collect_all()
        log.info(f"Collected {len(raw_articles)} raw articles")

        # Fetch 完整内容
        articles: list[Article] = []
        for raw in raw_articles:
            try:
                article = await self.fetcher.fetch(raw)
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

        # 写入 Obsidian Vault
        all_kept = result.highlight + result.keep
        for a in all_kept:
            try:
                self.writer.write_article(a)
            except Exception as e:
                log.error(f"Write article failed for {a.id}: {e}")

        # 生成每日汇总
        if all_kept:
            try:
                overview, learning_points = self.reporter.generate_overview(all_kept)
                self.writer.write_brief(
                    datetime.now(), result.highlight, result.keep,
                    result.discarded, overview, learning_points,
                )
            except Exception as e:
                log.error(f"Report generation failed: {e}")

        log.info(f"Pipeline complete: {len(result.highlight)} H / {len(result.keep)} K / {len(result.discarded)} D")
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
