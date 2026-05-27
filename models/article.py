from dataclasses import dataclass, field
from datetime import datetime
import hashlib


@dataclass
class RawArticle:
    """Collector 产出，未经清洗的原始文章"""
    source: str
    category: str          # A/B/C/D
    url: str
    title: str
    raw_content: str       # 原始 HTML 或 API 返回文本
    content_type: str = "text/html"  # text/html, application/pdf, image/*
    crawl_time: datetime = field(default_factory=datetime.now)

    def to_article_id(self) -> str:
        raw = f"{self.source}:{self.url}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]


@dataclass
class Article:
    """管道流通的统一数据结构"""
    id: str
    source: str
    category: str
    url: str
    title: str
    raw_content: str
    clean_content: str = ""
    content_type: str = "text/html"
    crawl_time: datetime = field(default_factory=datetime.now)

    # LLM 分析后填充
    summary: str = ""
    knowledge_analysis: str = ""
    quality_score: int = 0
    quality_reason: str = ""
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)

    def is_analyzed(self) -> bool:
        return self.quality_score > 0
