"""Configuration loader for fb-planner-audit."""
from __future__ import annotations

import os
import logging
from typing import Any, Optional

import yaml

from .models import Settings

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config.yaml")
_settings: Optional[Settings] = None


def load_config() -> dict[str, Any]:
    """Load and return the YAML configuration as a dict."""
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found: {_CONFIG_PATH}")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    logger.info("Config loaded from %s", _CONFIG_PATH)
    return config


def get_settings() -> Settings:
    """Return parsed Settings model (cached)."""
    global _settings
    if _settings is None:
        raw = load_config()
        _settings = Settings.model_validate(raw)
    return _settings


def get(key: str, default: Any = None) -> Any:
    """Get a dot-notation config value, e.g. get('fb.verify_token')."""
    cfg = load_config()
    parts = key.split(".")
    cur = cfg
    for p in parts:
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return default
    return cur
