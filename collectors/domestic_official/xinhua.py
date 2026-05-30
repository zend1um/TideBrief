"""新华社 RSS 采集器"""

import feedparser
from models.article import RawArticle
from collectors.base import BaseCollector


class XinhuaCollector(BaseCollector):
    name = "xinhua"
    category = "A"

    DEFAULT_RSS = "http://www.xinhuanet.com/politics/xhll.xml"

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        rss_url = self.config.get("rss_url", self.DEFAULT_RSS)

        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            description = entry.get("summary", entry.get("description", "")).strip()

            if not title or not link:
                continue

            articles.append(RawArticle(
                source=self.name,
                category=self.category,
                url=link,
                title=title,
                raw_content=description,
                content_type="text/html",
            ))

        return articles
