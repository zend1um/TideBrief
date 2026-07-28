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
    pub_date: datetime | None = None  # 原文发布时间
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
    pub_date: datetime | None = None  # 原文发布时间
    crawl_time: datetime = field(default_factory=datetime.now)

    # LLM 分析后填充
    translated_content: str = ""  # 翻译后的中文正文
    summary: str = ""
    knowledge_analysis: str = ""
    quality_score: int = 0
    quality_reason: str = ""
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)

    # 交易信号分析（0-10 分）。quality_score 保留用于兼容旧笔记，
    # 新的排序以 ranking_score 为准。
    prefilter_score: float = 0.0
    trading_relevance: int = 0
    market_impact_score: int = 0
    actionability_score: int = 0
    novelty_score: int = 0
    confidence_score: int = 0
    ranking_score: float = 0.0

    event_key: str = ""
    event_type: str = ""
    affected_assets: list[str] = field(default_factory=list)
    asset_impact: str = ""
    time_horizon: str = ""
    trading_logic: str = ""
    priced_in: str = ""
    counter_argument: str = ""
    invalidation: str = ""
    watch_signals: list[str] = field(default_factory=list)
    review_metric: str = ""
    review_symbol: str = ""
    expected_direction: str = "observe"
    review_horizon_days: int = 3
    political_economy_lesson: str = ""
    consensus_gap: str = ""

    def is_analyzed(self) -> bool:
        return self.quality_score > 0 or self.ranking_score > 0
