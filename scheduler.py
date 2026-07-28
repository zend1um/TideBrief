"""APScheduler 封装：每日 4:00 采集 + 8:00 晨报"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from filelock import FileLock, Timeout
from pipeline.calendar_sync import sync_economic_calendar
from pipeline.runner import Runner
from utils.runtime_status import RuntimeStatusStore, heartbeat_ping

log = logging.getLogger("infoCollector")


class CrawlScheduler:
    """定时任务调度器"""

    def __init__(self, runner: Runner, collect_time: str = "04:00",
                 morning_time: str = "08:00", timezone: str = "Asia/Shanghai",
                 vault_path: str = "", morning_brief_enabled: bool = False,
                 project_config: dict | None = None):
        self.runner = runner
        self.vault_path = vault_path
        self.project_config = project_config or {}
        output_config = self.project_config.get("output", {})
        schedule_config = self.project_config.get("schedule", {})
        self.collect_time = collect_time
        self.run_on_start_if_stale = schedule_config.get("run_on_start_if_stale", True)
        self.stale_after_hours = max(1, int(schedule_config.get("stale_after_hours", 26)))
        self.status = RuntimeStatusStore(output_config.get("runtime_status", "data/runtime-status.json"))
        self.pipeline_lock = FileLock(str(Path("logs") / "daily_collect.lock"), timeout=0)
        self.scheduler = BackgroundScheduler(
            timezone=timezone,
            job_defaults={
                "max_instances": 1,
                "coalesce": True,
                "misfire_grace_time": 6 * 60 * 60,
            },
        )

        h, m = collect_time.split(":")
        self.scheduler.add_job(
            self._run_pipeline,
            trigger="cron", hour=int(h), minute=int(m),
            id="daily_collect", name="Daily collection + analysis",
        )

        if morning_brief_enabled:
            h2, m2 = morning_time.split(":")
            self.scheduler.add_job(
                self._run_morning_brief,
                trigger="cron", hour=int(h2), minute=int(m2),
                id="morning_brief", name="Morning brief generation",
            )

        calendar_config = self.project_config.get("calendar", {})
        if calendar_config.get("sync_enabled", False):
            sync_hour, sync_minute = str(calendar_config.get("sync_time", "03:30")).split(":")
            self.scheduler.add_job(
                self._run_calendar_sync,
                trigger="cron",
                day_of_week=calendar_config.get("sync_day_of_week", "sun"),
                hour=int(sync_hour),
                minute=int(sync_minute),
                id="calendar_sync",
                name="Official economic calendar sync",
            )

    def _run_pipeline(self):
        self.status.job_started("daily_collect")
        heartbeat_ping("start")
        try:
            with self.pipeline_lock:
                result = asyncio.run(self.runner.run())
        except Timeout:
            message = "Another collection process is already running"
            self.status.job_skipped("daily_collect", message)
            log.warning("%s; skipped duplicate schedule", message)
        except Exception as e:
            self.status.job_failed("daily_collect", e)
            heartbeat_ping("fail", str(e))
            log.exception("Scheduled collection failed")
        else:
            details = {
                "signals": len(result.highlight),
                "context": len(result.keep),
                "collected": result.total_collected,
            }
            self.status.job_succeeded("daily_collect", details)
            heartbeat_ping("success")

    def _run_morning_brief(self):
        self.status.job_started("morning_brief")
        try:
            asyncio.run(self._generate_morning_brief())
        except Exception as e:
            self.status.job_failed("morning_brief", e)
            log.exception("Morning brief generation failed")
        else:
            self.status.job_succeeded("morning_brief")

    def _run_calendar_sync(self):
        self.status.job_started("calendar_sync")
        try:
            result = sync_economic_calendar(self.project_config)
        except Exception as exc:
            self.status.job_failed("calendar_sync", exc)
            log.exception("Economic calendar sync failed")
        else:
            self.status.job_succeeded(
                "calendar_sync",
                {
                    "fetched": result.fetched,
                    "matched": result.matched,
                    "total": result.total,
                },
            )
            log.info("Economic calendar synced: %s official events matched", result.matched)

    async def _generate_morning_brief(self):
        """读取昨日已分析文章，生成晨报"""
        import frontmatter
        from datetime import timedelta
        from models.article import Article
        from utils.obsidian import ObsidianWriter

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        # 4:00 采集的是前一天的数据，所以读昨天的目录
        crawl_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        vault = Path(self.vault_path)

        articles_dir = vault / "信息条目" / crawl_date
        if not articles_dir.exists():
            log.warning(f"No articles found for {crawl_date}, skipping morning brief")
            return

        articles = []
        for f in articles_dir.glob("*.md"):
            try:
                post = frontmatter.load(str(f))
                content = f.read_text(encoding="utf-8")
                score = post.get("quality", 0)
                if score < 7:
                    continue
                # 文件名格式: source-hash.md, 提取纯 hash 作为 id
                stem = f.stem  # e.g. "cnbc-a767adfbf003"
                source = post.get("source", "")
                article_id = stem[len(source)+1:] if stem.startswith(source + "-") else stem
                a = Article(
                    id=article_id, source=source,
                    category=post.get("category", ""),
                    url=post.get("url", ""),
                    title=post.get("title", stem),
                    raw_content="",
                )
                a.quality_score = score
                a.crawl_time = now
                # 如果 frontmatter 没有 title，尝试从正文提取
                if not a.title or a.title == stem:
                    for line in content.split("\n"):
                        line = line.strip()
                        # 找 # 标题 或 标题：模式
                        if line.startswith("# ") and not line.startswith("## "):
                            a.title = line[2:].strip()
                            break
                        if line.startswith("标题："):
                            a.title = line[3:].strip()
                            break
                    if not a.title or a.title == stem:
                        a.title = stem
                a.summary = content[:800]
                articles.append(a)
            except Exception:
                continue

        articles.sort(key=lambda x: x.quality_score, reverse=True)

        if not articles:
            log.warning("No high-quality articles for morning brief")
            return

        reporter = self.runner.reporter
        brief = reporter.generate_morning_brief(articles[:40])
        overview = brief.get("overview", "生成失败")
        points = brief.get("learning_points", "无")
        themes = brief.get("themes", "")

        writer = ObsidianWriter(str(vault))
        from datetime import datetime as dt
        crawl_dt = dt.strptime(crawl_date, "%Y-%m-%d")
        writer.write_morning_brief(crawl_dt, articles[:20], overview, points, themes)
        log.info(f"Morning brief written: {vault / '每日简报' / f'晨报-{date_str}.md'}")

    def start(self):
        self.scheduler.start()
        for job in self.scheduler.get_jobs():
            log.info(f"Scheduled: {job.name} at next run: {job.next_run_time}")
        if self._daily_collect_is_stale():
            self.scheduler.add_job(
                self._run_pipeline,
                id="startup_catchup",
                name="Startup catch-up collection",
                replace_existing=True,
            )
            log.info("Latest dashboard is stale; scheduled an immediate catch-up collection")
        if self._calendar_is_stale():
            self.scheduler.add_job(
                self._run_calendar_sync,
                id="startup_calendar_sync",
                name="Startup calendar catch-up",
                replace_existing=True,
            )
            log.info("Economic calendar is stale; scheduled an immediate sync")
        self.heartbeat()

    def heartbeat(self):
        next_runs = {
            job.id: job.next_run_time.isoformat() if job.next_run_time else None
            for job in self.scheduler.get_jobs()
        }
        self.status.scheduler_heartbeat(next_runs)

    def shutdown(self):
        self.scheduler.shutdown(wait=False)

    def _daily_collect_is_stale(self) -> bool:
        if not self.run_on_start_if_stale:
            return False
        status = self.status.read().get("jobs", {}).get("daily_collect", {})
        latest = self._parse_datetime(status.get("last_success_at"))
        if latest is None:
            dashboard = Path(
                self.project_config.get("output", {}).get("dashboard_snapshot", "data/dashboard.json")
            )
            if dashboard.exists():
                latest = datetime.fromtimestamp(dashboard.stat().st_mtime).astimezone()
        if latest is None:
            return True
        return datetime.now().astimezone() - latest.astimezone() >= timedelta(hours=self.stale_after_hours)

    def _calendar_is_stale(self) -> bool:
        calendar_config = self.project_config.get("calendar", {})
        if not calendar_config.get("sync_enabled", False):
            return False
        latest = self._parse_datetime(
            self.status.read().get("jobs", {}).get("calendar_sync", {}).get("last_success_at")
        )
        if latest is None:
            path = Path(calendar_config.get("path", "ui/economic-calendar.json"))
            if path.exists():
                try:
                    import json

                    latest = self._parse_datetime(
                        json.loads(path.read_text(encoding="utf-8")).get("as_of")
                    )
                except (OSError, json.JSONDecodeError):
                    latest = None
        return latest is None or datetime.now().astimezone() - latest.astimezone() >= timedelta(days=8)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
