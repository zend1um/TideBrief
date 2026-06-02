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
        self.raw_dir = self.vault_path / "原始存档"
        self.articles_dir = self.vault_path / "信息条目"
        self.brief_dir = self.vault_path / "每日简报"
        self.topic_dir = self.vault_path / "主题追踪"

    def write_raw(self, article: Article) -> Path:
        """写入原始存档 → 原始存档/YYYY-MM-DD/来源-id.md（LLM处理前的原文）"""
        date_str = article.crawl_time.strftime("%Y-%m-%d")
        out_dir = self.raw_dir / date_str
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{article.source}-{article.id}.md"
        filepath = out_dir / filename

        pub = article.pub_date.strftime("%Y-%m-%d %H:%M") if article.pub_date else "未知"

        post = frontmatter.Post(
            f"# {article.title}\n\n{article.clean_content}\n",
            source=article.source,
            url=article.url,
            published=pub,
            crawled=article.crawl_time.strftime("%Y-%m-%d %H:%M"),
            category=article.category,
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Raw article saved: {filepath}")
        return filepath

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

        body_parts = []
        if article.translated_content:
            body_parts.append(f"## 📰 中文正文\n\n{article.translated_content}\n")
        body_parts.append(f"> [!summary] 原文摘要\n> {article.summary}\n")
        body_parts.append(f"> [!knowledge] 政经常识解读\n> {article.knowledge_analysis}\n")
        body_parts.append(f"> [!impact] 影响分析\n> 待补充...\n")
        body_parts.append(f"## 🔗 相关概念\n{concept_links}\n")
        body_parts.append(
            f"## 📎 相关笔记\n"
            f"- [[../../每日简报/{date_str}|当日简报]]\n"
            f"- [[../../中国政经]] [[../../宏观经济学]]\n"
        )

        pub = article.pub_date.strftime("%Y-%m-%d %H:%M") if article.pub_date else "未知"

        post = frontmatter.Post(
            "\n".join(body_parts),
            title=article.title,
            date=date_str,
            published=pub,
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
            f"| {i+1} | {a.quality_score} | [{a.title}](../信息条目/{date_str}/{a.source}-{a.id}.md) | {a.source} |"
            for i, a in enumerate(highlights)
        )

        keep_rows = "\n".join(
            f"| {i+1} | {a.quality_score} | [{a.title}](../信息条目/{date_str}/{a.source}-{a.id}.md) | {a.source} |"
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

    def write_morning_brief(self, date: datetime, highlights: list[Article],
                            overview: str, learning_points: str, themes: str = "") -> Path:
        """写入晨报 → 每日简报/晨报-YYYY-MM-DD.md（8:00 推送用，约5分钟阅读）"""
        self.brief_dir.mkdir(parents=True, exist_ok=True)
        date_str = date.strftime("%Y-%m-%d")
        filepath = self.brief_dir / f"晨报-{date_str}.md"

        rows = "\n".join(
            f"| {i+1} | {a.quality_score} | [{a.title}](../信息条目/{date_str}/{a.source}-{a.id}.md) | {a.source} |"
            for i, a in enumerate(highlights)
        )

        theme_section = f"## 🔭 重点关注方向\n{themes}\n\n" if themes else ""

        post = frontmatter.Post(
            (
                f"# {date_str} 晨报\n\n"
                f"> 采集时间：{date_str} 04:00 | 生成时间：{date.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"## 📊 今日宏观主线\n{overview}\n\n"
                f"{theme_section}"
                f"## 📚 今日政经常识\n{learning_points}\n\n"
                f"## 🏆 重点文章\n"
                f"| # | 评分 | 标题 | 来源 |\n|---|------|------|------|\n"
                f"{rows}\n"
            ),
            date=date_str,
            type="morning_brief",
            article_count=len(highlights),
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Morning brief written: {filepath}")
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
