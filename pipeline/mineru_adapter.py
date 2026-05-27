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
