"""APScheduler 封装：每日定时触发采集管道"""

import asyncio
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from pipeline.runner import Runner

log = logging.getLogger("infoCollector")


class CrawlScheduler:
    """定时任务调度器"""

    def __init__(self, runner: Runner, cron_time: str = "05:00", timezone: str = "Asia/Shanghai"):
        self.runner = runner
        self.scheduler = BackgroundScheduler(timezone=timezone)
        hour, minute = cron_time.split(":")
        self.scheduler.add_job(
            self._run_pipeline,
            trigger="cron",
            hour=int(hour),
            minute=int(minute),
            id="daily_crawl",
            name="Daily political-economic crawl",
        )

    def _run_pipeline(self):
        """调度器触发的同步包装"""
        try:
            asyncio.run(self.runner.run())
        except Exception as e:
            log.error(f"Scheduled pipeline failed: {e}")

    def start(self):
        self.scheduler.start()
        log.info(f"Scheduler started, next run: {self.scheduler.get_job('daily_crawl').next_run_time}")

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
