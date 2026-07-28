"""LLM 单篇分析：只提取交易信号、证据链与政经框架。"""

from __future__ import annotations

import json
import logging
import os
import time

from models.article import Article

log = logging.getLogger("infoCollector")


SYSTEM_PROMPT = """你是一名克制、重证据的跨资产交易研究员。你的任务不是复述全文，也不是给出买卖建议，而是判断这条信息是否会改变市场定价。

分析纪律：
1. 先区分“新事实”“作者观点”和“你的推断”；没有数据支持时降低 confidence_score。
2. 写清事件→预期/现金流/风险溢价→资产价格的传导链，禁止只写“利好/利空”。
3. 判断信息是否可能已被定价；陈旧评论、重复报道、纯学术价值不得给高分。
4. 政治新闻只有在能通过财政、贸易、监管、供给、战争风险或资本流动影响资产时才有交易相关性。
5. 盘感训练要指出跨资产验证信号和证伪条件；不知道就明确写“不确定”。
6. 必须给出最强的反方观点。反方观点不是把结论简单取反，而是指出哪条证据、机制或市场行为可能让主逻辑失效。
7. 为事后复盘选择一个可量化目标。review_symbol 只能从 ^GSPC、^IXIC、^HSI、000001.SS、^TNX、DX-Y.NYB、CNY=X、CL=F、GC=F、HG=F、BTC-USD、^VIX 中选择；没有合适目标时留空并把 expected_direction 写为 observe。
8. trading_relevance、market_impact_score、actionability_score、novelty_score、confidence_score 均为 0-10 整数。

只输出一个 JSON 对象，不要 Markdown；默认不要全文翻译：
{
  "summary": "80字以内，只写新增事实和关键数字",
  "event_key": "可用于合并重复报道的简短标准事件名",
  "event_type": "宏观数据/央行/财政政策/地缘政治/公司催化/市场异动/长期背景/其他",
  "trading_relevance": 8,
  "market_impact_score": 7,
  "actionability_score": 6,
  "novelty_score": 7,
  "confidence_score": 7,
  "quality_reason": "为什么值得或不值得占用今日阅读名额",
  "affected_assets": ["美债", "美元", "黄金"],
  "asset_impact": "分别说明方向；方向不确定时写条件分支",
  "time_horizon": "盘中/1-5天/数周/数月以上",
  "trading_logic": "事件→预期变化→传导机制→资产定价",
  "priced_in": "市场可能已定价什么，真正的预期差是什么",
  "counter_argument": "最强反方观点：什么证据或机制支持相反结论",
  "invalidation": "什么事实或价格行为会推翻上述逻辑",
  "watch_signals": ["最多3个可观察的数据或跨资产价格"],
  "review_metric": "用于复盘的一个指标名称，例如美国10年期收益率",
  "review_symbol": "用于自动检查的行情代码，例如^TNX；没有则留空",
  "expected_direction": "up/down/observe",
  "review_horizon_days": 3,
  "political_economy_lesson": "一条可迁移的政经机制；没有则留空",
  "consensus_gap": "共识与潜在反身性/二阶效应；没有则写不确定",
  "tags": ["最多5个"],
  "concepts": ["最多3个"]
}"""


