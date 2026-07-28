"""Twitter/X RSS 采集器（通过 Nitter/xcancel 桥接）"""

import httpx
import feedparser
from datetime import datetime, timezone
from models.article import RawArticle
from collectors.base import BaseCollector


class TwitterNitterCollector(BaseCollector):
    name = "twitter"
    category = "C"

    # 默认关注的经济/投资类账号
    DEFAULT_HANDLES = [
        "ecb", "federalreserve", "BIS_org", "IMFNews",
        "Lagarde", "POTUS",
    ]

    DEFAULT_MIRROR = "https://nitter.net"

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        mirror = self.config.get("mirror", self.DEFAULT_MIRROR)
        handles = self.config.get("handles", self.DEFAULT_HANDLES)

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for handle in handles:
                rss_url = f"{mirror}/{handle}/rss"
                try:
                    resp = await client.get(rss_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    })
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)
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
                            source=self.name, category=self.category,
                            url=link, title=title, raw_content=description,
                            content_type="text/html", pub_date=pub_date,
                        ))
                except Exception:
                    continue
        return articles
