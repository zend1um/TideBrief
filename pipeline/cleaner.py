"""HTML/文本 → Markdown 清洗"""

import logging
from markdownify import markdownify as md
from models.article import Article

log = logging.getLogger("infoCollector")


class Cleaner:
    """将 Article.raw_content 清洗为 Markdown 放入 clean_content"""

    def clean(self, article: Article) -> Article:
        content = article.raw_content

        if article.content_type.startswith("text/html"):
            article.clean_content = md(content, heading_style="ATX", strip=["script", "style", "nav", "footer"])
        elif article.content_type.startswith("text/"):
            article.clean_content = content  # 纯文本直接保留
        # PDF/图片 → MinerU 适配器处理（见 mineru_adapter.py）
        # 当前对非 text 类型保留原始内容标记，后续路由到 MinerU

        # 截断过长内容（保留前 8000 字符给 LLM）
        if len(article.clean_content) > 8000:
            article.clean_content = article.clean_content[:8000] + "\n\n[...内容过长已截断]"

        return article