class Analyzer:
    """LLM 驱动的交易信号分析器。"""

    def __init__(
        self,
        provider: str = "deepseek",
        api_key: str = "",
        model: str = "deepseek-chat",
        max_retries: int = 3,
        include_full_translation: bool = False,
    ):
        self.provider = provider
        self.model = model
        self.max_retries = max_retries
        self.include_full_translation = include_full_translation
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")

        if self.provider == "deepseek":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def analyze(self, article: Article) -> Article:
        if not article.clean_content:
            article.quality_score = 1
            article.quality_reason = "无可用内容"
            return article

        log.info(f"Analyzing [{article.source}] {article.title[:50]}...")
        user_msg = (
            f"标题：{article.title}\n"
            f"来源：{article.source}\n"
            f"发布时间：{article.pub_date or '未知'}\n"
            f"预筛分：{article.prefilter_score}\n\n"
            f"正文：\n{article.clean_content}"
        )
        if self.include_full_translation:
            user_msg += "\n\n额外要求：在 JSON 中增加 translated_content 字段，提供中文全文翻译。"

        for attempt in range(self.max_retries):
            try:
                text = self._call_deepseek(user_msg) if self.provider == "deepseek" else self._call_anthropic(user_msg)
                self._apply_result(article, self._parse_json(text))
                break
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                log.warning(f"LLM response parse error for {article.id}, attempt {attempt + 1}: {exc}")
                if attempt == self.max_retries - 1:
                    article.quality_score = 3
                    article.quality_reason = f"LLM 响应解析失败: {exc}"
            except Exception as exc:
                log.warning(f"LLM API error for {article.id}, attempt {attempt + 1}: {exc}")
                if attempt == self.max_retries - 1:
                    article.quality_score = 3
                    article.quality_reason = f"LLM API 错误: {exc}"
                    break

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        return article

    @classmethod
    def _apply_result(cls, article: Article, result: dict) -> None:
        article.summary = str(result.get("summary", "")).strip()
        article.event_key = str(result.get("event_key", article.title)).strip()
        article.event_type = str(result.get("event_type", "其他")).strip()
        article.trading_relevance = cls._score(result.get("trading_relevance"))
        article.market_impact_score = cls._score(result.get("market_impact_score"))
        article.actionability_score = cls._score(result.get("actionability_score"))
        article.novelty_score = cls._score(result.get("novelty_score"))
        article.confidence_score = cls._score(result.get("confidence_score"))
        article.ranking_score = round(
            article.trading_relevance * 0.35
            + article.market_impact_score * 0.25
            + article.actionability_score * 0.20
            + article.novelty_score * 0.15
            + article.confidence_score * 0.05,
            2,
        )
        # 旧字段继续写入，已有 Obsidian 查询和旧代码不会失效。
        article.quality_score = round(article.ranking_score)
        article.quality_reason = str(result.get("quality_reason", "")).strip()
        article.affected_assets = cls._string_list(result.get("affected_assets"), 8)
        article.asset_impact = str(result.get("asset_impact", "")).strip()
        article.time_horizon = str(result.get("time_horizon", "")).strip()
        article.trading_logic = str(result.get("trading_logic", "")).strip()
        article.priced_in = str(result.get("priced_in", "")).strip()
        article.counter_argument = str(result.get("counter_argument", "")).strip()
        article.invalidation = str(result.get("invalidation", "")).strip()
        article.watch_signals = cls._string_list(result.get("watch_signals"), 3)
        article.review_metric = str(result.get("review_metric", "")).strip()
        article.review_symbol = str(result.get("review_symbol", "")).strip()
        article.expected_direction = cls._direction(result.get("expected_direction"))
        article.review_horizon_days = cls._horizon_days(result.get("review_horizon_days"))
        article.political_economy_lesson = str(result.get("political_economy_lesson", "")).strip()
        article.consensus_gap = str(result.get("consensus_gap", "")).strip()
        article.tags = cls._string_list(result.get("tags"), 5)
        article.concepts = cls._string_list(result.get("concepts"), 3)
        article.knowledge_analysis = article.trading_logic
        if cls._string_list(result.get("translated_content"), 1):
            article.translated_content = str(result.get("translated_content", ""))

    @staticmethod
    def _parse_json(text: str) -> dict:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            # json-repair 专门处理 LLM 常见的漏逗号、非法转义和代码围栏。
            from json_repair import loads as repair_loads
            value = repair_loads(text)
        if not isinstance(value, dict):
            raise ValueError("LLM output is not a JSON object")
        return value

    @staticmethod
    def _score(value) -> int:
        try:
            return max(0, min(10, int(round(float(value)))))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _string_list(value, limit: int) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:limit]

    @staticmethod
    def _direction(value) -> str:
        text = str(value or "").strip().casefold()
        if text in {"up", "上涨", "上行", "走强", "升"}:
            return "up"
        if text in {"down", "下跌", "下行", "走弱", "降"}:
            return "down"
        return "observe"

    @staticmethod
    def _horizon_days(value) -> int:
        try:
            return max(1, min(30, int(round(float(value)))))
        except (TypeError, ValueError):
            return 3

    def _call_deepseek(self, user_msg: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=2200,
            temperature=0.15,
            timeout=60,
        )
        return response.choices[0].message.content

    def _call_anthropic(self, user_msg: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2200,
            temperature=0.15,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        if not response.content:
            raise ValueError("Empty response from LLM")
        return response.content[0].text
