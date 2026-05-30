"""CSIS RSS 采集器 — 战略与国际研究中心"""

import feedparser
from models.article import RawArticle
from collectors.base import BaseCollector


class CSISCollector(BaseCollector):
    name = "csis"
    category = "D"

    DEFAULT_RSS = "https://www.csis.org/rss.xml"

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        rss_url = self.config.get("rss_url", self.DEFAULT_RSS)

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                description = entry.get("summary", entry.get("description", "")).strip()
                if title and link:
                    articles.append(RawArticle(
                        source=self.name,
                        category=self.category,
                        url=link,
                        title=title,
                        raw_content=description,
                        content_type="text/html",
                    ))
        except Exception:
            pass

        return articles
