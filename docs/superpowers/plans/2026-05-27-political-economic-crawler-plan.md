# 政治经济信息采集工具 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建每日自动采集政治经济信息、LLM 分析标注后存入 Obsidian Vault 并生成汇总报告的管道系统。

**Architecture:** 插件式 Collector 并行采集 → 统一管道串行处理（清洗 → LLM 分析 → 过滤 → 写入 Vault → 生成报告）。APScheduler 调度，httpx 异步抓取，Anthropic API 驱动内容分析。

**Tech Stack:** Python 3.11+, httpx, markdownify, APScheduler, anthropic sdk, PyYAML, python-frontmatter

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `E:/proj/infoCollector/requirements.txt`
- Create: `E:/proj/infoCollector/config.yaml`
- Create: `E:/proj/infoCollector/.gitignore`

- [ ] **Step 1: 创建 requirements.txt**

```
httpx>=0.27.0
markdownify>=1.0.0
apscheduler>=3.10.0
anthropic>=0.40.0
pyyaml>=6.0
python-frontmatter>=1.1.0
```

- [ ] **Step 2: 创建 config.yaml**

```yaml
vault:
  path: "E:/obsidian_vault/政治经济知识库"

schedule:
  time: "05:00"
  timezone: "Asia/Shanghai"

llm:
  provider: "anthropic"
  fast_model: "claude-haiku-4-5-20251001"
  smart_model: "claude-sonnet-4-6"

filter:
  quality_threshold: 5
  highlight_threshold: 8

collectors:
  domestic_official:
    xinhua:
      enabled: true
      rss_url: "http://www.xinhuanet.com/politics/xhll.xml"
    state_council:
      enabled: false
      url: "https://www.gov.cn/"
    pbc:
      enabled: false
      url: "http://www.pbc.gov.cn/"
  international_finance: {}
  academic: {}
  social_media: {}

output:
  daily_brief: true
  single_articles: true
  topic_aggregation:
    enabled: true
    min_articles: 5
```

- [ ] **Step 3: 创建 .gitignore**

```
__pycache__/
*.pyc
logs/
.env
.venv/
```

- [ ] **Step 4: 创建目录结构并虚拟环境安装依赖**

Run: `cd E:/proj/infoCollector && python -m venv .venv && source .venv/Scripts/activate && mkdir -p pipeline collectors/domestic_official collectors/international_finance collectors/academic collectors/social_media models utils logs && pip install -r requirements.txt`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: project scaffold with dependencies and config"
```

---

### Task 2: 数据模型

**Files:**
- Create: `E:/proj/infoCollector/models/__init__.py`
- Create: `E:/proj/infoCollector/models/article.py`

- [ ] **Step 1: 创建模型文件**

```python
from dataclasses import dataclass, field
from datetime import datetime
import hashlib


@dataclass
class RawArticle:
    """Collector 产出，未经清洗的原始文章"""
    source: str
    category: str          # A/B/C/D
    url: str
    title: str
    raw_content: str       # 原始 HTML 或 API 返回文本
    content_type: str = "text/html"  # text/html, application/pdf, image/*
    crawl_time: datetime = field(default_factory=datetime.now)

    def to_article_id(self) -> str:
        raw = f"{self.source}:{self.url}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]


@dataclass
class Article:
    """管道流通的统一数据结构"""
    id: str
    source: str
    category: str
    url: str
    title: str
    raw_content: str
    clean_content: str = ""
    content_type: str = "text/html"
    crawl_time: datetime = field(default_factory=datetime.now)

    # LLM 分析后填充
    summary: str = ""
    knowledge_analysis: str = ""
    quality_score: int = 0
    quality_reason: str = ""
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)

    def is_analyzed(self) -> bool:
        return self.quality_score > 0
```

- [ ] **Step 2: 创建 models/__init__.py**

```python
from .article import Article, RawArticle
```

- [ ] **Step 3: 验证导入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from models import Article, RawArticle; a = RawArticle('test','A','http://x.com','T','body'); print(a.to_article_id())"`

- [ ] **Step 4: Commit**

```bash
git add models/
git commit -m "feat: add Article and RawArticle data models"
```

---

### Task 3: 日志工具

**Files:**
- Create: `E:/proj/infoCollector/utils/__init__.py`
- Create: `E:/proj/infoCollector/utils/logger.py`

- [ ] **Step 1: 创建 utils/__init__.py**

```python
from .logger import setup_logger
from .obsidian import ObsidianWriter
```

- [ ] **Step 2: 创建 utils/logger.py**

```python
"""统一日志：控制台 + 按日切割的文件日志"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(name: str = "infoCollector", log_dir: str = "logs") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件（按日期）
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        Path(log_dir) / f"{today}.log", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
```

- [ ] **Step 3: 验证日志写入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from utils.logger import setup_logger; log = setup_logger(); log.info('test')" && cat logs/$(date +%Y-%m-%d).log`

- [ ] **Step 4: Commit**

