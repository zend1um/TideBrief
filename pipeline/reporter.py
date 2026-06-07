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

        prompt = """你是一位资深投资研究主管，为投资决策者撰写每日晨报。90%内容聚焦投资逻辑，10%为宏观背景。约5分钟阅读量。

要求：
1. 每一条投资逻辑必须写清楚传导链条（事件→机制→资产影响），引用具体数据和时间
2. 所有reference必须有时效性判断——该逻辑在当前市场环境是否继续有效？有没有新变量？
3. 宏观背景一句话带过即可

请按以下结构输出，严格 JSON 格式：
{
  "overview": "宏观背景一句话（50字内），例如：全球通胀超预期+美联储转向鹰派+地缘风险溢价持续",
  "learning_points": "今日投资要点（8-10条，每条100-150字）：每条必须包含：1)投资逻辑链（事件→传导→影响）2)具体资产/行业影响 3)引用的数据来源和时间 4)该逻辑的时效性判断",
  "themes": "重点关注方向（3-4个主题，每个200-300字）：挑选最值得持续跟踪的投资主题，分析：1)当前状态与历史参照 2)关键催化剂和风险变量 3)跨资产传导路径 4)需要验证的假设"
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
