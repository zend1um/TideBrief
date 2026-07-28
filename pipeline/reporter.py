"""把少量入选信号合成为一份可在几分钟内读完的交易简报。"""

from __future__ import annotations

import json
import logging
import os

from models.article import Article
from pipeline.market import MarketSnapshot

log = logging.getLogger("infoCollector")


SYSTEM_PROMPT = """你是一名跨资产交易台的晨会编辑。输入只有已经筛选过的信号和真实行情快照。

目标是帮助读者形成盘感，而不是制造更多阅读负担：
- 区分新闻事实、市场价格和推断，不得编造输入中没有的价格或数据。
- 判断当天主要定价因子，以及股票/债券/美元/商品之间是否互相验证。
- 不重复逐篇摘要；只提炼跨文章主线、关键分歧与待验证变量。
- 政经部分只讲一条可迁移机制，例如财政约束、联盟激励、产业政策或资本流动。
- 问题应允许第二天用价格或数据复盘，训练“先有假设，再看验证”。
- 全部内容控制在约 800 个中文字符内，不提供个性化买卖建议。

只输出 JSON：
{
  "market_regime": "80字内：增长/通胀/流动性/风险偏好的当前组合",
  "dominant_driver": "今天最重要的一个定价因子及原因",
  "cross_asset_check": "哪些资产在验证或反驳这条主线；行情缺失则明确说明",
  "political_economy": "一条与今日信号相连的可迁移政经机制",
  "calibration_questions": ["最多3个明天可以复盘的问题"],
  "blind_spots": ["最多3个可能推翻主线的变量"]
}"""


class Reporter:
    """每日交易简报生成器。"""

    def __init__(self, provider: str = "deepseek", api_key: str = "", model: str = "deepseek-chat"):
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")

        if self.provider == "deepseek":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate_daily_brief(
        self,
        articles: list[Article],
        market_snapshot: MarketSnapshot | None = None,
    ) -> dict:
        if not articles and not (market_snapshot and market_snapshot.moves):
            return self._empty_brief("今日没有达到阅读门槛的交易信号")

        article_list = "\n\n---\n\n".join(self._format_article(article) for article in articles[:10])
        market_text = market_snapshot.to_prompt() if market_snapshot else "未提供行情数据，禁止猜测价格表现。"
        user_message = f"跨资产行情：\n{market_text}\n\n入选信号：\n{article_list or '无'}"

        try:
            text = self._call_deepseek(user_message) if self.provider == "deepseek" else self._call_anthropic(user_message)
            result = self._parse_json(text)
            default = self._empty_brief()
            default.update({key: value for key, value in result.items() if key in default})
            return default
        except Exception as exc:
            log.error(f"Daily brief generation failed: {exc}")
            return self._empty_brief(f"综合分析暂不可用：{exc}")

    def generate_overview(self, articles: list[Article]) -> tuple[str, str]:
        """兼容旧调用方。"""
        brief = self.generate_daily_brief(articles)
        questions = self._numbered(brief.get("calibration_questions", []))
        return str(brief.get("market_regime", "")), questions

    def generate_morning_brief(self, articles: list[Article]) -> dict:
        """兼容旧调度器；内容仍使用精简模板。"""
        brief = self.generate_daily_brief(articles)
        return {
            **brief,
            "overview": brief.get("market_regime", ""),
            "themes": brief.get("dominant_driver", ""),
            "learning_points": self._numbered(brief.get("calibration_questions", [])),
        }

    @staticmethod
    def _format_article(article: Article) -> str:
        return (
            f"标题：{article.title}\n来源：{article.source}\n事件：{article.event_key}\n"
            f"综合分：{article.ranking_score}\n事实摘要：{article.summary}\n"
            f"传导链：{article.trading_logic}\n资产影响：{article.asset_impact}\n"
            f"已定价/预期差：{article.priced_in}\n反方观点：{article.counter_argument}\n"
            f"证伪：{article.invalidation}\n复盘目标：{article.review_metric} "
            f"{article.expected_direction}，{article.review_horizon_days}天\n"
            f"政经机制：{article.political_economy_lesson}"
        )

    @staticmethod
    def _empty_brief(regime: str = "今日主线不够清晰，宁可保持空白。") -> dict:
        return {
            "market_regime": regime,
            "dominant_driver": "暂无足够证据",
            "cross_asset_check": "暂无足够证据",
            "political_economy": "暂无",
            "calibration_questions": [],
            "blind_spots": [],
        }

    @staticmethod
    def _parse_json(text: str) -> dict:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            from json_repair import loads as repair_loads
            value = repair_loads(text)
        if not isinstance(value, dict):
            raise ValueError("LLM output is not a JSON object")
        return value

    @staticmethod
    def _numbered(value) -> str:
        if isinstance(value, str):
            return value
        if not isinstance(value, list):
            return ""
        return "\n".join(f"{index}. {item}" for index, item in enumerate(value, 1))

    def _call_deepseek(self, user_message: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1600,
            temperature=0.15,
            timeout=60,
        )
        return response.choices[0].message.content

    def _call_anthropic(self, user_message: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1600,
            temperature=0.15,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        if not response.content:
            raise ValueError("Empty response from LLM")
        return response.content[0].text
