"""Flask application factory and webhook entrypoint for fb-planner-audit."""
from __future__ import annotations

import os
import sys
import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from core.config import get
from core.audit import perform_user_audit

from flask import Flask, request, jsonify

from bot.handlers import handle_message, handle_postback

logger = logging.getLogger(__name__)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)  # noqa: E402

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

VERIFY_TOKEN: str = get("fb.verify_token", "fbplanneraudit_verify")
ADMIN_TELEGRAM_ID: int = get("admin.telegram_user_id", 0)
ADMIN_TELEGRAM_TOKEN: str = get("admin.telegram_bot_token", "")


def init_db() -> None:
    """Initialise database on startup."""
    from core.db import init_db as _init_db
    _init_db()


@app.route("/webhook", methods=["GET", "POST"])
def webhook() -> Any:
    """Facebook Messenger webhook endpoint."""
    if request.method == "GET":
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if token == VERIFY_TOKEN:
            return challenge
        return "Verification failed", 403

    data = request.get_json(silent=True) or {}
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            if not sender_id:
                continue
            if "message" in event and "text" in event["message"]:
                handle_message(sender_id, event["message"]["text"])
            elif "postback" in event:
                handle_postback(sender_id, event["postback"]["payload"])
    return "OK", 200


@app.route("/health", methods=["GET"])
def health() -> Any:
    """Health check endpoint for load balancers."""
    return jsonify({"status": "ok", "service": "fb-planner-audit"})


@app.route("/", methods=["GET"])
def root() -> str:
    """Root health endpoint."""
    return "FB Planner Audit running ✓"


def _start_scheduler() -> None:
    """Start background scheduler for periodic audits."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=_daily_audit_job,
        trigger="interval",
        minutes=get("scheduler.interval_minutes", 10),
        id="_daily_audit_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started, interval=%s minutes", get("scheduler.interval_minutes", 10))


def _daily_audit_job() -> None:
    """Background job: run audit for all users."""
    try:
        from core.db import iter_users
        for user in iter_users():
            try:
                perform_user_audit(user["id"], user.get("page_name", ""))
            except Exception as exc:
                logger.debug("Scheduled audit failed for %s: %s", user["id"], exc)
    except Exception as exc:
        logger.debug("Scheduler job failed: %s", exc)


init_db()
_start_scheduler()