```bash
git add utils/__init__.py utils/logger.py
git commit -m "feat: add logging utility with daily rotation"
```

---

### Task 4: Collector 基类

**Files:**
- Create: `E:/proj/infoCollector/collectors/__init__.py`
- Create: `E:/proj/infoCollector/collectors/base.py`

- [ ] **Step 1: 创建 collectors/__init__.py**

```python
from .base import BaseCollector
```

- [ ] **Step 2: 创建 collectors/base.py**

```python
"""Collector 抽象基类：每个信息源实现一个 Collector"""

from abc import ABC, abstractmethod
from models.article import RawArticle


class BaseCollector(ABC):
    """信息采集器基类"""

    name: str = ""
    category: str = ""  # A/B/C/D

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def collect(self) -> list[RawArticle]:
        """抓取今日内容，返回原始文章列表。异常由 Runner 统一捕获。"""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(category={self.category})"
```

- [ ] **Step 3: 验证基类抽象约束**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from collectors.base import BaseCollector; print(BaseCollector.__abstractmethods__)"`

Expected: `frozenset({'collect'})`

- [ ] **Step 4: Commit**

```bash
git add collectors/__init__.py collectors/base.py
git commit -m "feat: add BaseCollector abstract interface"
```

---

### Task 5: 新华社 Collector（第一个具体采集器）

**Files:**
- Create: `E:/proj/infoCollector/collectors/domestic_official/__init__.py`
- Create: `E:/proj/infoCollector/collectors/domestic_official/xinhua.py`

- [ ] **Step 1: 创建 domestic_official/__init__.py**

```python
from .xinhua import XinhuaCollector
```

- [ ] **Step 2: 创建 domestic_official/xinhua.py**

```python
"""新华社 RSS 采集器"""

import httpx
from models.article import RawArticle
from collectors.base import BaseCollector


class XinhuaCollector(BaseCollector):
    name = "xinhua"
    category = "A"

    DEFAULT_RSS = "http://www.xinhuanet.com/politics/xhll.xml"

    async def collect(self) -> list[RawArticle]:
        rss_url = self.config.get("rss_url", self.DEFAULT_RSS)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()

        # 简单 XML 解析（用标准库 xml.etree）
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)

        articles: list[RawArticle] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()

            if not title or not link:
                continue

            articles.append(RawArticle(
                source=self.name,
                category=self.category,
                url=link,
                title=title,
                raw_content=description,
                content_type="text/html",
            ))

        return articles
```

- [ ] **Step 3: 验证采集器实例化和导入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from collectors.domestic_official.xinhua import XinhuaCollector; c = XinhuaCollector(); print(c.name, c.category)"`

Expected: `xinhua A`

- [ ] **Step 4: Commit**

```bash
git add collectors/domestic_official/
git commit -m "feat: add Xinhua RSS collector"
```

---

### Task 6: HTTP 抓取器（Fetcher）

**Files:**
- Create: `E:/proj/infoCollector/pipeline/__init__.py`
- Create: `E:/proj/infoCollector/pipeline/fetcher.py`

- [ ] **Step 1: 创建 pipeline/__init__.py**

```python
from .fetcher import Fetcher
from .cleaner import Cleaner
from .analyzer import Analyzer
from .filter import ArticleFilter
from .writer import VaultWriter
from .reporter import Reporter
from .runner import Runner
```

- [ ] **Step 2: 创建 pipeline/fetcher.py**

```python
"""统一 HTTP 抓取：对非 HTML 内容根据 Content-Type 路由到 MinerU"""

import logging
import httpx
from models.article import RawArticle, Article

log = logging.getLogger("infoCollector")


class Fetcher:
    """将 RawArticle 抓取完整正文，产出 Article"""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch(self, raw: RawArticle) -> Article:
        """抓取单篇文章的完整内容"""
        article = Article(
            id=raw.to_article_id(),
            source=raw.source,
            category=raw.category,
            url=raw.url,
            title=raw.title,
            raw_content=raw.raw_content,
            content_type=raw.content_type,
            crawl_time=raw.crawl_time,
        )

        # RSS 已有正文摘要，且是 HTML 类型时，raw_content 可能已含足够信息
        if raw.raw_content and raw.content_type == "text/html" and len(raw.raw_content) > 200:
            article.raw_content = raw.raw_content
            return article

        # 否则发起 HTTP 请求获取完整正文
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(raw.url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    article.raw_content = resp.text
                    article.content_type = "text/html" if "html" in content_type else content_type
                    break
                except httpx.HTTPError as e:
                    log.warning(f"Fetch attempt {attempt+1}/{self.max_retries} failed for {raw.url}: {e}")
                    if attempt == self.max_retries - 1:
                        raise

        return article
```

- [ ] **Step 3: 验证导入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from pipeline.fetcher import Fetcher; print('ok')"`

- [ ] **Step 4: Commit**

```bash
git add pipeline/__init__.py pipeline/fetcher.py
git commit -m "feat: add HTTP fetcher with retry and content-type handling"
```

