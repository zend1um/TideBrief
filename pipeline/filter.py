"""文章质量过滤：按评分分流"""

import logging
from dataclasses import dataclass, field
from models.article import Article

log = logging.getLogger("infoCollector")


@dataclass
class FilterResult:
    """过滤后的文章分类结果"""
    highlight: list[Article] = field(default_factory=list)   # 评分 >= highlight_threshold，高价值推送
    keep: list[Article] = field(default_factory=list)         # 评分 >= quality_threshold 但不及高亮
    discarded: list[Article] = field(default_factory=list)    # 评分 < quality_threshold，丢弃


class ArticleFilter:
    """按质量评分将文章分为三档"""

    def __init__(self, quality_threshold: int = 5, highlight_threshold: int = 8):
        self.quality_threshold = quality_threshold
        self.highlight_threshold = highlight_threshold

    def apply(self, articles: list[Article]) -> FilterResult:
        result = FilterResult()
        for a in articles:
            if a.quality_score >= self.highlight_threshold:
                result.highlight.append(a)
                log.info(f"HIGHLIGHT [{a.quality_score}] {a.title[:50]}")
            elif a.quality_score >= self.quality_threshold:
                result.keep.append(a)
                log.info(f"KEEP     [{a.quality_score}] {a.title[:50]}")
            else:
                result.discarded.append(a)
                log.info(f"DISCARD  [{a.quality_score}] {a.title[:50]} — {a.quality_reason}")

        log.info(
            f"Filter summary: {len(result.highlight)} highlight, "
            f"{len(result.keep)} keep, {len(result.discarded)} discarded"
        )
        return result
