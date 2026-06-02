"""源发现脚本：定期扫描新的 RSS/API 源，测试可用性，打印可接入的源"""

import asyncio
import httpx
import feedparser
import yaml
from pathlib import Path

# 候选源列表（持续更新）
CANDIDATES = [
    # 投资/交易类
    ("SeekingAlpha", "https://seekingalpha.com/feed.xml", "B"),
    ("ZeroHedge", "https://feeds.feedburner.com/zerohedge/feed", "B"),
    ("Investopedia", "https://www.investopedia.com/feedbuilder/feed/getfeed", "B"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "B"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex", "B"),

    # 社交媒体（通过RSS桥接）
    ("Nitter", "https://nitter.net/search/rss?f=tweets&q=finance", "C"),
    ("Reddit investing", "https://www.reddit.com/r/investing/.rss", "C"),
    ("Reddit wallstreetbets", "https://www.reddit.com/r/wallstreetbets/.rss", "C"),

    # 央行/官方
    ("Fed", "https://www.federalreserve.gov/feeds/pressreleases.xml", "A"),
    ("ECB", "https://www.ecb.europa.eu/rss/press.html", "A"),
    ("BIS statistics", "https://www.bis.org/statistics/rss/index.htm", "A"),

    # 中国金融
    ("东方财富", "https://data.eastmoney.com/report/stock.jshtml", "A"),
    ("雪球热帖", "https://xueqiu.com/hots/topic/rss", "C"),
    ("证券时报", "https://www.stcn.com/rss/index.xml", "A"),
    ("第一财经", "https://www.yicai.com/rss/", "A"),

    # 量化/另类数据
    ("Quantocracy", "https://quantocracy.com/feed/", "D"),
    ("QuantInsti", "https://blog.quantinsti.com/feed/", "D"),
]


async def test_source(name: str, url: str, category: str) -> dict | None:
    """测试一个源是否可用"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, verify=False) as c:
            resp = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            if len(feed.entries) > 0:
                return {
                    "name": name, "url": url, "category": category,
                    "articles": len(feed.entries),
                    "sample": feed.entries[0].get("title", "")[:60],
                }
    except Exception:
        pass
    return None


async def main():
    print("Scanning new data sources...\n")
    results = []
    for name, url, cat in CANDIDATES:
        r = await test_source(name, url, cat)
        if r:
            results.append(r)
            print(f"[OK] [{r['category']}] {name}: {r['articles']} articles — {r['sample'][:50]}")
        else:
            print(f"[ERR] {name}")

    # 保存可用源
    out = Path(__file__).parent.parent / "discovered_sources.yml"
    existing = {}
    if out.exists():
        with open(out) as f:
            existing = yaml.safe_load(f) or {}

    for r in results:
        key = r["name"].lower().replace(" ", "_")
        existing[key] = {"name": r["name"], "url": r["url"], "category": r["category"]}

    with open(out, "w") as f:
        yaml.dump(existing, f, allow_unicode=True)

    print(f"\nSaved {len(results)} sources to discovered_sources.yml")


if __name__ == "__main__":
    asyncio.run(main())
