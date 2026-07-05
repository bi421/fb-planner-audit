import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import logging
import sqlite3
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from core.config import get
from core.db import _conn, get_user, get_user_subscription
from core.audit import perform_user_audit, generate_plan
from core.qpay import create_invoice

from flask import Flask, request, jsonify

from bot.handlers import handle_messaging, send_text_message

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

VERIFY_TOKEN = get("fb.verify_token", "fbplanner_verify")
ADMIN_TELEGRAM_ID = get("admin.telegram_user_id", 0)
ADMIN_TELEGRAM_TOKEN = get("admin.telegram_bot_token", "")


def init_db():
    from core.db import init_db as _init_db
    _init_db()


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    try:
        handle_messaging(data)
    except Exception as exc:
        logger.exception("Webhook handling failed: %s", exc)
    return "OK", 200


@app.route("/", methods=["GET"])
def health_check():
    return "ok", 200


def _start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=_daily_audit_job,
        trigger="interval",
        minutes=10,
        id="_daily_audit_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started, interval=10 minutes")


def _daily_audit_job():
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
