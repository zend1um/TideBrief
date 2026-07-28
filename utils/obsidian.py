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
        body_parts.append(f"> [!summary] 新增事实\n> {article.summary}\n")
        body_parts.append(
            "## 交易映射\n"
            f"- **影响资产**：{'、'.join(article.affected_assets) or '不明确'}\n"
            f"- **方向与条件**：{article.asset_impact or '不确定'}\n"
            f"- **时间尺度**：{article.time_horizon or '不确定'}\n"
            f"- **已定价 / 预期差**：{article.priced_in or '不确定'}\n"
        )
        body_parts.append(f"## 传导链\n{article.trading_logic or article.knowledge_analysis or '不明确'}\n")
        body_parts.append(f"## 反方观点\n{article.counter_argument or '暂无独立反方论证'}\n")
        body_parts.append(f"## 证伪条件\n{article.invalidation or '暂无明确证伪条件'}\n")
        body_parts.append(
            "## 复盘目标\n"
            f"- **指标**：{article.review_metric or '人工复核'}"
            f"{f'（{article.review_symbol}）' if article.review_symbol else ''}\n"
            f"- **预期方向**：{article.expected_direction}\n"
            f"- **复盘周期**：{article.review_horizon_days} 天\n"
        )
        if article.watch_signals:
            body_parts.append("## 后续观察\n" + "\n".join(f"- {item}" for item in article.watch_signals) + "\n")
        if article.political_economy_lesson:
            body_parts.append(f"## 政经机制\n{article.political_economy_lesson}\n")
        if article.consensus_gap:
            body_parts.append(f"## 共识与二阶效应\n{article.consensus_gap}\n")
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
            ranking_score=article.ranking_score,
            trading_relevance=article.trading_relevance,
            market_impact=article.market_impact_score,
            actionability=article.actionability_score,
            novelty=article.novelty_score,
            confidence=article.confidence_score,
            quality_reason=article.quality_reason,
            tags=article.tags,
            category=article.category,
            concepts=article.concepts,
            event_key=article.event_key,
            event_type=article.event_type,
            affected_assets=article.affected_assets,
            time_horizon=article.time_horizon,
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Article written: {filepath}")
        return filepath

    def write_brief(self, date: datetime, highlights: list[Article],
                    keeps: list[Article], discarded: list[Article],
                    overview: str, learning_points: str,
                    market_snapshot=None, synthesis: dict | None = None,
                    stats: dict | None = None) -> Path:
        """写入每日交易简报；只展示固定阅读预算内的信息。"""
        self.brief_dir.mkdir(parents=True, exist_ok=True)
        date_str = date.strftime("%Y-%m-%d")
        filepath = self.brief_dir / f"{date_str}.md"

        synthesis = synthesis or {}
        stats = stats or {}
        market_text = market_snapshot.to_markdown() if market_snapshot else "> 未生成行情快照"
        regime = synthesis.get("market_regime", overview) or overview
        driver = synthesis.get("dominant_driver", "暂无足够证据")
        cross_asset = synthesis.get("cross_asset_check", "暂无足够证据")
        political_economy = synthesis.get("political_economy", "暂无")
        questions = self._format_list(synthesis.get("calibration_questions", learning_points))
        blind_spots = self._format_list(synthesis.get("blind_spots", []))
        signal_cards = "\n\n".join(
            self._signal_card(article, index, date_str) for index, article in enumerate(highlights, 1)
        ) or "> 今天没有信息达到交易信号门槛。保持空白也是一种筛选。"
        context_cards = "\n\n".join(
            (
                f"### [{article.title}](../信息条目/{date_str}/{article.source}-{article.id}.md)\n"
                f"{article.political_economy_lesson or article.summary}"
            )
            for article in keeps
        ) or "> 今日无额外背景阅读。"
        total = stats.get("total_collected", len(highlights) + len(keeps) + len(discarded))
        prefilter_rejected = stats.get("prefilter_rejected", 0)
        duplicates = stats.get("duplicates", 0)
        analyzed = stats.get("analyzed", len(highlights) + len(keeps) + len(discarded))

        post = frontmatter.Post(
            (
                f"# {date_str} 每日交易简报\n\n"
                f"> 阅读预算：约 3-5 分钟｜交易信号 {len(highlights)} 条｜背景阅读 {len(keeps)} 条\n\n"
                f"## 市场温度计\n{market_text}\n\n"
                f"## 今日主线\n{regime}\n\n"
                f"- **主导定价因子**：{driver}\n"
                f"- **跨资产验证**：{cross_asset}\n\n"
                f"## 必看交易信号\n{signal_cards}\n\n"
                f"## 政经框架（最多两条）\n{context_cards}\n\n"
                f"## 盘感训练：明日复盘\n{questions or '- 暂无'}\n\n"
                f"## 可能推翻主线的变量\n{blind_spots or '- 暂无'}\n\n"
                f"## 今日可迁移的政经机制\n{political_economy}\n\n"
                f"<details><summary>筛选统计</summary>\n\n"
                f"采集 {total} 条 → 预筛/去重后分析 {analyzed} 条 → 展示 {len(highlights) + len(keeps)} 条；"
                f"预筛排除 {prefilter_rejected} 条，重复事件 {duplicates} 条。\n\n"
                f"</details>\n"
            ),
            date=date_str,
            type="trading_brief",
            total_crawled=total,
            analyzed=analyzed,
            after_filter=len(highlights) + len(keeps),
        )

        filepath.write_text(frontmatter.dumps(post), encoding="utf-8")
        log.info(f"Daily brief written: {filepath}")
        return filepath

    @staticmethod
    def _signal_card(article: Article, index: int, date_str: str) -> str:
        link = f"../信息条目/{date_str}/{article.source}-{article.id}.md"
        watches = "、".join(article.watch_signals) or "暂无"
        return (
            f"### {index}. [{article.title}]({link}) `综合 {article.ranking_score:.1f}`\n"
            f"- **新增事实**：{article.summary or '摘要暂缺'}\n"
            f"- **交易映射**：{article.asset_impact or '方向不确定'}（{article.time_horizon or '期限不确定'}）\n"
            f"- **预期差**：{article.priced_in or '不确定'}\n"
            f"- **反方观点**：{article.counter_argument or '暂缺'}\n"
            f"- **证伪条件**：{article.invalidation or '暂缺'}\n"
            f"- **盯盘变量**：{watches}"
        )

    @staticmethod
    def _format_list(value) -> str:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, list):
            return ""
        return "\n".join(f"- {item}" for item in value if str(item).strip())

    def write_morning_brief(self, date: datetime, highlights: list[Article],
                            overview: str, learning_points, themes: str = "") -> Path:
        """写入晨报 → 每日简报/晨报-YYYY-MM-DD.md（8:00 推送用，约5分钟阅读）"""
        self.brief_dir.mkdir(parents=True, exist_ok=True)
        date_str = date.strftime("%Y-%m-%d")
        filepath = self.brief_dir / f"晨报-{date_str}.md"

        rows = "\n".join(
            f"| {i+1} | {a.quality_score} | [{a.title}](../信息条目/{date_str}/{a.source}-{a.id}.md) | {a.source} |"
            for i, a in enumerate(highlights)
        )

        # 格式化 themes（纯文本或列表）
        theme_text = ""
        if themes:
            if isinstance(themes, list):
                for t in themes:
                    if isinstance(t, dict):
                        theme_text += f"### {t.get('title', '')}\n{t.get('content', '')}\n\n"
                    else:
                        theme_text += f"{t}\n\n"
            else:
                theme_text = str(themes)
        theme_section = f"## 🔭 重点关注方向\n\n{theme_text}\n" if theme_text else ""

        # 格式化 learning_points（纯文本或列表）
        points_text = ""
        if isinstance(learning_points, list):
            for i, p in enumerate(learning_points, 1):
                if isinstance(p, dict):
                    points_text += f"{i}. **{p.get('title', '')}**：{p.get('content', '')}\n"
                else:
                    points_text += f"{i}. {p}\n"
        elif isinstance(learning_points, str) and learning_points.strip():
            points_text = learning_points
        else:
            points_text = str(learning_points) if learning_points else ""

        post = frontmatter.Post(
            (
                f"# {date_str} 晨报\n\n"
                f"> 采集时间：{date_str} 04:00 | 生成时间：{date.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"## 📊 今日宏观主线\n{overview}\n\n"
                f"{theme_section}"
                f"## 📚 今日投资要点\n{points_text}\n"
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
