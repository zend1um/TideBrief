"""每日汇总报告：调用 LLM 生成概览和学习要点"""

import json
import logging
import anthropic
from datetime import datetime
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

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate_overview(self, articles: list[Article]) -> tuple[str, str]:
        """
        输入当天所有文章（含高价值和一般），返回 (概览, 学习要点)。
        如果文章数为 0 或 API 调用失败，返回默认占位文本。
        """
        if not articles:
            return "今日无采集内容", "无"

        # 构建文章摘要列表供 LLM 参考
        article_list = "\n\n---\n\n".join(
            f"标题：{a.title}\n来源：{a.source}\n评分：{a.quality_score}\n摘要：{a.summary}"
            for a in articles
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"今日文章列表：\n\n{article_list}"}],
            )
            if not response.content:
                raise ValueError("Empty response from LLM")
            result = json.loads(response.content[0].text)
            return result.get("overview", "分析暂缺"), result.get("learning_points", "无")
        except (json.JSONDecodeError, anthropic.APIError, IndexError) as e:
            log.error(f"Reporter generation failed: {e}")
            return f"LLM 分析暂不可用（{e}）", "无"
