"""Collector 抽象基类：每个信息源实现一个 Collector"""

from abc import ABC, abstractmethod
from models.article import RawArticle


class BaseCollector(ABC):
    """信息采集器基类"""

    name: str = ""
    category: str = ""  # A/B/C/D

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def collect(self) -> list[RawArticle]:
        """抓取今日内容，返回原始文章列表。异常由 Runner 统一捕获。"""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(category={self.category})"
