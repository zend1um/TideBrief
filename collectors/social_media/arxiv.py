"""arXiv q-fin Atom API 采集器 — 量化金融论文"""

import httpx
import feedparser
from models.article import RawArticle
from collectors.base import BaseCollector


class ArxivCollector(BaseCollector):
    name = "arxiv"
    category = "D"

    DEFAULT_QUERY = "cat:q-fin.*"
    DEFAULT_MAX = 25

    async def collect(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        query = self.config.get("query", self.DEFAULT_QUERY)
        max_results = self.config.get("max_results", self.DEFAULT_MAX)
        api_url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query={query}&start=0&max_results={max_results}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
                resp = await client.get(api_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                })
                resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("id", entry.get("link", "")).strip()
                summary = entry.get("summary", "").strip()

                if title and link:
                    articles.append(RawArticle(
                        source=self.name,
                        category=self.category,
                        url=link,
                        title=title,
                        raw_content=summary,
                        content_type="text/html",
                    ))
        except Exception:
            pass

        return articles
