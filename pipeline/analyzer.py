"""LLM 单篇分析：翻译 + 投资逻辑分析 + 质量评分
支持 Anthropic 和 DeepSeek 两种后端"""

import json
import logging
import time
import os
from models.article import Article

log = logging.getLogger("infoCollector")

SYSTEM_PROMPT = """你是一位资深投资研究分析师。你将收到一篇可能是英文或其他语言的文章，你的任务是：

1. 先将文章全文翻译成流畅的中文
2. 然后从投资决策角度进行结构化分析

分析框架：
- 发生了什么？（事件/数据/政策变化，引用原文中的具体数字和时间）
- 投资逻辑链是什么？（从事件到资产价格的传导机制，每一步推理都要写清楚）
- 影响的资产类别？（股票/债券/商品/外汇/加密货币等，具体到行业或品种）
- 时效性判断？（这个逻辑在当下市场环境下是否仍然成立？有没有新的变量改变了历史规律？）

评分标准（投资决策价值）：
8-10：直接影响大类资产定价，有明确的交易逻辑和数据支撑，逻辑链条完整
5-7：间接影响市场，对某些行业或品种有参考价值，但缺乏直接交易信号
1-4：无投资参考价值，纯情绪/标题党/重复报道/逻辑过时

输出严格 JSON，不要 markdown 代码块，不要前后说明文字：
{
  "translated_content": "文章中文翻译全文",
  "summary": "150字以内摘要，突出投资相关要点",
  "knowledge_analysis": "投资逻辑分析：逻辑链（从事件→传导机制→资产影响）+ 引用数据/来源 + 时效性判断（该逻辑在当前市场是否成立）+ 一句话宏观背景",
  "quality_score": 7,
  "quality_reason": "评分理由",
  "tags": ["通胀", "美联储", "利率"],
  "concepts": ["菲利普斯曲线", "实际利率", "终端利率"]
}"""


class Analyzer:
    """LLM 驱动的文章分析器：翻译 + 分析"""

    def __init__(self, provider: str = "deepseek", api_key: str = "",
                 model: str = "deepseek-chat", max_retries: int = 3):
        self.provider = provider
        self.model = model
        self.max_retries = max_retries
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
        user_msg = f"标题：{article.title}\n\n正文：\n{article.clean_content}"

        for attempt in range(self.max_retries):
            try:
                if self.provider == "deepseek":
                    result = self._call_deepseek(user_msg)
                else:
                    result = self._call_anthropic(user_msg)

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
            except Exception as e:
                log.warning(f"LLM API error for {article.id}, attempt {attempt+1}: {e}")
                if attempt == self.max_retries - 1:
                    article.quality_score = 3
                    article.quality_reason = f"LLM API 错误: {e}"
                    break

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        return article

    def _call_deepseek(self, user_msg: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4096,
            temperature=0.3,
            timeout=60,
        )
        text = response.choices[0].message.content
        return json.loads(text)

    def _call_anthropic(self, user_msg: str) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        if not response.content:
            raise ValueError("Empty response from LLM")
        return json.loads(response.content[0].text)
