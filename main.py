"""入口：CLI 手动运行 + 定时调度"""

from dotenv import load_dotenv
load_dotenv()  # 自动加载 .env 中的 API keys

import os
import sys
import asyncio
import logging
import argparse
import yaml
from pathlib import Path

from pipeline.fetcher import Fetcher
from pipeline.cleaner import Cleaner
from pipeline.analyzer import Analyzer
from pipeline.filter import ArticleFilter
from pipeline.reporter import Reporter
from pipeline.runner import Runner
from utils.logger import setup_logger
from utils.obsidian import ObsidianWriter
from collectors.domestic_official.peopledaily import PeopleDailyCollector
from collectors.international_finance.cnbc import CNBCCollector
from collectors.international_finance.marketwatch import MarketWatchCollector
from collectors.international_finance.ftchinese import FTChineseCollector
from collectors.international_finance.projectsyndicate import ProjectSyndicateCollector
from collectors.academic.nber import NBERCollector
from collectors.academic.cfr import CFRCollector
from collectors.academic.csis import CSISCollector
from collectors.social_media.hackernews import HackerNewsCollector
from collectors.social_media.arxiv import ArxivCollector
from scheduler import CrawlScheduler


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    # 后续 Collector 在此注册...

    vault_path = config["vault"]["path"]
    fetcher = Fetcher()
    cleaner = Cleaner()
    provider = config["llm"]["provider"]
    analyzer = Analyzer(provider=provider, api_key=api_key, model=config["llm"]["fast_model"])
    article_filter = ArticleFilter(
        quality_threshold=config["filter"]["quality_threshold"],
        highlight_threshold=config["filter"]["highlight_threshold"],
    )
    writer = ObsidianWriter(vault_path)
    reporter = Reporter(provider=provider, api_key=api_key, model=config["llm"]["smart_model"])
    vault_overrides = config.get("vault", {}).get("overrides", {})

    return Runner(
        collectors=collectors,
        fetcher=fetcher,
        cleaner=cleaner,
        analyzer=analyzer,
        article_filter=article_filter,
        writer=writer,
        reporter=reporter,
        vault_overrides=vault_overrides,
    )


def main():
    parser = argparse.ArgumentParser(description="政治经济信息采集工具")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "schedule"],
                        help="run: 立即执行一次采集; schedule: 启动定时调度")
    parser.add_argument("--source", type=str, help="仅运行指定 Collector")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    log = setup_logger()
    config = load_config(args.config)
    runner = build_runner(config)

    if args.source:
        runner.collectors = [c for c in runner.collectors if c.name == args.source]
        if not runner.collectors:
            log.warning(f"Collector '{args.source}' not found or not enabled")

    if args.command == "run":
        log.info("Running pipeline once...")
        asyncio.run(runner.run())
        log.info("Done.")
    elif args.command == "schedule":
        log.info("Starting scheduler...")
        scheduler = CrawlScheduler(
            runner,
            collect_time=config["schedule"]["collect_time"],
            morning_time=config["schedule"]["morning_brief_time"],
            timezone=config["schedule"]["timezone"],
            vault_path=config["vault"]["path"],
        )
        scheduler.start()
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.shutdown()
            log.info("Shutdown.")


if __name__ == "__main__":
    main()
