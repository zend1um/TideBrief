"""新华社 RSS 采集器"""

import feedparser
from datetime import datetime, timezone
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

            pub_date = None
            pub_parsed = entry.get("published_parsed", entry.get("updated_parsed"))
            if pub_parsed:
                try:
                    pub_date = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            articles.append(RawArticle(
                source=self.name,
                category=self.category,
                url=link,
                title=title,
                raw_content=description,
                content_type="text/html",
                pub_date=pub_date,
            ))

        return articles
