"""CFR RSS 采集器 — 外交关系委员会"""

import feedparser
from datetime import datetime, timezone
from models.article import RawArticle
from collectors.base import BaseCollector


class CFRCollector(BaseCollector):
    name = "cfr"
    category = "D"

    DEFAULT_RSS = "https://www.cfr.org/feed"

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        rss_url = self.config.get("rss_url", self.DEFAULT_RSS)

        try:
            feed = feedparser.parse(rss_url)
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
            pass

        return articles