---

### Task 7: 内容清洗器（Cleaner + MinerU 适配器桩）

**Files:**
- Create: `E:/proj/infoCollector/pipeline/cleaner.py`
- Create: `E:/proj/infoCollector/pipeline/mineru_adapter.py`

- [ ] **Step 1: 创建 pipeline/cleaner.py**

```python
"""HTML/文本 → Markdown 清洗"""

import logging
from markdownify import markdownify as md
from models.article import Article

log = logging.getLogger("infoCollector")


class Cleaner:
    """将 Article.raw_content 清洗为 Markdown 放入 clean_content"""

    def clean(self, article: Article) -> Article:
        content = article.raw_content

        if article.content_type.startswith("text/html"):
            article.clean_content = md(content, heading_style="ATX", strip=["script", "style", "nav", "footer"])
        elif article.content_type.startswith("text/"):
            article.clean_content = content  # 纯文本直接保留
        # PDF/图片 → MinerU 适配器处理（见 mineru_adapter.py）
        # 当前对非 text 类型保留原始内容标记，后续路由到 MinerU

        # 截断过长内容（保留前 8000 字符给 LLM）
        if len(article.clean_content) > 8000:
            article.clean_content = article.clean_content[:8000] + "\n\n[...内容过长已截断]"

        return article
```

- [ ] **Step 2: 创建 pipeline/mineru_adapter.py**

```python
"""MinerU 转换适配器（预留接口）

当文章 content_type 为 application/pdf 或 image/* 时，调用 MinerU 转为 Markdown。
MinerU 配置完成后，取消下方注释并填入实际路径。
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from models.article import Article

log = logging.getLogger("infoCollector")


class MinerUAdapter:
    """MinerU PDF/图片 → Markdown 转换器（预留）"""

    def __init__(self, mineru_path: str = "mineru"):
        self.mineru_path = mineru_path

    def supports(self, content_type: str) -> bool:
        return content_type.startswith("application/pdf") or content_type.startswith("image/")

    def convert(self, article: Article) -> Article:
        """将非文本内容通过 MinerU 转为 Markdown"""
        if not self.supports(article.content_type):
            return article

        # 将原始内容写入临时文件
        suffix = ".pdf" if "pdf" in article.content_type else ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            # 注意：raw_content 在此场景下是 bytes 或下载的文件路径
            # 此处为预留接口，需根据实际 MinerU 调用方式调整
            tmp_path = Path(f.name)

        try:
            result = subprocess.run(
                [self.mineru_path, str(tmp_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                article.clean_content = result.stdout
            else:
                log.error(f"MinerU conversion failed: {result.stderr}")
        except FileNotFoundError:
            log.warning("MinerU not installed — skipping conversion")
        except Exception as e:
            log.error(f"MinerU error: {e}")
        finally:
            tmp_path.unlink(missing_ok=True)

        return article
```

- [ ] **Step 3: 验证 Cleaner 对 HTML 清洗**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from pipeline.cleaner import Cleaner; from models.article import Article; a = Article(id='t',source='x',category='A',url='http://x.com',title='T',raw_content='<h1>Hello</h1><p>world</p>'); c = Cleaner(); c.clean(a); print(a.clean_content)"`

- [ ] **Step 4: Commit**

```bash
git add pipeline/cleaner.py pipeline/mineru_adapter.py
git commit -m "feat: add HTML cleaner and MinerU adapter stub"
```

---

### Task 8: LLM 分析器（Analyzer）

**Files:**
- Create: `E:/proj/infoCollector/pipeline/analyzer.py`

- [ ] **Step 1: 创建 pipeline/analyzer.py**

```python
"""LLM 单篇分析：摘要 + 政经常识解读 + 质量评分"""

import json
import logging
import anthropic
from models.article import Article

log = logging.getLogger("infoCollector")

SYSTEM_PROMPT = """你是一位政治经济学研究助手。你的任务是对新闻文章进行结构化分析，帮助读者提升政经常识素养。

分析框架（PEER）：
- Policy/Event: 什么政策或事件？
- Explanation: 为什么会发生？（利益/结构/历史）
- Effect: 会产生什么影响？（短期/长期，直接/间接）
- Response: 各方如何应对？

要求：
1. 用通俗语言解释涉及的经济政治概念
2. 标注分析中的不确定性（哪些是推理，哪些是事实）
3. 质量评分标准：8-10=涉及政策变化/数据发布/重大事件有中长期分析价值；5-7=有一定信息量但非核心信号；1-4=纯情绪/标题党/重复报道/无实质内容

输出严格 JSON，不要 markdown 代码块，不要前后说明文字：
{
  "summary": "200字以内中文摘要",
  "knowledge_analysis": "政经常识解读，包括: 为什么重要?涉及哪些经济政治原理?有什么历史参照?",
  "quality_score": 7,
  "quality_reason": "评分理由，一句话",
  "tags": ["货币政策", "央行"],
  "concepts": ["公开市场操作", "逆回购"]
}"""


class Analyzer:
    """LLM 驱动的文章分析器"""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001", max_retries: int = 3):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries

    def analyze(self, article: Article) -> Article:
        """对单篇文章进行 LLM 分析，填充 Article 的分析字段"""
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
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                )
                text = response.content[0].text
                result = json.loads(text)

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

        return article
```

