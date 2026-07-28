"""统一 HTTP 抓取：对非 HTML 内容根据 Content-Type 路由到 MinerU"""

import asyncio
import logging
import httpx
from models.article import RawArticle, Article

log = logging.getLogger("infoCollector")


class Fetcher:
    """将 RawArticle 抓取完整正文，产出 Article"""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch(self, raw: RawArticle) -> Article:
        """抓取单篇文章的完整内容"""
        article = Article(
            id=raw.to_article_id(),
            source=raw.source,
            category=raw.category,
            url=raw.url,
            title=raw.title,
            raw_content=raw.raw_content,
            content_type=raw.content_type,
            pub_date=raw.pub_date,
            crawl_time=raw.crawl_time,
        )

        # RSS 已有正文摘要（>200字符），直接用，不发起 HTTP 请求
        if raw.raw_content and len(raw.raw_content) > 200:
            return article

        # 否则发起 HTTP 请求获取完整正文
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(raw.url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    article.raw_content = resp.text
                    article.content_type = "text/html" if "html" in content_type else content_type
                    return article
                except httpx.HTTPStatusError as e:
                    # 401/403 不会因为你重试就通过，直接放弃
                    if e.response.status_code in (401, 403):
                        return article
                    if attempt == self.max_retries - 1:
                        return article
                    await asyncio.sleep(0.5 * (2 ** attempt))
                except httpx.HTTPError:
                    if attempt == self.max_retries - 1:
                        return article
                    await asyncio.sleep(0.5 * (2 ** attempt))

        return article
