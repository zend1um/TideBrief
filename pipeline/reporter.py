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

    def generate_morning_brief(self, articles: list[Article]) -> dict:
        """晨报专用：更详细的分析，约 5 分钟阅读量"""
        if not articles:
            return {"overview": "今日无采集内容", "learning_points": "无", "themes": ""}

        article_list = "\n\n---\n\n".join(
            f"标题：{a.title}\n来源：{a.source}\n评分：{a.quality_score}\n摘要：{a.summary}"
            for a in articles[:40]
        )

        prompt = """你是一位资深政治经济学编辑，需要为读者撰写每日晨报。晨报目标：5分钟阅读完，信息密度高，有深度分析。

请按以下结构输出，严格 JSON 格式：
{
  "overview": "今日宏观主线（300-500字）：综合今天所有信息，提炼出3-5条最重要的主题线，每条说清楚发生了什么、为什么重要、市场如何反应。不是简单列表，而是有逻辑链的叙事",
  "learning_points": "今日政经常识要点（8-10条，每条50-100字）：从今天的文章中提取可以提升读者经济政治素养的知识点。解释概念、机制、历史背景。例如：为什么美联储加息会导致新兴市场资本外流？什么是'相互依存武器化'？",
  "themes": "重点关注方向（3-4个主题，每个150-200字）：挑选今天最值得持续跟踪的主题，分析其演变趋势、关键变量、未来可能的发展路径"
}"""

        try:
            if self.provider == "deepseek":
                result = self._call_deepseek_with_prompt(article_list, prompt, max_tokens=2048)
            else:
                result = self._call_anthropic_with_prompt(article_list, prompt, max_tokens=2048)
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
