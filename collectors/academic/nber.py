"""NBER RSS 采集器 — 美国国家经济研究局工作论文"""

import feedparser
from models.article import RawArticle
from collectors.base import BaseCollector


class NBERCollector(BaseCollector):
    name = "nber"
    category = "D"

    DEFAULT_RSS = "https://www.nber.org/rss/new.xml"

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
