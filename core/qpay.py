"""Payment integration for fb-planner-audit."""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional

from core.db import set_pro

logger = logging.getLogger(__name__)

_PLANS: Dict[str, int] = {
    "basic": 9,
    "pro": 29,
    "enterprise": 99,
}


def create_invoice(user_id: str, plan: str) -> Dict[str, Any]:
    """Return an invoice dict for the requested plan."""
    if not user_id:
        raise ValueError("user_id must not be empty")
    if plan not in _PLANS:
        raise ValueError(f"Invalid plan: {plan}")

    amount = _PLANS[plan]
    invoice_id = f"inv_{plan}_{user_id[:8]}_{hashlib.sha256(user_id.encode()).hexdigest()[:6]}"
    return {
        "amount": amount,
        "currency": "USD",
        "invoice_id": invoice_id,
        "plan": plan,
        "status": "pending",
    }


def verify_webhook(payload: Dict[str, Any], signature: str, secret: Optional[str] = None) -> bool:
    """Verify webhook signature with replay protection."""
    if secret is None:
        from core.config import get
        secret = get("fb.app_secret", "")
    if not secret or not signature:
        return False

    try:
        import hmac
        import hashlib
        timestamp = payload.get("timestamp", 0)
        if abs(time.time() - int(timestamp)) > 300:
            return False
        expected = hmac.new(secret.encode(), str(payload).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def activate_subscription(user_id: str, plan: str, days: int = 30) -> Dict[str, Any]:
    """Activate a subscription in the database."""
    if not user_id or not plan:
        raise ValueError("user_id and plan must not be empty")
    if days <= 0:
        raise ValueError("days must be positive")

    set_pro(user_id, plan, days)

    try:
        from core.precheck import get_user_quota
        quota = get_user_quota(user_id)
        return {"status": "activated", "quota": quota, "plan": plan}
    except Exception:
        return {"status": "activated", "plan": plan}
