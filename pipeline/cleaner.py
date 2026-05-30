"""内容清洗：MarkItDown 主转换 + MinerU 备选"""

import logging
import tempfile
import os
from pathlib import Path
from markitdown import MarkItDown
from models.article import Article

log = logging.getLogger("infoCollector")


class Cleaner:
    """将 Article.raw_content 清洗为 Markdown"""

    def __init__(self):
        self.md = MarkItDown()

    def clean(self, article: Article) -> Article:
        content = article.raw_content

        if article.content_type.startswith("text/html"):
            article.clean_content = self._html_to_md(content)
        elif article.content_type.startswith("text/"):
            article.clean_content = content
        elif article.content_type.startswith("application/pdf") or article.content_type.startswith("image/"):
            # PDF/图片：MarkItDown 尝试，失败则标记需要 MinerU
            try:
                article.clean_content = self._html_to_md(content)
            except Exception:
                article.clean_content = ""
                log.info(f"MarkItDown failed for {article.id}, needs MinerU")
        elif article.content_type.startswith("application/"):
            # DOCX/PPTX/XLSX 等：MarkItDown 原生支持
            article.clean_content = self._html_to_md(content)

        if article.clean_content and len(article.clean_content) > 8000:
            article.clean_content = article.clean_content[:8000] + "\n\n[...内容过长已截断]"

        return article

    def _html_to_md(self, content: str) -> str:
        """通过 MarkItDown 将 HTML/文档内容转为 Markdown"""
        suffix = ".html"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w", encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name

        try:
            result = self.md.convert(tmp_path)
            return result.text_content.strip()
        finally:
            os.unlink(tmp_path)
