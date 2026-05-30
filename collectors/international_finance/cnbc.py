"""CNBC RSS 采集器"""

import feedparser
from datetime import datetime, timezone
from models.article import RawArticle
from collectors.base import BaseCollector


class CNBCCollector(BaseCollector):
    name = "cnbc"
    category = "B"

    FEEDS = {
        "top": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    }

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        enabled_feeds = self.config.get("feeds", ["top", "economy"])

        for feed_name in enabled_feeds:
            url = self.FEEDS.get(feed_name)
            if not url:
                continue
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    description = entry.get("summary", entry.get("description", "")).strip()
                    pub_date = None
                    pub_parsed = entry.get("published_parsed", entry.get("updated_parsed"))
                    if pub_parsed:
                        try:
                            pub_date = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass

                    if title and link:
                        articles.append(RawArticle(
                            source=self.name,
                            category=self.category,
                            url=link,
                            title=title,
                            raw_content=description,
                            content_type="text/html",
                            pub_date=pub_date,
                        ))
            except Exception:
                continue

        return articles
