"""每日汇总报告：调用 LLM 生成概览和学习要点
支持 Anthropic 和 DeepSeek 两种后端"""

import json
import logging
import os
from models.article import Article

log = logging.getLogger("infoCollector")

SYSTEM_PROMPT = """你是一位投资研究编辑。根据当日文章列表，生成简报：

1. 今日概览（一句话，50字内）：宏观背景定调
2. 今日学习要点（3-5条投资要点，每条一句话，含具体标的/方向）

输出严格 JSON：
{
  "overview": "一句话宏观背景...",
  "learning_points": "1. 要点一\\n2. 要点二\\n3. 要点三"
}"""


class Reporter:
    """每日汇总报告生成器"""

    def __init__(self, provider: str = "deepseek", api_key: str = "",
                 model: str = "deepseek-chat"):
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")

        if self.provider == "deepseek":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate_overview(self, articles: list[Article]) -> tuple[str, str]:
        if not articles:
            return "今日无采集内容", "无"

        article_list = "\n\n---\n\n".join(
            f"标题：{a.title}\n来源：{a.source}\n评分：{a.quality_score}\n摘要：{a.summary}"
            for a in articles
        )

        try:
            if self.provider == "deepseek":
                result = self._call_deepseek(article_list)
            else:
                result = self._call_anthropic(article_list)
            return result.get("overview", "分析暂缺"), result.get("learning_points", "无")
        except Exception as e:
            log.error(f"Reporter generation failed: {e}")
            return f"LLM 分析暂不可用（{e}）", "无"

    def generate_morning_brief(self, articles: list[Article]) -> dict:
        """晨报专用：更详细的分析，约 5 分钟阅读量"""
        if not articles:
            return {"overview": "今日无采集内容", "learning_points": "无", "themes": ""}

        article_list = "\n\n---\n\n".join(
            f"标题：{a.title}\n来源：{a.source}\n评分：{a.quality_score}\n摘要：{a.summary}"
            for a in articles[:40]
        )

        prompt = """你是资深投资研究主管。基于今日文章写晨报。约5分钟阅读量。90%投资逻辑，10%宏观背景。

输出严格JSON：
{
  "overview": "一句话宏观背景（50字）",
  "themes": "重点关注方向（3-4个，每个150-200字，纯文本用空行分隔）。每个主题说明：当前状态、关键催化剂、跨资产影响、需验证假设",
  "learning_points": "今日投资要点（8-10条，纯文本用换行分隔）。每条包含：投资逻辑链（事件→传导→资产影响）、引用数据/时间、时效性判断"
}"""

        try:
            if self.provider == "deepseek":
                result = self._call_deepseek_with_prompt(article_list, prompt, max_tokens=4096)
            else:
                result = self._call_anthropic_with_prompt(article_list, prompt, max_tokens=4096)
            return result
        except Exception as e:
            log.error(f"Morning brief generation failed: {e}")
            return {"overview": f"生成失败: {e}", "learning_points": "无", "themes": ""}

    def _call_deepseek(self, article_list: str) -> dict:
        return self._call_deepseek_with_prompt(article_list, SYSTEM_PROMPT, 512)

    def _call_deepseek_with_prompt(self, article_list: str, system_prompt: str, max_tokens: int) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"今日文章列表：\n\n{article_list}"},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            timeout=60,
        )
        return json.loads(response.choices[0].message.content)

    def _call_anthropic_with_prompt(self, article_list: str, system_prompt: str, max_tokens: int) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": f"今日文章列表：\n\n{article_list}"}],
        )
        if not response.content:
            raise ValueError("Empty response from LLM")
        return json.loads(response.content[0].text)

    def _call_anthropic(self, article_list: str) -> dict:
        return self._call_anthropic_with_prompt(article_list, SYSTEM_PROMPT, 512)
