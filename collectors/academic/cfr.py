"""CFR RSS 采集器 — 外交关系委员会"""

import httpx
import feedparser
from datetime import datetime, timezone
from models.article import RawArticle
from collectors.base import BaseCollector


class CFRCollector(BaseCollector):
    name = "cfr"
    category = "D"

    DEFAULT_URL = "https://www.cfr.org/feed"

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        url = self.config.get("rss_url", self.DEFAULT_URL)

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                })
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
        except Exception:
            return articles

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

        return articles
