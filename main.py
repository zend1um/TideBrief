"""入口：CLI 手动运行 + 定时调度"""

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")  # 自动加载 .env 中的 API keys

import os
import asyncio
import logging
import argparse
import signal
from threading import Event

from pipeline.fetcher import Fetcher
from pipeline.cleaner import Cleaner
from pipeline.analyzer import Analyzer
from pipeline.filter import ArticleFilter
from pipeline.prefilter import SignalPrefilter
from pipeline.market import MarketDataProvider
from pipeline.calendar_sync import sync_economic_calendar
from pipeline.review_store import ThesisReviewStore
from pipeline.reporter import Reporter
from pipeline.runner import Runner
from utils.logger import setup_logger
from utils.obsidian import ObsidianWriter
from utils.config import load_config as load_project_config
from utils.runtime_status import RuntimeStatusStore, heartbeat_ping
from collectors.domestic_official.peopledaily import PeopleDailyCollector
from collectors.international_finance.cnbc import CNBCCollector
from collectors.international_finance.marketwatch import MarketWatchCollector
from collectors.international_finance.ftchinese import FTChineseCollector
from collectors.international_finance.projectsyndicate import ProjectSyndicateCollector
from collectors.international_finance.seekingalpha import SeekingAlphaCollector
from collectors.international_finance.zerohedge import ZeroHedgeCollector
from collectors.international_finance.bloomberg import BloombergCollector
from collectors.international_finance.yahoofinance import YahooFinanceCollector
from collectors.academic.nber import NBERCollector
from collectors.academic.cfr import CFRCollector
from collectors.academic.csis import CSISCollector
from collectors.social_media.hackernews import HackerNewsCollector
from collectors.social_media.arxiv import ArxivCollector
from collectors.social_media.twitter_nitter import TwitterNitterCollector
from scheduler import CrawlScheduler


def load_config(config_path: str = "config.yaml") -> dict:
    """保留原有入口，同时合并 UI 运行时设置和部署环境变量。"""
    return load_project_config(config_path)


def build_runner(config: dict) -> Runner:
    """根据配置组装管道组件"""
    provider = config["llm"]["provider"]
    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set in .env")
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    # Collector 注册（按配置启用）
    collectors = []
    cfg_domestic = config.get("collectors", {}).get("domestic_official", {})
    if cfg_domestic.get("peopledaily", {}).get("enabled", False):
        collectors.append(PeopleDailyCollector(cfg_domestic["peopledaily"]))
    cfg_intl = config.get("collectors", {}).get("international_finance", {})
    if cfg_intl.get("cnbc", {}).get("enabled", False):
        collectors.append(CNBCCollector(cfg_intl["cnbc"]))
    if cfg_intl.get("marketwatch", {}).get("enabled", False):
        collectors.append(MarketWatchCollector(cfg_intl["marketwatch"]))
    if cfg_intl.get("ftchinese", {}).get("enabled", False):
        collectors.append(FTChineseCollector(cfg_intl["ftchinese"]))
    if cfg_intl.get("projectsyndicate", {}).get("enabled", False):
        collectors.append(ProjectSyndicateCollector(cfg_intl["projectsyndicate"]))
    if cfg_intl.get("seekingalpha", {}).get("enabled", False):
        collectors.append(SeekingAlphaCollector(cfg_intl["seekingalpha"]))
    if cfg_intl.get("zerohedge", {}).get("enabled", False):
        collectors.append(ZeroHedgeCollector(cfg_intl["zerohedge"]))
    if cfg_intl.get("bloomberg", {}).get("enabled", False):
        collectors.append(BloombergCollector(cfg_intl["bloomberg"]))
    if cfg_intl.get("yahoofinance", {}).get("enabled", False):
        collectors.append(YahooFinanceCollector(cfg_intl["yahoofinance"]))
    cfg_academic = config.get("collectors", {}).get("academic", {})
    if cfg_academic.get("nber", {}).get("enabled", False):
        collectors.append(NBERCollector(cfg_academic["nber"]))
    if cfg_academic.get("cfr", {}).get("enabled", False):
        collectors.append(CFRCollector(cfg_academic["cfr"]))
    if cfg_academic.get("csis", {}).get("enabled", False):
        collectors.append(CSISCollector(cfg_academic["csis"]))
    cfg_social = config.get("collectors", {}).get("social_media", {})
    if cfg_social.get("hackernews", {}).get("enabled", False):
        collectors.append(HackerNewsCollector(cfg_social["hackernews"]))
    if cfg_social.get("arxiv", {}).get("enabled", False):
        collectors.append(ArxivCollector(cfg_social["arxiv"]))
    if cfg_social.get("twitter", {}).get("enabled", False):
        collectors.append(TwitterNitterCollector(cfg_social["twitter"]))
    # 后续 Collector 在此注册...

    vault_path = config["vault"]["path"]
    fetcher = Fetcher()
    cleaner = Cleaner()
    provider = config["llm"]["provider"]
    analyzer = Analyzer(
        provider=provider,
        api_key=api_key,
        model=config["llm"]["fast_model"],
        include_full_translation=config.get("llm", {}).get("include_full_translation", False),
    )
    filter_cfg = config.get("filter", {})
    prefilter_cfg = filter_cfg.get("prefilter", {})
    article_prefilter = SignalPrefilter(
        min_score=prefilter_cfg.get("min_score", 3.5),
        max_candidates=prefilter_cfg.get("max_candidates", 24),
        max_per_source=prefilter_cfg.get("max_per_source", 5),
        dedupe_threshold=prefilter_cfg.get("dedupe_threshold", 88),
        focus_keywords=prefilter_cfg.get("focus_keywords", []),
        source_weights=prefilter_cfg.get("source_weights", {}),
        category_limits=prefilter_cfg.get("category_limits"),
    )
    article_filter = ArticleFilter(
        quality_threshold=filter_cfg.get("quality_threshold", 5),
        highlight_threshold=filter_cfg.get("highlight_threshold", 8),
        relevance_threshold=filter_cfg.get("relevance_threshold", 6),
        ranking_threshold=filter_cfg.get("ranking_threshold", 6.2),
        actionability_threshold=filter_cfg.get("actionability_threshold", 5),
        max_daily_items=filter_cfg.get("max_daily_items", 8),
        max_context_items=filter_cfg.get("max_context_items", 2),
        event_dedupe_threshold=filter_cfg.get("event_dedupe_threshold", 84),
    )
    writer = ObsidianWriter(vault_path)
    reporter = Reporter(provider=provider, api_key=api_key, model=config["llm"]["smart_model"])
    vault_overrides = config.get("vault", {}).get("overrides", {})
    market_cfg = config.get("market", {})
    market_provider = None
    if market_cfg.get("enabled", True):
        market_provider = MarketDataProvider(
            symbols=market_cfg.get("symbols"),
            period=market_cfg.get("period", "10d"),
        )
    output_cfg = config.get("output", {})
    review_store = ThesisReviewStore(
        output_cfg.get("review_database", "data/thesis_reviews.db"),
        move_threshold_pct=output_cfg.get("review_move_threshold_pct", 0.3),
    )

    return Runner(
        collectors=collectors,
        fetcher=fetcher,
        cleaner=cleaner,
        analyzer=analyzer,
        article_filter=article_filter,
        writer=writer,
        reporter=reporter,
        vault_overrides=vault_overrides,
        prefilter=article_prefilter,
        market_provider=market_provider,
        archive_raw=output_cfg.get("archive_raw", False),
        write_single_articles=output_cfg.get("single_articles", True),
        generate_brief=output_cfg.get("daily_brief", True),
        dashboard_snapshot_path=output_cfg.get("dashboard_snapshot", "data/dashboard.json"),
        review_store=review_store,
    )


