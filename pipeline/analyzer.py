"""LLM 单篇分析：翻译 + 摘要 + 政经常识解读 + 质量评分"""

import json
import logging
import time
import anthropic
from models.article import Article

log = logging.getLogger("infoCollector")

SYSTEM_PROMPT = """你是一位政治经济学研究助手。你将收到一篇可能是英文或其他语言的文章，你的任务是：

1. 先将文章全文翻译成流畅的中文
2. 然后用 PEER 框架进行结构化分析

分析框架（PEER）：
- Policy/Event: 什么政策或事件？
- Explanation: 为什么会发生？（利益/结构/历史）
- Effect: 会产生什么影响？（短期/长期，直接/间接）
- Response: 各方如何应对？

要求：
1. 翻译要忠实原文，保持专业术语准确
2. 用通俗语言解释涉及的经济政治概念
3. 标注分析中的不确定性（哪些是推理，哪些是事实）
4. 质量评分标准：8-10=涉及政策变化/数据发布/重大事件有中长期分析价值；5-7=有一定信息量但非核心信号；1-4=纯情绪/标题党/重复报道/无实质内容

输出严格 JSON，不要 markdown 代码块，不要前后说明文字：
{
  "translated_content": "文章中文翻译全文",
  "summary": "200字以内中文摘要",
  "knowledge_analysis": "政经常识解读，包括: 为什么重要?涉及哪些经济政治原理?有什么历史参照?",
  "quality_score": 7,
  "quality_reason": "评分理由，一句话",
  "tags": ["货币政策", "央行"],
  "concepts": ["公开市场操作", "逆回购"]
}"""


class Analyzer:
    """LLM 驱动的文章分析器：翻译 + 分析"""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001", max_retries: int = 3):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries

    def analyze(self, article: Article) -> Article:
        """对单篇文章进行 LLM 翻译和分析，填充 Article 的分析字段"""
        if not article.clean_content:
            log.warning(f"No clean content for article {article.id}, skipping analysis")
            article.quality_score = 1
            article.quality_reason = "无可用内容"
            return article

        user_msg = f"标题：{article.title}\n\n正文：\n{article.clean_content}"

        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                )
                if not response.content:
                    raise ValueError("Empty response from LLM")
                text = response.content[0].text
                result = json.loads(text)

                article.translated_content = result.get("translated_content", "")
                article.summary = result.get("summary", "")
                article.knowledge_analysis = result.get("knowledge_analysis", "")
                article.quality_score = int(result.get("quality_score", 5))
                article.quality_reason = result.get("quality_reason", "")
                article.tags = result.get("tags", [])
                article.concepts = result.get("concepts", [])
                break

            except (json.JSONDecodeError, KeyError) as e:
                log.warning(f"LLM response parse error for {article.id}, attempt {attempt+1}: {e}")
                if attempt == self.max_retries - 1:
                    article.quality_score = 3
                    article.quality_reason = f"LLM 响应解析失败: {e}"
            except anthropic.APIError as e:
                log.warning(f"LLM API error for {article.id}, attempt {attempt+1}: {e}")
                if attempt == self.max_retries - 1:
                    article.quality_score = 3
                    article.quality_reason = f"LLM API 错误: {e}"
                    break

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        return article
