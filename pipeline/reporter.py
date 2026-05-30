"""每日汇总报告：调用 LLM 生成概览和学习要点
支持 Anthropic 和 DeepSeek 两种后端"""

import json
import logging
import os
from models.article import Article

log = logging.getLogger("infoCollector")

SYSTEM_PROMPT = """你是一位政治经济学编辑。你需要根据当日收集的文章列表，生成每日简报的两个核心部分：

1. 今日概览（150字内）：今天的核心主题是什么？市场主线是什么？哪些信号值得关注？
2. 今日学习要点（3-5条）：从今天所有文章中提炼出的政经常识要点，每条一句话。

输出严格 JSON：
{
  "overview": "今日概览内容...",
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

    def _call_deepseek(self, article_list: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"今日文章列表：\n\n{article_list}"},
            ],
            max_tokens=512,
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content)

    def _call_anthropic(self, article_list: str) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"今日文章列表：\n\n{article_list}"}],
        )
        if not response.content:
            raise ValueError("Empty response from LLM")
        return json.loads(response.content[0].text)