def main():
    parser = argparse.ArgumentParser(description="政治经济信息采集工具")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "schedule", "ui", "calendar-sync"],
        help="run: 立即采集; schedule: 定时调度; ui: 本地仪表盘; calendar-sync: 同步官方日历",
    )
    parser.add_argument("--source", type=str, help="仅运行指定 Collector")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="UI 监听地址")
    parser.add_argument("--port", type=int, default=8765, help="UI 监听端口")
    args = parser.parse_args()

    log = setup_logger()
    config = load_config(args.config)
    if args.command == "ui":
        import uvicorn
        os.environ["INFOCOLLECTOR_CONFIG"] = str(Path(args.config).resolve())
        log.info(f"Opening local dashboard at http://{args.host}:{args.port}")
        uvicorn.run("ui.server:app", host=args.host, port=args.port, log_level="warning")
        return
    if args.command == "calendar-sync":
        result = sync_economic_calendar(config)
        log.info(
            "Calendar sync complete: fetched=%s matched=%s total=%s",
            result.fetched,
            result.matched,
            result.total,
        )
        return

    runner = build_runner(config)

    if args.source:
        runner.collectors = [c for c in runner.collectors if c.name == args.source]
        if not runner.collectors:
            log.warning(f"Collector '{args.source}' not found or not enabled")

    if args.command == "run":
        log.info("Running pipeline once...")
        status = RuntimeStatusStore(config.get("output", {}).get("runtime_status", "data/runtime-status.json"))
        status.job_started("daily_collect")
        heartbeat_ping("start")
        try:
            result = asyncio.run(runner.run())
        except Exception as exc:
            status.job_failed("daily_collect", exc)
            heartbeat_ping("fail", str(exc))
            raise
        else:
            status.job_succeeded(
                "daily_collect",
                {
                    "signals": len(result.highlight),
                    "context": len(result.keep),
                    "collected": result.total_collected,
                },
            )
            heartbeat_ping("success")
        log.info("Done.")
    elif args.command == "schedule":
        log.info("Starting scheduler...")
        scheduler = CrawlScheduler(
            runner,
            collect_time=config["schedule"]["collect_time"],
            morning_time=config["schedule"]["morning_brief_time"],
            timezone=config["schedule"]["timezone"],
            vault_path=config["vault"]["path"],
            morning_brief_enabled=config.get("output", {}).get("morning_brief", False),
            project_config=config,
        )
        scheduler.start()
        stop_event = Event()

        def request_shutdown(*_args):
            stop_event.set()

        signal.signal(signal.SIGTERM, request_shutdown)
        signal.signal(signal.SIGINT, request_shutdown)
        try:
            while not stop_event.wait(60):
                scheduler.heartbeat()
        finally:
            scheduler.shutdown()
            log.info("Shutdown.")


if __name__ == "__main__":
    main()
