"""Entrypoint for fb-planner-audit.

Supports two modes:
- WEBHOOK (default): runs Flask app for Facebook webhook
- POLLING: runs Telegram bot polling (placeholder)
"""
from __future__ import annotations

import os
import sys
import threading
import time
import logging

import schedule

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.db import init_db  # noqa: E402
from bot.app import app  # noqa: E402
from core.policy_updater import update  # noqa: E402

logger = logging.getLogger(__name__)


def _run_scheduler() -> None:
    """Run scheduled tasks."""
    schedule.every().monday.at("09:00").do(update)
    while True:
        schedule.run_pending()
        time.sleep(60)


def _run_webhook() -> None:
    """Run Flask webhook server."""
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    logger.info("Starting webhook mode on port %s (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)


def _run_polling() -> None:
    """Run Telegram polling (placeholder)."""
    logger.info("Polling mode not implemented yet")


def main() -> None:
    """Main entrypoint."""
    init_db()
    t = threading.Thread(target=_run_scheduler, daemon=True)
    t.start()

    mode = os.environ.get("RUN_MODE", "webhook").lower()
    if mode == "webhook":
        _run_webhook()
    elif mode == "polling":
        _run_polling()
    else:
        raise ValueError(f"Invalid RUN_MODE: {mode}. Use 'webhook' or 'polling'.")


if __name__ == "__main__":
    main()