- [ ] **Step 2: 验证导入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from pipeline.analyzer import Analyzer, SYSTEM_PROMPT; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add pipeline/analyzer.py
git commit -m "feat: add LLM analyzer with PEER framework prompt"
```

---

### Task 9: 质量过滤器（Filter）

**Files:**
- Create: `E:/proj/infoCollector/pipeline/filter.py`

- [ ] **Step 1: 创建 pipeline/filter.py**

```python
"""文章质量过滤：按评分分流"""

import logging
from dataclasses import dataclass, field
from models.article import Article

log = logging.getLogger("infoCollector")


@dataclass
class FilterResult:
    """过滤后的文章分类结果"""
    highlight: list[Article] = field(default_factory=list)   # 评分 >= highlight_threshold，高价值推送
    keep: list[Article] = field(default_factory=list)         # 评分 >= quality_threshold 但不及高亮
    discarded: list[Article] = field(default_factory=list)    # 评分 < quality_threshold，丢弃


class ArticleFilter:
    """按质量评分将文章分为三档"""

    def __init__(self, quality_threshold: int = 5, highlight_threshold: int = 8):
        self.quality_threshold = quality_threshold
        self.highlight_threshold = highlight_threshold

    def apply(self, articles: list[Article]) -> FilterResult:
        result = FilterResult()
        for a in articles:
            if a.quality_score >= self.highlight_threshold:
                result.highlight.append(a)
                log.info(f"HIGHLIGHT [{a.quality_score}] {a.title[:50]}")
            elif a.quality_score >= self.quality_threshold:
                result.keep.append(a)
                log.info(f"KEEP     [{a.quality_score}] {a.title[:50]}")
            else:
                result.discarded.append(a)
                log.info(f"DISCARD  [{a.quality_score}] {a.title[:50]} — {a.quality_reason}")

        log.info(
            f"Filter summary: {len(result.highlight)} highlight, "
            f"{len(result.keep)} keep, {len(result.discarded)} discarded"
        )
        return result
```

- [ ] **Step 2: 验证过滤逻辑**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from pipeline.filter import ArticleFilter; from models.article import Article; f = ArticleFilter(5, 8); articles = [Article(id='1',source='x',category='A',url='',title='',raw_content='',quality_score=9), Article(id='2',source='x',category='A',url='',title='',raw_content='',quality_score=6), Article(id='3',source='x',category='A',url='',title='',raw_content='',quality_score=3)]; r = f.apply(articles); print(len(r.highlight), len(r.keep), len(r.discarded))"`

Expected: `1 1 1`

- [ ] **Step 3: Commit**

```bash
git add pipeline/filter.py
git commit -m "feat: add quality-based article filter"
```

---

### Task 10: Obsidian Vault 写入器（Writer）

**Files:**
- Create: `E:/proj/infoCollector/utils/obsidian.py`

- [ ] **Step 1: 创建 utils/obsidian.py**

