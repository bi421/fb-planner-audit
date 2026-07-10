"""Message and postback routing for fb-planner-audit."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import requests as req

from core.db import get_user, upsert_user
from core.audit import check_text_risk, perform_user_audit, generate_plan
from core.precheck import scan_text, record_precheck_usage
from core.qpay import create_invoice
from core.config import get
from bot.templates import (
    WELCOME_CAROUSEL,
    QUICK_REPLIES_AUDIT,
    AUDIT_RESULT_TEMPLATE,
    PLAN_RESULT_TEMPLATE,
    PAYMENT_TEMPLATE,
)

logger = logging.getLogger(__name__)

FB_GRAPH = "https://graph.facebook.com/v18.0"
PAGE_TOKEN: str = get("fb.page_token", "")
VERIFY_TOKEN: str = get("fb.verify_token", "fbplanneraudit_verify")
ADMIN_TELEGRAM_ID: int = get("admin.telegram_user_id", 0)
ADMIN_TELEGRAM_TOKEN: str = get("admin.telegram_bot_token", "")

_QUICK_REPLIES: List[Dict[str, Any]] = [
    {"content_type": "text", "title": "Шалгах", "payload": "AUDIT"},
    {"content_type": "text", "title": "Төлбөр", "payload": "PAY"},
    {"content_type": "text", "title": "Тусламж", "payload": "HELP"},
]

_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 10
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)


def _check_rate_limit(user_id: str) -> bool:
    """Return True if user is within rate limit."""
    now = time.time()
    timestamps = _rate_limit_store[user_id]
    _rate_limit_store[user_id] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[user_id]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_store[user_id].append(now)
    return True


def _call_send_api(recipient_id: str, payload: Dict[str, Any]) -> None:
    """Send a payload to the Messenger Send API."""
    url = f"{FB_GRAPH}/me/messages"
    params = {"access_token": PAGE_TOKEN}
    body = {"recipient": {"id": recipient_id}, "message": payload}
    try:
        resp = req.post(url, params=params, json=body, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.exception("Send API failed: %s", exc)


def send_message(recipient_id: str, text: str) -> None:
    """Send a plain text message to a Messenger recipient."""
    _call_send_api(recipient_id, {"text": text})


def handle_message(sender_id: str, text: str) -> None:
    """Handle a plain text message from a user."""
    if not _check_rate_limit(sender_id):
        send_message(sender_id, "⚠️ Хэт олон мессеж илгээсэн байна. 1 минутын дараа дахин оролдоно уу.")
        return

    result = scan_text(text)
    risk_score = result.get("risk_score", 0)
    reasons = result.get("reasons", [])
    if risk_score > 70:
        reasons_str = ", ".join([str(r) for r in reasons]) if reasons else "Тодорхойгүй"
        send_message(sender_id, f"⚠️ Эрсдэлтэй үг илэрлээ: {reasons_str}")
    elif risk_score < 30:
        send_message(sender_id, "✅ Зөв, нийтлэх боломжтой")
    else:
        send_message(sender_id, f"⚠️ Эрсдэлтэй байдал: {risk_score}/100")

    record_precheck_usage(sender_id)


def handle_postback(sender_id: str, payload: str) -> None:
    """Handle a postback payload from a user."""
    if payload == "PAY":
        invoice = create_invoice(sender_id, "pro")
        send_message(sender_id, f"Нэхэмжлэх: {invoice['invoice_id']}\nДүн: {invoice['amount']} {invoice['currency']}")
    else:
        send_message(sender_id, "Тусламж хүсэлт хүлээгдэж байна.")


def send_text_message(psid: str, text: str) -> None:
    """Send a plain text message."""
    _call_send_api(psid, {"text": text})


def send_typing_on(psid: str) -> None:
    """Send the typing-on indicator."""
    _call_send_api(psid, {"sender_action": "typing_on"})


def send_quick_replies(psid: str, text: str, replies: List[Dict[str, Any]]) -> None:
    """Send a message with quick replies."""
    payload = {"text": text, "quick_replies": replies}
    _call_send_api(psid, payload)


def send_template(psid: str, template: Dict[str, Any]) -> None:
    """Send a structured template (generic, etc.)."""
    _call_send_api(psid, template)


def verify_fb_token(signed_request: str) -> Optional[Dict[str, Any]]:
    """Stub: verify signed_request and return user dict or None."""
    try:
        from base64 import urlsafe_b64decode
        encoded = signed_request.split(".")[1]
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = urlsafe_b64decode(padded).decode("utf-8")
        data = json.loads(decoded)
        return data.get("user_id") or data.get("user")
    except Exception:
        return None


def handle_messaging(event: Dict[str, Any]) -> None:
    """Route incoming webhook event to the correct action."""
    psid = event.get("sender", {}).get("id")
    if not psid:
        logger.warning("No sender id in event")
        return
    upsert_user(psid)
    if "postback" in event:
        payload = event["postback"].get("payload", "")
        _route_postback(psid, payload)
    elif "message" in event:
        msg = event["message"]
        if msg.get("quick_reply"):
            payload = msg["quick_reply"].get("payload", "")
            _route_postback(psid, payload)
        else:
            text = msg.get("text", "")
            _route_text(psid, text)


def _route_postback(psid: str, payload: str) -> None:
    if payload == "GET_STARTED":
        send_template(psid, WELCOME_CAROUSEL)
    elif payload == "AUDIT":
        send_text_message(psid, "Хуудасны нэрийг оруулна уу.")
    elif payload == "audit_yes":
        user = get_user(psid)
        if user and user.get("page_name"):
            _run_audit_for_user(psid, user["page_name"])
        else:
            send_text_message(psid, "Хуудасны нэрийг оруулна уу.")
    elif payload == "audit_new":
        send_text_message(psid, "Шинэ ауудит шалгах URL оруулна уу.")
    elif payload == "PLAN":
        user = get_user(psid)
        page_id = user.get("page_id") or user.get("id")
        plan_md = generate_plan(page_id)
        send_text_message(psid, plan_md)
        send_template(psid, PLAN_RESULT_TEMPLATE)
    elif payload == "PAY":
        _handle_pay(psid)
    else:
        logger.info("Unknown postback payload: %s", payload)


def _route_text(psid: str, text: str) -> None:
    risk = check_text_risk(text)
    if risk.get("risk_level") == "high":
        reasons = risk.get("risky_words") or risk.get("suggestions") or []
        reasons_str = ", ".join([str(x) for x in reasons]) if isinstance(reasons, list) else str(reasons)
        send_text_message(psid, f"⚠️ Энэ мессеж эрсдэлтэй: {reasons_str}" if reasons_str else "⚠️ Энэ мессеж эрсдэлтэй")
        return
    user = get_user(psid)

    if user and not user.get("page_name"):
        upsert_user(psid, page_name=text)
        send_quick_replies(psid, "Хуудас бүртгэгдлээ. Аудит хийх үү?", QUICK_REPLIES_AUDIT)
    else:
        send_text_message(psid, "Та awc дээрээ дарна уу.")


def _run_audit_for_user(psid: str, page_name: str) -> None:
    send_typing_on(psid)
    result = perform_user_audit(psid, page_name)
    score = result.get("risk_score", 0)
    issues = result.get("issues", [])
    summary = json.dumps(issues, ensure_ascii=False)
    resp_text = f"Аудит дууслаа.\nЭрсдэл: {score}/100\n\n{summary}"
    send_text_message(psid, resp_text)
    send_template(psid, AUDIT_RESULT_TEMPLATE)


def _handle_pay(psid: str) -> None:
    invoice = create_invoice(psid, "pro")
    send_template(psid, PAYMENT_TEMPLATE)
    send_text_message(psid, f"Нэхэмжлэх: {invoice['invoice_id']}\nДүн: {invoice['amount']} {invoice['currency']}")
