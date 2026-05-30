"""Project Syndicate RSS 采集器 — 全球顶尖经济学家评论"""

import httpx
import xml.etree.ElementTree as ET
from models.article import RawArticle
from collectors.base import BaseCollector


class ProjectSyndicateCollector(BaseCollector):
    name = "projectsyndicate"
    category = "B"

    DEFAULT_RSS = "https://www.project-syndicate.org/rss"

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        rss_url = self.config.get("rss_url", self.DEFAULT_RSS)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
            try:
                resp = await client.get(rss_url, headers={
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
                pass

        return articles
