"""统一 HTTP 抓取：对非 HTML 内容根据 Content-Type 路由到 MinerU"""

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

        # RSS 已有正文摘要，且是 HTML 类型时，raw_content 可能已含足够信息
        if raw.raw_content and raw.content_type == "text/html" and len(raw.raw_content) > 200:
            article.raw_content = raw.raw_content
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
                    break
                except httpx.HTTPError as e:
                    log.warning(f"Fetch attempt {attempt+1}/{self.max_retries} failed for {raw.url}: {e}")
                    if attempt == self.max_retries - 1:
                        raise

        return article
