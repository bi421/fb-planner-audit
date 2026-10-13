"""Flask application factory and webhook entrypoint for fb-planner-audit."""
from __future__ import annotations

import os
import sys
import logging
import uuid
import time
import threading
from collections import defaultdict, deque
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



# Single-worker, process-local rate limit. Render/Gunicorn is configured for one worker.
_rate_lock = threading.Lock()
_rate_events: dict[str, deque[float]] = defaultdict(deque)


@app.before_request
def enforce_audit_rate_limit() -> Any:
    if request.endpoint not in {"web_audit", "api_audit"}:
        return None
    identity = str(session.get("audit_user_id") or request.remote_addr or "anonymous")
    now = time.monotonic()
    with _rate_lock:
        events = _rate_events[identity]
        while events and now - events[0] >= 60:
            events.popleft()
        if len(events) >= 10:
            return jsonify({"error": "rate_limited", "message": "Нэг хэрэглэгч минутанд 10 шалгалт хийх боломжтой."}), 429
        events.append(now)
    return None


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
    user_id = str(session.get("audit_user_id") or "")
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


@app.route("/billing/invoice", methods=["POST"])
def billing_invoice() -> Any:
    """Create a real QPay invoice for a selected plan."""
    from core.db import save_invoice
    from core.qpay import PLANS, create_invoice, QPayError

    if not session.get("audit_user_id"):
        session["audit_user_id"] = "web:" + uuid.uuid4().hex
    plan = str(request.form.get("plan") or (request.get_json(silent=True) or {}).get("plan") or "")
    if plan not in PLANS:
        return jsonify({"error": "invalid_plan", "plans": PLANS}), 400
    details = PLANS[plan]
    try:
        invoice = create_invoice(details["amount"], f"FB Planner Audit - {plan}", user_id=session["audit_user_id"], plan=plan)
        save_invoice(session["audit_user_id"], invoice["invoice_id"], details["amount"], plan)
        if request.is_json:
            return jsonify(invoice), 201
        return render_template("payment.html", invoice=invoice, plan=plan, error=None)
    except (QPayError, RuntimeError):
        logger.exception("QPay invoice creation failed")
        if request.is_json:
            return jsonify({"error": "payment_unavailable", "message": "QPay одоогоор холбогдох боломжгүй байна."}), 503
        return render_template("payment.html", invoice=None, plan=plan, error="QPay төлбөрийн үйлчилгээ түр боломжгүй байна."), 503


@app.route("/billing/check/<invoice_id>", methods=["GET"])
def billing_check(invoice_id: str) -> Any:
    """Check an invoice owned by this browser session."""
    from core.db import get_invoice
    from core.qpay import check_payment
    invoice = get_invoice(invoice_id)
    if not invoice or invoice.get("user_id") != session.get("audit_user_id"):
        return jsonify({"error": "invoice_not_found"}), 404
    if invoice.get("status") == "paid":
        return jsonify({"status": "paid"})
    try:
        payment = check_payment(invoice_id)
        if payment["paid"]:
            return jsonify({"status": "processing", "message": "Төлбөр баталгаажсан; эрх шинэчлэгдэж байна. Вебхүүк хүлээн авна уу."})
        return jsonify({"status": "pending"})
    except Exception:
        logger.exception("QPay payment check failed")
        return jsonify({"error": "payment_check_unavailable"}), 503


@app.route("/webhook/qpay", methods=["POST"])
def qpay_webhook() -> Any:
    """Verify payment against QPay API; never trust callback fields as proof."""
    from core.db import get_invoice, mark_invoice_paid
    from core.qpay import PLANS, activate_subscription, check_payment

    payload = request.get_json(silent=True) or {}
    invoice_id = str(payload.get("invoice_id") or payload.get("object_id") or "")
    if not invoice_id:
        return jsonify({"error": "invoice_id_required"}), 400
    invoice = get_invoice(invoice_id)
    if not invoice:
        logger.warning("QPay callback for unknown invoice")
        return jsonify({"error": "unknown_invoice"}), 404
    if invoice.get("status") == "paid":
        return jsonify({"ok": True, "status": "already_paid"})
    try:
        payment = check_payment(invoice_id)
        if not payment.get("paid"):
            return jsonify({"ok": True, "status": "pending"}), 202
        paid = mark_invoice_paid(invoice_id)
        if paid:
            activate_subscription(paid["user_id"], paid["plan"])
            _notify_owner_payment(paid)
        return jsonify({"ok": True, "status": "paid"})
    except Exception:
        logger.exception("QPay webhook processing failed")
        return jsonify({"error": "payment_processing_failed"}), 503


def _notify_owner_payment(invoice: dict[str, Any]) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.getenv("OWNER_TELEGRAM_ID", "")
    if not token or not owner_id:
        logger.info("Payment succeeded; owner Telegram alert not configured (invoice=%s)", invoice.get("invoice_id"))
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": owner_id, "text": f"QPay төлбөр баталгаажлаа: {invoice.get('amount')}₮ / {invoice.get('plan')} / user={invoice.get('user_id')}"},
            timeout=5,
        ).raise_for_status()
    except Exception:
        logger.exception("Owner payment alert failed")


@app.route("/health", methods=["GET"])
def health() -> Any:
    """Health check endpoint for load balancers."""
    return jsonify({"status": "ok", "service": "fb-planner-audit"})


@app.route("/", methods=["GET"])
def root() -> Any:
    """Render the Mongolian product landing page."""
    return render_template("landing.html")


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
