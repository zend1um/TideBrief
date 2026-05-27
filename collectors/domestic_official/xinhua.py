"""新华社 RSS 采集器"""

import httpx
from models.article import RawArticle
from collectors.base import BaseCollector


class XinhuaCollector(BaseCollector):
    name = "xinhua"
    category = "A"

    DEFAULT_RSS = "http://www.xinhuanet.com/politics/xhll.xml"

    async def collect(self) -> list[RawArticle]:
        rss_url = self.config.get("rss_url", self.DEFAULT_RSS)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()

        # 简单 XML 解析（用标准库 xml.etree）
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)

        articles: list[RawArticle] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()

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