```python
"""Obsidian Vault 格式工具：生成 frontmatter + wikilink 的 Markdown 笔记"""

import logging
from pathlib import Path
from datetime import datetime
import frontmatter
from models.article import Article

log = logging.getLogger("infoCollector")


class ObsidianWriter:
    """将 Article 写入 Obsidian Vault"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.articles_dir = self.vault_path / "信息条目"
        self.brief_dir = self.vault_path / "每日简报"
        self.topic_dir = self.vault_path / "主题追踪"

    def write_article(self, article: Article) -> Path:
        """写入单篇信息笔记 → 信息条目/YYYY-MM-DD/来源-id.md"""
        date_str = article.crawl_time.strftime("%Y-%m-%d")
        out_dir = self.articles_dir / date_str
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{article.source}-{article.id}.md"
        filepath = out_dir / filename

        # 构建 wikilink 回链到知识框架笔记
        concept_links = "\n".join(
            f"- [[{concept}]]" for concept in article.concepts
        )
        tag_links = " ".join(f"#{tag}" for tag in article.tags)

        post = frontmatter.Post(
            (
                f"> [!summary] 原文摘要\n"
                f"> {article.summary}\n\n"
                f"> [!knowledge] 政经常识解读\n"
                f"> {article.knowledge_analysis}\n\n"
                f"> [!impact] 影响分析\n"
                f"> 待补充...\n\n"
                f"## 🔗 相关概念\n"
                f"{concept_links}\n\n"
                f"## 📎 相关笔记\n"
                f"- [[../../每日简报/{date_str}|当日简报]]\n"
                f"- [[../../中国政经]] [[../../宏观经济学]]\n"
            ),
            date=date_str,
            source=article.source,
            url=article.url,
            quality=article.quality_score,
            quality_reason=article.quality_reason,
            tags=article.tags,
            category=article.category,
            concepts=article.concepts,
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Article written: {filepath}")
        return filepath

    def write_brief(self, date: datetime, highlights: list[Article], 
                    keeps: list[Article], discarded: list[Article],
                    overview: str, learning_points: str) -> Path:
        """写入每日汇总笔记 → 每日简报/YYYY-MM-DD.md"""
        self.brief_dir.mkdir(parents=True, exist_ok=True)
        date_str = date.strftime("%Y-%m-%d")
        filepath = self.brief_dir / f"{date_str}.md"

        highlight_rows = "\n".join(
            f"| {i+1} | {a.quality_score} | [[../信息条目/{date_str}/{a.source}-{a.id}\|{a.title}]] | {a.source} |"
            for i, a in enumerate(highlights)
        )

        keep_rows = "\n".join(
            f"| {i+1} | {a.quality_score} | [[../信息条目/{date_str}/{a.source}-{a.id}\|{a.title}]] | {a.source} |"
            for i, a in enumerate(keeps)
        )

        discarded_rows = "\n".join(
            f"| {a.quality_score} | {a.title[:40]} | {a.quality_reason} |"
            for a in discarded
        )

        post = frontmatter.Post(
            (
                f"# {date_str} 每日政经简报\n\n"
                f"## 📊 今日概览\n{overview}\n\n"
                f"## 🏆 高价值文章（评分 ≥ 8）\n"
                f"| # | 评分 | 标题 | 来源 |\n|---|------|------|------|\n"
                f"{highlight_rows}\n\n"
                f"## 📚 今日学习要点\n{learning_points}\n\n"
                f"## 📋 一般信息（评分 5-7）\n"
                f"| # | 评分 | 标题 | 来源 |\n|---|------|------|------|\n"
                f"{keep_rows}\n\n"
                f"## 🗑 已过滤信息\n"
                f"| 评分 | 标题 | 原因 |\n|------|------|------|\n"
                f"{discarded_rows}\n"
            ),
            date=date_str,
            total_crawled=len(highlights) + len(keeps) + len(discarded),
            after_filter=len(highlights) + len(keeps),
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Daily brief written: {filepath}")
        return filepath

    def write_topic(self, topic_name: str, articles: list[Article], analysis: str) -> Path:
        """写入主题聚合笔记 → 主题追踪/主题名.md"""
        self.topic_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.topic_dir / f"{topic_name}.md"

        article_links = "\n".join(
            f"- [[../信息条目/{a.crawl_time.strftime('%Y-%m-%d')}/{a.source}-{a.id}|{a.title}]]"
            for a in articles
        )

        post = frontmatter.Post(
            (
                f"# {topic_name}\n\n"
                f"## 分析\n{analysis}\n\n"
                f"## 相关文章\n{article_links}\n"
            ),
            topic=topic_name,
            article_count=len(articles),
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Topic written: {filepath}")
        return filepath
```

- [ ] **Step 2: 更新 utils/__init__.py**

```python
from .logger import setup_logger
from .obsidian import ObsidianWriter
```

- [ ] **Step 3: 验证 ObsidianWriter 写入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from utils.obsidian import ObsidianWriter; from models.article import Article; from datetime import datetime; w = ObsidianWriter('E:/obsidian_vault/政治经济知识库'); a = Article(id='test123',source='xinhua',category='A',url='http://x.com',title='测试文章',raw_content='test',summary='摘要',knowledge_analysis='分析',quality_score=8,quality_reason='重要',tags=['test'],concepts=['测试概念'],clean_content='content'); w.write_article(a); print('done')"`

然后检查：`cat "E:/obsidian_vault/政治经济知识库/信息条目/$(date +%Y-%m-%d)/xinhua-test123.md"`

- [ ] **Step 4: Commit**

```bash
git add utils/__init__.py utils/obsidian.py
git commit -m "feat: add Obsidian vault writer with frontmatter and wikilinks"
```

---

### Task 11: 每日汇总报告生成器（Reporter）

**Files:**
- Create: `E:/proj/infoCollector/pipeline/reporter.py`

- [ ] **Step 1: 创建 pipeline/reporter.py**

```python
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
            result = json.loads(response.content[0].text)
            return result.get("overview", "分析暂缺"), result.get("learning_points", "无")
        except (json.JSONDecodeError, anthropic.APIError, KeyError) as e:
            log.error(f"Reporter generation failed: {e}")
            return f"LLM 分析暂不可用（{e}）", "无"
```

