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

from bot.handlers import handle_message, handle_postback

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

VERIFY_TOKEN = get("fb.verify_token", "fbplanner_verify")
ADMIN_TELEGRAM_ID = get("admin.telegram_user_id", 0)
ADMIN_TELEGRAM_TOKEN = get("admin.telegram_bot_token", "")


def init_db():
    from core.db import init_db as _init_db
    _init_db()


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if token == VERIFY_TOKEN:
            return challenge
        return "Verification failed", 403

    data = request.get_json()
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


@app.route('/')
def health():
    return "FB Planner v2 running ✓"


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
