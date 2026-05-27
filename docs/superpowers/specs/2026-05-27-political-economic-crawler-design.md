# 政治经济信息采集工具 — 设计文档

**日期**: 2026-05-27  
**状态**: 设计中  

---

## 概述

每日自动采集政治经济类信息源，经 LLM 分析标注后沉淀为 Obsidian 知识库笔记，生成每日汇总报告，帮助用户在信息摄入中提升政经常识素养。

## 信息源策略

四层信息源，按优先级：

| 层级 | 类型 | 示例 |
|------|------|------|
| A | 国内官方媒体和政策发布 | 新华社、国务院公报、央行公告 |
| B | 国际财经媒体和分析 | Bloomberg、Reuters、经济学人 |
| C | 社交媒体和论坛讨论 | 微博、知乎 |
| D | 学术/研究类内容 | 智库报告、学术论文 |

---

## 技术选型

- **语言**：Python
- **调度**：APScheduler（Cron 触发器，每日 5:00）
- **HTTP**：httpx（异步，支持重试）
- **HTML→MD**：markdownify
- **PDF/图片→MD**：MinerU（预留接口）
- **LLM**：Anthropic API（Haiku 做单篇分析，Sonnet 做汇总报告）
- **存储**：Obsidian Vault（本地文件系统，Markdown + frontmatter）

## 项目结构

```
infoCollector/
├── config.yaml
├── requirements.txt
├── main.py                    # 入口
├── scheduler.py               # APScheduler 封装
├── pipeline/
│   ├── runner.py              # 管道编排器
│   ├── fetcher.py             # 统一抓取（含 Content-Type 路由）
│   ├── cleaner.py             # HTML/文本 → Markdown
│   ├── mineru_adapter.py      # MinerU 转换适配器（预留）
│   ├── analyzer.py            # LLM 单篇分析
│   ├── filter.py              # 质量评分过滤
│   ├── writer.py              # 写入 Obsidian Vault
│   └── reporter.py            # 每日汇总报告
├── collectors/
│   ├── base.py                # Collector 基类
│   ├── domestic_official/     # A类
│   ├── international_finance/ # B类
│   ├── academic/              # D类
│   └── social_media/          # C类
├── models/
│   └── article.py             # Article/RawArticle 数据类
└── utils/
    ├── logger.py
    └── obsidian.py            # Obsidian 格式工具
```

---

## 管道数据流

### 阶段一：并行采集

每日 5:00 触发，所有启用的 Collector 通过线程池并行抓取，产出 `RawArticle` 列表。

### 阶段二：串行处理

```
原始内容
    │
    ├── HTML → Cleaner (markdownify) ──┐
    │                                   │
    └── PDF/图片 → MinerU → MD ────────┘
                    │
                    ▼
            Analyzer (LLM)
            输入: 标题 + 清洗后正文
            输出: JSON {summary, knowledge_analysis,
                        quality_score, quality_reason,
                        tags[], concepts[]}
                    │
                    ▼
            Filter
            quality >= 8 → 高价值，推送
            quality 5-7 → 保留到 vault，不推送
            quality < 5  → 丢弃，仅记日志
                    │
                    ▼
            Writer → 写入 Obsidian Vault
                    │
                    ▼
            Reporter → 生成每日汇总笔记
```

### 核心数据结构

```python
@dataclass
class Article:
    id: str
    source: str
    category: str              # A/B/C/D
    url: str
    title: str
    raw_content: str
    clean_content: str
    crawl_time: datetime
    # LLM 分析后填充
    summary: str
    knowledge_analysis: str
    quality_score: int
    quality_reason: str
    tags: list[str]
    concepts: list[str]
```

### Collector 接口

```python
class BaseCollector(ABC):
    name: str
    category: str

    @abstractmethod
    async def collect(self) -> list[RawArticle]:
        """抓取今日内容"""
```

---

## Obsidian Vault 集成

Vault 路径：`E:/obsidian_vault/政治经济知识库`

### 新增目录

```
政治经济知识库/
├── (已有笔记和目录保持不变)
├── 📁 每日简报/       # 每日汇总报告
│   └── 2026-05-27.md
├── 📁 信息条目/       # 单篇信息笔记
│   └── 2026-05-27/
│       └── 来源-hash.md
└── 📁 主题追踪/       # 主题聚合（同主题≥5篇触发）
    └── xxx主题.md
```

### 单篇笔记模板

frontmatter 包含 date/source/url/quality/tags/category/concepts。
正文分为四个 callout 区块：原文摘要（LLM生成）、政经常识解读（PEER 框架）、影响分析（推演）、相关笔记（wikilink 回链已有知识框架）。

### 每日汇总模板

包含：今日概览、高价值文章列表（评分≥8）、今日学习要点提炼、低价值过滤日志。

---

## LLM 策略

| 任务 | 模型 | 频率 |
|------|------|------|
| 单篇分析（摘要+解读+评分） | Haiku | 高频（每日数十次） |
| 每日汇总报告 | Sonnet | 低频（每日 1 次） |
| 主题聚合笔记 | Sonnet | 极低频（几周 1 次） |

单篇分析使用单次 LLM 调用完成所有分析任务，输出严格 JSON。

分析框架注入已有的 PEER 框架：Policy/Event → Explanation → Effect → Response。

---

## 调度

- Windows 任务计划程序每日 4:55 触发 `python main.py`
- APScheduler 在 5:00 执行采集管道
- 执行完毕后进程退出
- 支持 CLI 手动运行：`python main.py run` / `python main.py run --source xinhua`

---

## 容错

- 单个 Collector 异常隔离，不影响其他源
- LLM API 调用失败自动重试 3 次（指数退避）
- 统一日志输出到 `logs/YYYY-MM-DD.log`

---

## 推送（后续阶段）

- 当前：本地 MD 文件
- 后续：飞书 Webhook、微信推送（独立推送模块）