- [ ] **Step 2: 验证导入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from pipeline.reporter import Reporter; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add pipeline/reporter.py
git commit -m "feat: add daily report generator with LLM overview"
```

---

### Task 12: 管道编排器（Runner）

**Files:**
- Create: `E:/proj/infoCollector/pipeline/runner.py`

- [ ] **Step 1: 创建 pipeline/runner.py**

```python
"""管道编排器：串联采集 → 清洗 → 分析 → 过滤 → 写入 → 报告"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from collectors.base import BaseCollector
from pipeline.fetcher import Fetcher
from pipeline.cleaner import Cleaner
from pipeline.analyzer import Analyzer
from pipeline.filter import ArticleFilter, FilterResult
from pipeline.reporter import Reporter
from utils.obsidian import ObsidianWriter
from models.article import Article, RawArticle

log = logging.getLogger("infoCollector")


class Runner:
    """信息采集管道编排器"""

    def __init__(
        self,
        collectors: list[BaseCollector],
        fetcher: Fetcher,
        cleaner: Cleaner,
        analyzer: Analyzer,
        article_filter: ArticleFilter,
        writer: ObsidianWriter,
        reporter: Reporter,
    ):
        self.collectors = collectors
        self.fetcher = fetcher
        self.cleaner = cleaner
        self.analyzer = analyzer
        self.article_filter = article_filter
        self.writer = writer
        self.reporter = reporter

    async def run(self) -> FilterResult:
        """执行完整管道"""
        log.info(f"Pipeline started with {len(self.collectors)} collectors")

        # 阶段一：并行采集
        raw_articles = await self._collect_all()
        log.info(f"Collected {len(raw_articles)} raw articles")

        # Fetch 完整内容
        articles: list[Article] = []
        for raw in raw_articles:
            try:
                article = await self.fetcher.fetch(raw)
                articles.append(article)
            except Exception as e:
                log.error(f"Fetch failed for {raw.source}:{raw.title}: {e}")

        # 阶段二：串行处理
        # 清洗
        for a in articles:
            try:
                self.cleaner.clean(a)
            except Exception as e:
                log.error(f"Clean failed for {a.id}: {e}")

        # LLM 分析（逐个调用，避免并发限流）
        for a in articles:
            try:
                self.analyzer.analyze(a)
            except Exception as e:
                log.error(f"Analyze failed for {a.id}: {e}")
                a.quality_score = 3
                a.quality_reason = f"分析异常: {e}"

        # 过滤
        result = self.article_filter.apply(articles)

        # 写入 Obsidian Vault
        all_kept = result.highlight + result.keep
        for a in all_kept:
            try:
                self.writer.write_article(a)
            except Exception as e:
                log.error(f"Write article failed for {a.id}: {e}")

        # 生成每日汇总
        if all_kept:
            try:
                overview, learning_points = self.reporter.generate_overview(all_kept)
                self.writer.write_brief(
                    datetime.now(), result.highlight, result.keep,
                    result.discarded, overview, learning_points,
                )
            except Exception as e:
                log.error(f"Report generation failed: {e}")

        log.info(f"Pipeline complete: {len(result.highlight)} H / {len(result.keep)} K / {len(result.discarded)} D")
        return result

    async def _collect_all(self) -> list[RawArticle]:
        """并行执行所有 Collector"""
        tasks = []
        for c in self.collectors:
            tasks.append(self._safe_collect(c))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_raw: list[RawArticle] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(f"Collector {self.collectors[i]} failed: {result}")
            elif isinstance(result, list):
                all_raw.extend(result)

        return all_raw

    async def _safe_collect(self, collector: BaseCollector) -> list[RawArticle]:
        """安全的 Collector 调用，异常隔离"""
        try:
            log.info(f"Collecting from {collector.name}...")
            articles = await collector.collect()
            log.info(f"  {collector.name}: {len(articles)} articles")
            return articles
        except Exception as e:
            log.error(f"Collector {collector.name} error: {e}")
            return []
```

- [ ] **Step 2: 验证导入**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python -c "from pipeline.runner import Runner; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add pipeline/runner.py
git commit -m "feat: add pipeline runner with parallel collect and serial process"
```

---

### Task 13: 调度器 + CLI 入口

**Files:**
- Create: `E:/proj/infoCollector/scheduler.py`
- Create: `E:/proj/infoCollector/main.py`

- [ ] **Step 1: 创建 scheduler.py**

```python
"""APScheduler 封装：每日定时触发采集管道"""

import asyncio
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from pipeline.runner import Runner

log = logging.getLogger("infoCollector")


class CrawlScheduler:
    """定时任务调度器"""

    def __init__(self, runner: Runner, cron_time: str = "05:00", timezone: str = "Asia/Shanghai"):
        self.runner = runner
        self.scheduler = BackgroundScheduler(timezone=timezone)
        hour, minute = cron_time.split(":")
        self.scheduler.add_job(
            self._run_pipeline,
            trigger="cron",
            hour=int(hour),
            minute=int(minute),
            id="daily_crawl",
            name="Daily political-economic crawl",
        )

    def _run_pipeline(self):
        """调度器触发的同步包装"""
        try:
            asyncio.run(self.runner.run())
        except Exception as e:
            log.error(f"Scheduled pipeline failed: {e}")

    def start(self):
        self.scheduler.start()
        log.info(f"Scheduler started, next run: {self.scheduler.get_job('daily_crawl').next_run_time}")

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
```

- [ ] **Step 2: 创建 main.py**

```python
"""入口：CLI 手动运行 + 定时调度"""

import os
import sys
import asyncio
import logging
import argparse
import yaml
from pathlib import Path

from pipeline.fetcher import Fetcher
from pipeline.cleaner import Cleaner
from pipeline.analyzer import Analyzer
from pipeline.filter import ArticleFilter
from pipeline.reporter import Reporter
from pipeline.runner import Runner
from utils.logger import setup_logger
from utils.obsidian import ObsidianWriter
from collectors.domestic_official.xinhua import XinhuaCollector
from scheduler import CrawlScheduler


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_runner(config: dict) -> Runner:
    """根据配置组装管道组件"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    # Collector 注册（按配置启用）
    collectors = []
    cfg_domestic = config.get("collectors", {}).get("domestic_official", {})
    if cfg_domestic.get("xinhua", {}).get("enabled", False):
        collectors.append(XinhuaCollector(cfg_domestic["xinhua"]))
    # 后续 Collector 在此注册...

    vault_path = config["vault"]["path"]
    fetcher = Fetcher()
    cleaner = Cleaner()
    analyzer = Analyzer(api_key=api_key, model=config["llm"]["fast_model"])
    article_filter = ArticleFilter(
        quality_threshold=config["filter"]["quality_threshold"],
        highlight_threshold=config["filter"]["highlight_threshold"],
    )
    writer = ObsidianWriter(vault_path)
    reporter = Reporter(api_key=api_key, model=config["llm"]["smart_model"])

    return Runner(
        collectors=collectors,
        fetcher=fetcher,
        cleaner=cleaner,
        analyzer=analyzer,
        article_filter=article_filter,
        writer=writer,
        reporter=reporter,
    )


