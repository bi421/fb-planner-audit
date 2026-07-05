"""Message and postback routing for fb-planner-v2."""
import json
import logging
from typing import Dict

import requests as req

from core.db import get_user, upsert_user, get_user_subscription
from core.audit import check_text_risk, perform_user_audit, generate_plan
from core.qpay import create_invoice
from bot.templates import (
    WELCOME_CAROUSEL,
    QUICK_REPLIES_AUDIT,
    AUDIT_RESULT_TEMPLATE,
    PLAN_RESULT_TEMPLATE,
    PAYMENT_TEMPLATE,
    ERROR_TEMPLATE,
)
from core.config import get

logger = logging.getLogger(__name__)

FB_GRAPH = "https://graph.facebook.com/v18.0"
PAGE_TOKEN = get("fb.page_token", "")
VERIFY_TOKEN = get("fb.verify_token", "fbplanner_verify")
ADMIN_TELEGRAM_ID = get("admin.telegram_user_id", 0)
ADMIN_TELEGRAM_TOKEN = get("admin.telegram_bot_token", "")


def _call_send_api(recipient_id: str, payload: Dict):
    """Send a payload to the Messenger Send API."""
    url = f"{FB_GRAPH}/me/messages"
    params = {"access_token": PAGE_TOKEN}
    body = {"recipient": {"id": recipient_id}, "message": payload}
    try:
        resp = req.post(url, params=params, json=body, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.exception("Send API failed: %s", exc)



def send_text_message(psid: str, text: str):
    """Send a plain text message."""
    _call_send_api(psid, {"text": text})


def send_typing_on(psid: str):
    """Send the typing-on indicator."""
    _call_send_api(psid, {"sender_action": "typing_on"})


def send_quick_replies(psid: str, text: str, replies: list):
    """Send a message with quick replies."""
    payload = {"text": text, "quick_replies": replies}
    _call_send_api(psid, payload)


def send_template(psid: str, template: Dict):
    """Send a structured template (generic, etc.)."""
    _call_send_api(psid, template)


def verify_fb_token(signed_request: str) -> dict | None:
    """Stub: verify signed_request and return user dict or None."""
    try:
        from base64 import urlsafe_b64decode
        encoded = signed_request.split(".")[1]
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = urlsafe_b64decode(padded).decode("utf-8")
        import json
        data = json.loads(decoded)
        return data.get("user_id") or data.get("user")
    except Exception:
        return None


def handle_messaging(event: dict):
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


def _route_postback(psid: str, payload: str):
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


def _route_text(psid: str, text: str):
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


def _run_audit_for_user(psid: str, page_name: str):
    send_typing_on(psid)
    result = perform_user_audit(psid, page_name)
    score = result.get("risk_score", 0)
    issues = result.get("issues", [])
    summary = json.dumps(issues, ensure_ascii=False)
    resp_text = f"Аудит дууслаа.\nЭрсдэл: {score}/100\n\n{summary}"
    send_text_message(psid, resp_text)
    send_template(psid, AUDIT_RESULT_TEMPLATE)


def _handle_pay(psid: str):
    invoice = create_invoice(psid, "pro")
    send_template(psid, PAYMENT_TEMPLATE)
    send_text_message(psid, f"Нэхэмжлэх: {invoice['invoice_id']}\nДүн: {invoice['amount']} {invoice['currency']}")
