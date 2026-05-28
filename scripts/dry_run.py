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
