"""Configuration loader for fb-planner-v2."""
import os
import logging

import yaml

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

_config = None


def load_config():
    """Load and return the YAML configuration as a dict."""
    global _config
    if _config is not None:
        return _config
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        _config = yaml.safe_load(fh)
    logger.info("Config loaded from %s", CONFIG_PATH)
    return _config


def get(key, default=None):
    """Get a dot-notation config value, e.g. get('fb.verify_token')."""
    cfg = load_config()
    parts = key.split(".")
    cur = cfg
    for p in parts:
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return default
    return cur