def main():
    parser = argparse.ArgumentParser(description="政治经济信息采集工具")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "schedule"],
                        help="run: 立即执行一次采集; schedule: 启动定时调度")
    parser.add_argument("--source", type=str, help="仅运行指定 Collector")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    log = setup_logger()
    config = load_config(args.config)
    runner = build_runner(config)

    if args.command == "run":
        log.info("Running pipeline once...")
        asyncio.run(runner.run())
        log.info("Done.")
    elif args.command == "schedule":
        log.info("Starting scheduler...")
        scheduler = CrawlScheduler(runner, config["schedule"]["time"], config["schedule"]["timezone"])
        scheduler.start()
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.shutdown()
            log.info("Shutdown.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 验证 CLI 帮助输出**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python main.py --help`

Expected: 显示命令行参数说明

- [ ] **Step 4: Commit**

```bash
git add scheduler.py main.py
git commit -m "feat: add CLI entry point and APScheduler wrapper"
```

---

### Task 14: 集成测试与首次运行

**Files:**
- Create: `E:/proj/infoCollector/tests/__init__.py`
- Create: `E:/proj/infoCollector/tests/test_pipeline.py`

- [ ] **Step 1: 创建 tests/test_pipeline.py**

```python
"""管道集成测试（需 ANTHROPIC_API_KEY 环境变量）"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from models.article import Article, RawArticle
from pipeline.cleaner import Cleaner
from pipeline.filter import ArticleFilter
from pipeline.fetcher import Fetcher
from collectors.base import BaseCollector
from utils.obsidian import ObsidianWriter


class MockCollector(BaseCollector):
    name = "mock"
    category = "A"

    async def collect(self) -> list[RawArticle]:
        return [
            RawArticle(
                source=self.name, category=self.category,
                url="http://test.com/1", title="测试文章1",
                raw_content="<h1>GDP增长5%</h1><p>一季度经济数据发布</p>",
                content_type="text/html",
            ),
            RawArticle(
                source=self.name, category=self.category,
                url="http://test.com/2", title="标题党标题",
                raw_content="震惊！XXX竟然这样做！点击查看...",
                content_type="text/html",
            ),
        ]


class TestCleaner:
    def test_html_to_markdown(self):
        cleaner = Cleaner()
        article = Article(
            id="test", source="mock", category="A",
            url="http://x.com", title="T",
            raw_content="<h1>Title</h1><p>Para</p>",
        )
        result = cleaner.clean(article)
        assert "# Title" in result.clean_content
        assert "Para" in result.clean_content

    def test_truncate_long_content(self):
        cleaner = Cleaner()
        article = Article(
            id="test", source="mock", category="A",
            url="http://x.com", title="T",
            raw_content="x" * 10000,
        )
        result = cleaner.clean(article)
        assert len(result.clean_content) <= 8500  # 8000 + truncate msg

    def test_plain_text_passthrough(self):
        cleaner = Cleaner()
        article = Article(
            id="test", source="mock", category="A",
            url="http://x.com", title="T",
            raw_content="plain text",
            content_type="text/plain",
        )
        result = cleaner.clean(article)
        assert result.clean_content == "plain text"


class TestArticleFilter:
    def test_filter_tiers(self):
        f = ArticleFilter(quality_threshold=5, highlight_threshold=8)
        articles = [
            Article(id="1", source="x", category="A", url="", title="", raw_content="", quality_score=9),
            Article(id="2", source="x", category="A", url="", title="", raw_content="", quality_score=6),
            Article(id="3", source="x", category="A", url="", title="", raw_content="", quality_score=3),
        ]
        result = f.apply(articles)
        assert len(result.highlight) == 1
        assert len(result.keep) == 1
        assert len(result.discarded) == 1
        assert result.highlight[0].id == "1"
        assert result.keep[0].id == "2"
        assert result.discarded[0].id == "3"


class TestObsidianWriter:
    def test_write_article(self, tmp_path):
        writer = ObsidianWriter(str(tmp_path))
        article = Article(
            id="abc123", source="xinhua", category="A",
            url="http://x.com", title="测试",
            raw_content="raw", summary="摘要",
            knowledge_analysis="分析", quality_score=8,
            quality_reason="重要", tags=["经济"], concepts=["GDP"],
            clean_content="正文",
        )
        article.crawl_time = datetime(2026, 5, 27)
        path = writer.write_article(article)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "摘要" in content
        assert "分析" in content
        assert "quality: 8" in content

    def test_write_brief(self, tmp_path):
        writer = ObsidianWriter(str(tmp_path))
        highlights = [
            Article(id="1", source="xinhua", category="A", url="", title="高价值文章",
                    raw_content="", summary="摘要", quality_score=8,
                    quality_reason="", tags=[], concepts=[]),
        ]
        path = writer.write_brief(
            date=datetime(2026, 5, 27),
            highlights=highlights,
            keeps=[],
            discarded=[],
            overview="今日市场稳定",
            learning_points="1. 要点一\n2. 要点二",
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "今日市场稳定" in content
        assert "高价值文章" in content
        assert "要点一" in content
```

- [ ] **Step 2: 运行测试**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && pip install pytest && python -m pytest tests/ -v`

Expected: 所有 5 个测试通过

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: add pipeline unit tests for cleaner, filter, and writer"
```

---

### Task 15: 干运行验证（跳过 LLM 调用）

**Files:**
- Create: `E:/proj/infoCollector/scripts/dry_run.py`

- [ ] **Step 1: 创建 scripts/dry_run.py**

```python
"""干运行：测试采集+清洗流程，不调用 LLM，不写入 Vault"""

import asyncio
import sys
sys.path.insert(0, ".")

from collectors.domestic_official.xinhua import XinhuaCollector
from pipeline.fetcher import Fetcher
from pipeline.cleaner import Cleaner


async def main():
    collector = XinhuaCollector({"rss_url": XinhuaCollector.DEFAULT_RSS})
    fetcher = Fetcher()
    cleaner = Cleaner()

    print(f"Collecting from {collector.name}...")
    raw_list = await collector.collect()
    print(f"Got {len(raw_list)} articles")

    for raw in raw_list[:5]:
        print(f"\n--- {raw.title} ---")
        article = await fetcher.fetch(raw)
        cleaner.clean(article)
        print(f"Clean content ({len(article.clean_content)} chars):")
        print(article.clean_content[:300])


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 运行干测试**

Run: `cd E:/proj/infoCollector && source .venv/Scripts/activate && python scripts/dry_run.py`

Expected: 列出新华社 RSS 的前 5 篇文章标题和清洗后正文前 300 字

- [ ] **Step 3: Commit**

```bash
git add scripts/
git commit -m "test: add dry-run script for collection and cleaning verification"
```

---

### Task 16: Windows 任务计划配置脚本

**Files:**
- Create: `E:/proj/infoCollector/scripts/setup_scheduled_task.ps1`

- [ ] **Step 1: 创建 setup_scheduled_task.ps1**

```powershell
# Windows 任务计划：每日 4:55 触发信息采集
# 以管理员身份运行此脚本

$TaskName = "InfoCollectorDailyCrawl"
$Description = "每日 4:55 运行政治经济信息采集管道"
$ScriptPath = "E:\proj\infoCollector\run.bat"

# 创建 run.bat（激活虚拟环境并运行 main.py）
@"
@echo off
cd /d E:\proj\infoCollector
call .venv\Scripts\activate.bat
python main.py run >> logs\scheduled_%date:~0,10%.log 2>&1
"@ | Out-File -FilePath $ScriptPath -Encoding ASCII

# 创建计划任务
$Action = New-ScheduledTaskAction -Execute $ScriptPath
$Trigger = New-ScheduledTaskTrigger -Daily -At 04:55
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $TaskName -Description $Description `
    -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings `
    -Force

Write-Host "Task '$TaskName' registered. Next run: 04:55 daily."
Write-Host "Check in Task Scheduler (taskschd.msc) to verify."
```

- [ ] **Step 2: Commit**

```bash
git add scripts/setup_scheduled_task.ps1
git commit -m "feat: add Windows scheduled task setup script"
```
