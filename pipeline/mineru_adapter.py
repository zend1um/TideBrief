"""MinerU API v4 适配器：异步提交 → 轮询 → 下载结果

API 文档: https://mineru.net/api/v4
流程: POST /api/v4/extract/task → 轮询 GET task/{id} → 下载 full_zip_url → 提取 full.md
"""

import logging
import time
import zipfile
import io
import os
import requests
from models.article import Article

log = logging.getLogger("infoCollector")

MINERU_BASE = "https://mineru.net/api/v4"


class MinerUAdapter:
    """MinerU PDF/图片/文档 → Markdown 转换器"""

    def __init__(self, token: str = ""):
        self.token = token or os.environ.get("MINERU_TOKEN", "")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def supports(self, content_type: str) -> bool:
        supported = (
            "application/pdf" in content_type
            or content_type.startswith("image/")
            or any(ext in content_type for ext in ["doc", "docx", "ppt", "pptx", "xls", "xlsx"])
        )
        return supported

    def convert_url(self, url: str, model: str = "vlm") -> str:
        """提交 URL 给 MinerU 异步解析，返回 Markdown

        Args:
            url: 文件 URL（PDF/DOCX/图片等）
            model: vlm（推荐）/ pipeline / MinerU-HTML（仅 HTML）

        Returns:
            Markdown 文本，失败返回空字符串
        """
        if not self.token:
            log.warning("MinerU token not configured, skipping")
            return ""

        # 1. 提交任务
        data = {"url": url, "model_version": model}
        try:
            resp = requests.post(
                f"{MINERU_BASE}/extract/task",
                headers=self.headers,
                json=data,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") != 0:
                log.error(f"MinerU task creation failed: {result.get('msg')}")
                return ""
            task_id = result["data"]["task_id"]
            log.info(f"MinerU task created: {task_id}")
        except Exception as e:
            log.error(f"MinerU task creation error: {e}")
            return ""

        # 2. 轮询等待完成（最长 5 分钟，间隔 5 秒）
        full_zip_url = self._poll_task(task_id)
        if not full_zip_url:
            return ""

        # 3. 下载 zip 并提取 full.md
        return self._download_and_extract(full_zip_url)

    def _poll_task(self, task_id: str, max_wait: int = 300, interval: int = 5) -> str:
        """轮询任务状态，返回 full_zip_url"""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{MINERU_BASE}/extract/task/{task_id}",
                    headers=self.headers,
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
                data = result.get("data", {})
                state = data.get("state", "")

                if state == "done":
                    return data.get("full_zip_url", "")
                elif state == "failed":
                    log.error(f"MinerU task failed: {data.get('err_msg', 'unknown')}")
                    return ""
                else:
                    log.debug(f"MinerU task {task_id}: {state}")
            except Exception as e:
                log.warning(f"MinerU poll error: {e}")

            time.sleep(interval)

        log.error(f"MinerU task {task_id} timed out after {max_wait}s")
        return ""

    def _download_and_extract(self, zip_url: str) -> str:
        """下载 zip 包，提取 full.md"""
        try:
            resp = requests.get(zip_url, timeout=60)
            resp.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                # 查找 full.md（可能在子目录中）
                for name in z.namelist():
                    if name.endswith("full.md"):
                        return z.read(name).decode("utf-8")
                # 备选：查找任何 .md 文件
                for name in z.namelist():
                    if name.endswith(".md"):
                        return z.read(name).decode("utf-8")

                log.warning(f"MinerU zip has no .md files: {z.namelist()[:10]}")
                return ""
        except Exception as e:
            log.error(f"MinerU download/extract error: {e}")
            return ""
