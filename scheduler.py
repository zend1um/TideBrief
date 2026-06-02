"""APScheduler 封装：每日 4:00 采集 + 8:00 晨报"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from pipeline.runner import Runner

log = logging.getLogger("infoCollector")


class CrawlScheduler:
    """定时任务调度器"""

    def __init__(self, runner: Runner, collect_time: str = "04:00",
                 morning_time: str = "08:00", timezone: str = "Asia/Shanghai",
                 vault_path: str = ""):
        self.runner = runner
        self.vault_path = vault_path
        self.scheduler = BackgroundScheduler(timezone=timezone)

        h, m = collect_time.split(":")
        self.scheduler.add_job(
            self._run_pipeline,
            trigger="cron", hour=int(h), minute=int(m),
            id="daily_collect", name="Daily collection + analysis",
        )

        h2, m2 = morning_time.split(":")
        self.scheduler.add_job(
            self._run_morning_brief,
            trigger="cron", hour=int(h2), minute=int(m2),
            id="morning_brief", name="Morning brief generation",
        )

    def _run_pipeline(self):
        try:
            asyncio.run(self.runner.run())
        except Exception as e:
            log.error(f"Scheduled collection failed: {e}")

    def _run_morning_brief(self):
        try:
            asyncio.run(self._generate_morning_brief())
        except Exception as e:
            log.error(f"Morning brief generation failed: {e}")

    async def _generate_morning_brief(self):
        """读取昨日已分析文章，生成晨报"""
        import frontmatter
        from datetime import timedelta

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
                    content = f.read_text(encoding="utf-8")
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

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
