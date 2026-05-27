"""管道集成测试（需 ANTHROPIC_API_KEY 环境变量）"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from models.article import Article, RawArticle
from pipeline.cleaner import Cleaner
from pipeline.filter import ArticleFilter
from pipeline.fetcher import Fetcher
from collectors.base import BaseCollector
from utils.obsidian import ObsidianWriter


class MockCollector(BaseCollector):
    name = "mock"
    category = "A"

    async def collect(self) -> list[RawArticle]:
        return [
            RawArticle(
                source=self.name, category=self.category,
                url="http://test.com/1", title="测试文章1",
                raw_content="<h1>GDP增长5%</h1><p>一季度经济数据发布</p>",
                content_type="text/html",
            ),
            RawArticle(
                source=self.name, category=self.category,
                url="http://test.com/2", title="标题党标题",
                raw_content="震惊！XXX竟然这样做！点击查看...",
                content_type="text/html",
            ),
        ]


class TestCleaner:
    def test_html_to_markdown(self):
        cleaner = Cleaner()
        article = Article(
            id="test", source="mock", category="A",
            url="http://x.com", title="T",
            raw_content="<h1>Title</h1><p>Para</p>",
        )
        result = cleaner.clean(article)
        assert "# Title" in result.clean_content
        assert "Para" in result.clean_content

    def test_truncate_long_content(self):
        cleaner = Cleaner()
        article = Article(
            id="test", source="mock", category="A",
            url="http://x.com", title="T",
            raw_content="x" * 10000,
        )
        result = cleaner.clean(article)
        assert len(result.clean_content) <= 8500  # 8000 + truncate msg

    def test_plain_text_passthrough(self):
        cleaner = Cleaner()
        article = Article(
            id="test", source="mock", category="A",
            url="http://x.com", title="T",
            raw_content="plain text",
            content_type="text/plain",
        )
        result = cleaner.clean(article)
        assert result.clean_content == "plain text"


class TestArticleFilter:
    def test_filter_tiers(self):
        f = ArticleFilter(quality_threshold=5, highlight_threshold=8)
        articles = [
            Article(id="1", source="x", category="A", url="", title="", raw_content="", quality_score=9),
            Article(id="2", source="x", category="A", url="", title="", raw_content="", quality_score=6),
            Article(id="3", source="x", category="A", url="", title="", raw_content="", quality_score=3),
        ]
        result = f.apply(articles)
        assert len(result.highlight) == 1
        assert len(result.keep) == 1
        assert len(result.discarded) == 1
        assert result.highlight[0].id == "1"
        assert result.keep[0].id == "2"
        assert result.discarded[0].id == "3"


class TestObsidianWriter:
    def test_write_article(self, tmp_path):
        writer = ObsidianWriter(str(tmp_path))
        article = Article(
            id="abc123", source="xinhua", category="A",
            url="http://x.com", title="测试",
            raw_content="raw", summary="摘要",
            knowledge_analysis="分析", quality_score=8,
            quality_reason="重要", tags=["经济"], concepts=["GDP"],
            clean_content="正文",
        )
        article.crawl_time = datetime(2026, 5, 27)
        path = writer.write_article(article)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "摘要" in content
        assert "分析" in content
        assert "quality: 8" in content

    def test_write_brief(self, tmp_path):
        writer = ObsidianWriter(str(tmp_path))
        highlights = [
            Article(id="1", source="xinhua", category="A", url="", title="高价值文章",
                    raw_content="", summary="摘要", quality_score=8,
                    quality_reason="", tags=[], concepts=[]),
        ]
        path = writer.write_brief(
            date=datetime(2026, 5, 27),
            highlights=highlights,
            keeps=[],
            discarded=[],
            overview="今日市场稳定",
            learning_points="1. 要点一\n2. 要点二",
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "今日市场稳定" in content
        assert "高价值文章" in content
        assert "要点一" in content
