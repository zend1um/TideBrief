"""arXiv q-fin Atom API 采集器 — 量化金融论文"""

import httpx
import xml.etree.ElementTree as ET
from models.article import RawArticle
from collectors.base import BaseCollector

ATOM_NS = "http://www.w3.org/2005/Atom"


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

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
            try:
                resp = await client.get(api_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                })
                resp.raise_for_status()
                root = ET.fromstring(resp.text)

                for entry in root.findall(f"{{{ATOM_NS}}}entry"):
                    title = (entry.findtext(f"{{{ATOM_NS}}}title") or "").strip()
                    link_el = entry.find(f"{{{ATOM_NS}}}id")
                    link = link_el.text.strip() if link_el is not None and link_el.text else ""
                    summary = (entry.findtext(f"{{{ATOM_NS}}}summary") or "").strip()

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
