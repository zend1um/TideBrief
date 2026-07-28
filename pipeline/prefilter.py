"""低成本交易相关性预筛选与事件去重。

在下载全文和调用 LLM 之前，仅根据标题、RSS 摘要、来源和发布时间缩小候选池。
这层有意保持透明、可配置，不把关键词命中伪装成交易结论。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import re

from models.article import RawArticle

try:
    from rapidfuzz import fuzz, utils as fuzz_utils
except ImportError:  # 让项目在依赖尚未安装时仍可给出清晰的降级行为
    fuzz = None
    fuzz_utils = None


DEFAULT_KEYWORD_GROUPS: dict[str, dict] = {
    "macro_data": {
        "weight": 3.0,
        "keywords": [
            "cpi", "pce", "ppi", "gdp", "pmi", "nonfarm", "payroll", "unemployment",
            "inflation", "deflation", "retail sales", "industrial production", "trade balance",
            "通胀", "通缩", "非农", "失业率", "居民消费价格", "生产者价格", "国内生产总值",
            "采购经理", "社会融资", "新增贷款", "零售销售", "工业增加值", "贸易顺差",
        ],
    },
    "central_bank": {
        "weight": 3.5,
        "keywords": [
            "federal reserve", "fed ", "fomc", "ecb", "boj", "pboc", "central bank",
            "rate cut", "rate hike", "interest rate", "yield curve", "quantitative easing",
            "美联储", "联储", "欧洲央行", "日本央行", "人民银行", "央行", "降息", "加息",
            "利率", "收益率曲线", "量化宽松", "降准", "公开市场操作",
        ],
    },
    "policy": {
        "weight": 2.5,
        "keywords": [
            "tariff", "sanction", "export control", "fiscal stimulus", "tax cut", "regulation",
            "antitrust", "budget deficit", "debt ceiling", "capital control", "intervention",
            "关税", "制裁", "出口管制", "财政刺激", "减税", "监管", "反垄断", "赤字",
            "债务上限", "资本管制", "汇率干预", "房地产政策", "产业政策",
        ],
    },
    "corporate_catalyst": {
        "weight": 2.5,
        "keywords": [
            "earnings", "guidance", "profit warning", "default", "bankruptcy", "downgrade",
            "upgrade", "buyback", "merger", "acquisition", "ipo", "supply disruption",
            "财报", "业绩预告", "盈利预警", "违约", "破产", "评级下调", "评级上调",
            "回购", "并购", "收购", "上市", "供应中断", "减产", "扩产",
        ],
    },
    "geopolitics": {
        "weight": 2.5,
        "keywords": [
            "war", "ceasefire", "invasion", "missile", "strait of hormuz", "red sea",
            "taiwan strait", "opec", "trade war", "election", "coup",
            "战争", "停火", "入侵", "导弹", "霍尔木兹", "红海", "台海", "欧佩克",
            "贸易战", "大选", "政变", "地缘冲突",
        ],
    },
    "market_language": {
        "weight": 1.5,
        "keywords": [
            "stocks", "equities", "bonds", "treasury", "yield", "credit spread", "dollar",
            "yuan", "yen", "euro", "oil", "gold", "copper", "bitcoin", "volatility", "vix",
            "股票", "股市", "债券", "国债", "收益率", "信用利差", "美元", "人民币", "日元",
            "欧元", "原油", "黄金", "铜价", "比特币", "波动率", "估值", "风险溢价",
        ],
    },
}

DEFAULT_NEGATIVE_KEYWORDS = [
    "sports", "football", "world cup", "celebrity", "movie", "gaming", "recipe", "travel",
    "programming language", "open source release", "show hn", "文化", "旅游", "体育", "世界杯",
    "明星", "电影", "游戏", "美食", "开源发布", "编程技巧",
]

DEFAULT_SOURCE_WEIGHTS = {
    "bloomberg": 1.5,
    "cnbc": 1.3,
    "marketwatch": 1.2,
    "ftchinese": 1.2,
    "yahoofinance": 1.0,
    "seekingalpha": 0.8,
    "zerohedge": 0.4,
    "twitter": 0.8,
    "peopledaily": 0.2,
    "projectsyndicate": 0.1,
    "nber": -0.5,
    "cfr": -0.3,
    "csis": -0.3,
    "hackernews": -1.5,
    "arxiv": -1.0,
}

CATEGORY_WEIGHTS = {"A": 0.3, "B": 1.0, "C": 0.2, "D": -0.5}


@dataclass
class PrefilterResult:
    selected: list[RawArticle] = field(default_factory=list)
    rejected: list[RawArticle] = field(default_factory=list)
    duplicates: list[RawArticle] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


class SignalPrefilter:
    """透明的启发式预筛选，负责控制 LLM 候选池而非作最终判断。"""

    def __init__(
        self,
        min_score: float = 3.5,
        max_candidates: int = 24,
        max_per_source: int = 5,
        dedupe_threshold: float = 88.0,
        focus_keywords: list[str] | None = None,
        keyword_groups: dict[str, dict] | None = None,
        negative_keywords: list[str] | None = None,
        source_weights: dict[str, float] | None = None,
        category_limits: dict[str, int] | None = None,
    ):
        self.min_score = min_score
        self.max_candidates = max_candidates
        self.max_per_source = max_per_source
        self.dedupe_threshold = dedupe_threshold
        self.focus_keywords = [x.lower().strip() for x in (focus_keywords or []) if x.strip()]
        self.keyword_groups = keyword_groups or DEFAULT_KEYWORD_GROUPS
        self.negative_keywords = negative_keywords or DEFAULT_NEGATIVE_KEYWORDS
        self.source_weights = {**DEFAULT_SOURCE_WEIGHTS, **(source_weights or {})}
        self.category_limits = category_limits or {"A": 5, "B": 18, "C": 4, "D": 2}

    def apply(self, articles: list[RawArticle]) -> PrefilterResult:
        result = PrefilterResult()
        scored = sorted(
            ((self.score(article), article) for article in articles),
            key=lambda item: (item[0], self._pub_timestamp(item[1].pub_date)),
            reverse=True,
        )

        source_counts: defaultdict[str, int] = defaultdict(int)
        category_counts: defaultdict[str, int] = defaultdict(int)
        selected_titles: list[str] = []
        selected_urls: set[str] = set()

        for score, article in scored:
            result.scores[article.to_article_id()] = score
            if score < self.min_score:
                result.rejected.append(article)
                continue
            if article.url in selected_urls or self._is_duplicate(article.title, selected_titles):
                result.duplicates.append(article)
                continue
            if source_counts[article.source] >= self.max_per_source:
                result.rejected.append(article)
                continue
            category_limit = self.category_limits.get(article.category, self.max_candidates)
            if category_counts[article.category] >= category_limit:
                result.rejected.append(article)
                continue
            if len(result.selected) >= self.max_candidates:
                result.rejected.append(article)
                continue

            result.selected.append(article)
            selected_titles.append(article.title)
            selected_urls.add(article.url)
            source_counts[article.source] += 1
            category_counts[article.category] += 1

        return result

    def score(self, article: RawArticle) -> float:
        text = self._normalise_text(f"{article.title} {article.raw_content[:1200]}")
        score = self.source_weights.get(article.source, 0.0)
        score += CATEGORY_WEIGHTS.get(article.category, 0.0)
        positive_groups = 0

        for group in self.keyword_groups.values():
            keywords = group.get("keywords", [])
            if any(self._contains(text, keyword) for keyword in keywords):
                score += float(group.get("weight", 0))
                positive_groups += 1

        if self.focus_keywords and any(self._contains(text, keyword) for keyword in self.focus_keywords):
            score += 5.0
            positive_groups += 1

        if any(self._contains(text, keyword) for keyword in self.negative_keywords):
            score -= 4.0 if positive_groups == 0 else 2.0

        # 具体数字往往意味着数据发布、价格变化或政策幅度，但不能单独构成入选理由。
        if positive_groups and re.search(r"(?:\d+(?:\.\d+)?%|\$\s?\d+|\d+\s?(?:bp|bps|基点|亿|万亿))", text):
            score += 0.8

        if article.pub_date:
            pub = article.pub_date
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - pub.astimezone(timezone.utc)).total_seconds() / 86400
            if age_days <= 2:
                score += 0.7
            elif age_days > 14:
                score -= 3.0

        return round(score, 2)

    def _is_duplicate(self, title: str, selected_titles: list[str]) -> bool:
        if not title or not selected_titles:
            return False
        if fuzz is None:
            from difflib import SequenceMatcher
            normalised = self._normalise_text(title)
            return any(
                SequenceMatcher(None, normalised, self._normalise_text(other)).ratio() * 100
                >= self.dedupe_threshold
                for other in selected_titles
            )
        return any(
            max(
                fuzz.WRatio(title, other, processor=fuzz_utils.default_process),
                fuzz.token_set_ratio(title, other, processor=fuzz_utils.default_process),
            ) >= self.dedupe_threshold
            for other in selected_titles
        )

    @staticmethod
    def _normalise_text(value: str) -> str:
        value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
        return re.sub(r"\s+", " ", value).lower().strip()

    @staticmethod
    def _pub_timestamp(value: datetime | None) -> float:
        if value is None:
            return 0.0
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()

    @staticmethod
    def _contains(text: str, keyword: str) -> bool:
        keyword = keyword.lower().strip()
        if not keyword:
            return False
        if keyword.isascii() and len(keyword) <= 4 and keyword.isalnum():
            return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
        return keyword in text
