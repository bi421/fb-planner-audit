"""Flask application factory and webhook entrypoint for fb-planner-audit."""
from __future__ import annotations

import os
import sys
import logging
import uuid
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from core.config import get
from core.audit import perform_user_audit
from core.brain.routes import brain_bp

from flask import Flask, request, jsonify, render_template, session

logger = logging.getLogger(__name__)


# Handlers may depend on optional modules (e.g. templates). Do not crash the
# whole service if handlers can't be imported; Render health checks must still
# return 200.
try:
    from bot.handlers import handle_message, handle_postback
except ImportError as exc:  # pragma: no cover
    logger.warning("bot.handlers import failed (%s). Webhook message handling disabled.", exc)

    def handle_message(*a, **k):
        return {"ok": False, "error": "handlers not loaded"}

    def handle_postback(*a, **k):
        return {"ok": False, "error": "handlers not loaded"}


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)  # noqa: E402

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)
app.config["JSON_AS_ASCII"] = False

# Optional CORS support (useful when calling /brain/* from other domains).
try:
    from flask_cors import CORS

    CORS(app, resources={r"/brain/*": {"origins": "*"}})
except ImportError:  # pragma: no cover
    pass

app.register_blueprint(brain_bp)



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


@app.route("/audit", methods=["GET", "POST"])
def web_audit() -> Any:
    """Simple web audit and quota paywall."""
    from core.audit import audit_creative
    from core.precheck import check_quota_and_scan

    if not session.get("audit_user_id"):
        session["audit_user_id"] = "web:" + uuid.uuid4().hex
    report = None
    error = None
    copy_text = ""
    if request.method == "POST":
        copy_text = (request.form.get("copy") or "")[:10000]
        if not copy_text.strip():
            error = "Зарын текстээ оруулна уу."
        else:
            try:
                result = check_quota_and_scan(session["audit_user_id"], copy_text)
                if result.get("status") == "paid_required":
                    error = "Үнэгүй 5 шалгалтын эрх дууссан. Төлбөрийн багцаа сонгоно уу."
                else:
                    report = audit_creative(copy_text)
            except Exception:
                logger.exception("Web audit failed")
                error = "Шалгалт түр амжилтгүй боллоо. Дахин оролдоно уу."
    return render_template("audit.html", report=report, error=error, copy_text=copy_text)


@app.route("/v1/audit", methods=["POST"])
def api_audit() -> Any:
    """JSON audit endpoint for the web app and future extension."""
    from core.audit import audit_creative
    from core.precheck import check_quota_and_scan

    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "")[:10000]
    if not text.strip():
        return jsonify({"error": "text_required"}), 400
    user_id = str(payload.get("user_id") or session.get("audit_user_id") or "")
    if not user_id:
        session["audit_user_id"] = "web:" + uuid.uuid4().hex
        user_id = session["audit_user_id"]
    try:
        result = check_quota_and_scan(user_id, text)
        if result.get("status") == "paid_required":
            return jsonify({"error": "quota_exceeded", "message": result["message"]}), 402
        return jsonify(audit_creative(text))
    except Exception:
        logger.exception("API audit failed")
        return jsonify({"error": "audit_unavailable"}), 503


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


try:
    init_db()
except Exception:
    logger.exception("Supabase unavailable at startup; database-backed features will fail closed")
_start_scheduler()
