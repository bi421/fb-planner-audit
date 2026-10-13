"""QPay V2 integration.

Required Render environment variables:
QPAY_CLIENT_ID, QPAY_CLIENT_SECRET, QPAY_INVOICE_CODE.
Amounts are Mongolian tögrög (MNT). No local/fake invoice is returned when QPay
credentials or the upstream service are unavailable.
"""
from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)
_BASE_URL = os.getenv("QPAY_BASE_URL", "https://merchant.qpay.mn/v2").rstrip("/")
_TIMEOUT = (3.05, 15)
_token_cache: tuple[str, float] | None = None

PLANS: dict[str, dict[str, int]] = {
    "starter": {"amount": 9_900, "quota_limit": 50},
    "agency": {"amount": 49_900, "quota_limit": 500},
}


class QPayError(RuntimeError):
    """Raised when QPay cannot complete a payment operation."""


def _credentials() -> tuple[str, str, str]:
    client_id = os.getenv("QPAY_CLIENT_ID", "").strip()
    client_secret = os.getenv("QPAY_CLIENT_SECRET", "").strip()
    invoice_code = os.getenv("QPAY_INVOICE_CODE", "").strip()
    if not all((client_id, client_secret, invoice_code)):
        raise QPayError("QPAY_CLIENT_ID, QPAY_CLIENT_SECRET and QPAY_INVOICE_CODE must be configured")
    return client_id, client_secret, invoice_code


def _access_token() -> str:
    global _token_cache
    if _token_cache and _token_cache[1] > time.time() + 30:
        return _token_cache[0]
    client_id, client_secret, _ = _credentials()
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        response = requests.post(
            f"{_BASE_URL}/auth/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise QPayError("QPay token response did not include access_token")
        expires_in = max(60, int(payload.get("expires_in", 3600)))
        _token_cache = (str(token), time.time() + expires_in)
        return str(token)
    except (requests.RequestException, ValueError) as exc:
        logger.exception("QPay authentication failed")
        raise QPayError("Could not authenticate with QPay") from exc


def _api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{_BASE_URL}/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
            json=payload,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise QPayError("Unexpected QPay response format")
        return data
    except (requests.RequestException, ValueError) as exc:
        logger.exception("QPay API request failed: %s", path)
        raise QPayError(f"QPay request failed: {path}") from exc


def create_invoice(amount: int, description: str, *, user_id: str | None = None,
                   plan: str | None = None, callback_url: str | None = None) -> dict[str, Any]:
    """Create a real QPay V2 invoice in MNT and return QR/payment URLs."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("amount must be a positive number of MNT")
    if not description or not description.strip():
        raise ValueError("description must not be empty")
    _, _, invoice_code = _credentials()
    sender_invoice_no = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "invoice_code": invoice_code,
        "sender_invoice_no": sender_invoice_no,
        "invoice_receiver_code": "terminal",
        "invoice_description": description.strip()[:255],
        "amount": int(amount),
        "callback_url": callback_url or os.getenv("QPAY_CALLBACK_URL", "").strip(),
    }
    result = _api_post("invoice", payload)
    invoice_id = result.get("invoice_id")
    if not invoice_id:
        raise QPayError("QPay invoice response did not include invoice_id")
    return {
        "invoice_id": str(invoice_id),
        "sender_invoice_no": sender_invoice_no,
        "amount": int(amount),
        "currency": "MNT",
        "description": description.strip(),
        "plan": plan,
        "user_id": user_id,
        "status": "pending",
        "qr_image": result.get("qr_image"),
        "qr_text": result.get("qr_text"),
        "qpay_short_url": result.get("qPay_shortUrl"),
        "urls": result.get("urls", []),
    }


def check_payment(invoice_id: str) -> dict[str, Any]:
    """Query QPay V2 for payments applied to an invoice; never infer payment."""
    if not invoice_id or not str(invoice_id).strip():
        raise ValueError("invoice_id must not be empty")
    result = _api_post("payment/check", {"object_type": "INVOICE", "object_id": str(invoice_id)})
    rows = result.get("rows", [])
    paid = any(str(row.get("payment_status", "")).upper() == "PAID" for row in rows if isinstance(row, dict))
    return {"invoice_id": str(invoice_id), "paid": paid, "status": "paid" if paid else "pending", "payments": rows}


def activate_subscription(user_id: str, plan: str, days: int = 30) -> dict[str, Any]:
    """Activate a subscription only after the caller has verified payment."""
    if not user_id or plan not in PLANS:
        raise ValueError("user_id and a supported plan (starter/agency) are required")
    if days <= 0:
        raise ValueError("days must be positive")
    from core.db import set_pro
    set_pro(user_id, plan, days)
    return {"status": "activated", "plan": plan, "quota_limit": PLANS[plan]["quota_limit"]}


def verify_webhook(payload: dict[str, Any], signature: str, secret: str | None = None) -> bool:
    """Verify timestamped HMAC callbacks when a shared webhook secret is configured.

    QPay payment status must still be checked against QPay's API before activation.
    """
    import hashlib
    import hmac
    import json

    secret = secret or os.getenv("QPAY_WEBHOOK_SECRET", "")
    if not secret or not signature or not isinstance(payload, dict):
        return False
    try:
        timestamp = int(payload.get("timestamp", 0))
        if abs(time.time() - timestamp) > 300:
            return False
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except (TypeError, ValueError, OverflowError):
        return False
