"""统一配置读取：静态 YAML、持久化 UI 设置与部署环境变量。"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any

import yaml


ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "INFOCOLLECTOR_VAULT_PATH": ("vault", "path"),
    "INFOCOLLECTOR_DASHBOARD_PATH": ("output", "dashboard_snapshot"),
    "INFOCOLLECTOR_REVIEW_DB": ("output", "review_database"),
    "INFOCOLLECTOR_RUNTIME_STATUS_PATH": ("output", "runtime_status"),
    "INFOCOLLECTOR_CALENDAR_PATH": ("calendar", "path"),
    "INFOCOLLECTOR_COLLECT_TIME": ("schedule", "collect_time"),
    "INFOCOLLECTOR_TIMEZONE": ("schedule", "timezone"),
}

RUNTIME_SETTING_KEYS = {
    "focus_keywords",
    "max_daily_items",
    "max_context_items",
}


def settings_path(config_path: str | Path, explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    from_env = os.environ.get("INFOCOLLECTOR_SETTINGS_PATH", "").strip()
    if from_env:
        return Path(from_env)
    return Path(config_path).resolve().parent / "data" / "runtime-settings.json"


def load_config(
    config_path: str | Path = "config.yaml",
    *,
    runtime_settings_path: str | Path | None = None,
) -> dict:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("config.yaml 顶层必须是对象")

    merged = deepcopy(config)
    runtime_path = settings_path(path, runtime_settings_path)
    if runtime_path.exists():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            runtime = {}
        if isinstance(runtime, dict):
            filter_config = merged.setdefault("filter", {})
            prefilter = filter_config.setdefault("prefilter", {})
            for key in RUNTIME_SETTING_KEYS:
                if key not in runtime:
                    continue
                if key == "focus_keywords":
                    prefilter[key] = runtime[key]
                else:
                    filter_config[key] = runtime[key]

    for variable, key_path in ENV_OVERRIDES.items():
        value = os.environ.get(variable, "").strip()
        if value:
            _set_nested(merged, key_path, value)
    return merged


def write_runtime_settings(path: str | Path, settings: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: settings[key] for key in RUNTIME_SETTING_KEYS if key in settings}
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    return output


def _set_nested(config: dict, key_path: tuple[str, ...], value: Any) -> None:
    target = config
    for key in key_path[:-1]:
        target = target.setdefault(key, {})
    target[key_path[-1]] = value
