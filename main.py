"""入口：CLI 手动运行 + 定时调度"""

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
from collectors.domestic_official.xinhua import XinhuaCollector
from collectors.international_finance.cnbc import CNBCCollector
from scheduler import CrawlScheduler


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_runner(config: dict) -> Runner:
    """根据配置组装管道组件"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    # Collector 注册（按配置启用）
    collectors = []
    cfg_domestic = config.get("collectors", {}).get("domestic_official", {})
    if cfg_domestic.get("xinhua", {}).get("enabled", False):
        collectors.append(XinhuaCollector(cfg_domestic["xinhua"]))
    cfg_intl = config.get("collectors", {}).get("international_finance", {})
    if cfg_intl.get("cnbc", {}).get("enabled", False):
        collectors.append(CNBCCollector(cfg_intl["cnbc"]))
    # 后续 Collector 在此注册...

    vault_path = config["vault"]["path"]
    fetcher = Fetcher()
    cleaner = Cleaner()
    analyzer = Analyzer(api_key=api_key, model=config["llm"]["fast_model"])
    article_filter = ArticleFilter(
        quality_threshold=config["filter"]["quality_threshold"],
        highlight_threshold=config["filter"]["highlight_threshold"],
    )
    writer = ObsidianWriter(vault_path)
    reporter = Reporter(api_key=api_key, model=config["llm"]["smart_model"])

    return Runner(
        collectors=collectors,
        fetcher=fetcher,
        cleaner=cleaner,
        analyzer=analyzer,
        article_filter=article_filter,
        writer=writer,
        reporter=reporter,
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
        scheduler = CrawlScheduler(runner, config["schedule"]["time"], config["schedule"]["timezone"])
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
