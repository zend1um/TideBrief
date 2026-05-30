"""CNBC RSS 采集器"""

import httpx
import xml.etree.ElementTree as ET
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

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
            for feed_name in enabled_feeds:
                url = self.FEEDS.get(feed_name)
                if not url:
                    continue
                try:
                    resp = await client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    })
                    resp.raise_for_status()
                    root = ET.fromstring(resp.text)
                    for item in root.iter("item"):
                        title = (item.findtext("title") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        description = (item.findtext("description") or "").strip()
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
                    continue

        return articles
