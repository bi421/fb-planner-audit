"""Payment stub for fb-planner-v2."""
import logging
import uuid
from typing import Dict

from core.db import set_pro

logger = logging.getLogger(__name__)


def create_invoice(user_id: str, plan: str) -> Dict:
    """Return a fake invoice dict for the requested plan."""
    amounts = {"basic": 9, "pro": 29, "enterprise": 99}
    amount = amounts.get(plan, 9)
    return {
        "amount": amount,
        "currency": "USD",
        "invoice_id": f"inv_{plan}_{user_id[:8]}_{uuid.uuid4().hex[:6]}",
        "plan": plan,
        "status": "pending",
    }


def verify_webhook(payload: Dict, signature: str) -> bool:
    """Stub: always returns True for dev environments."""
    return True


def activate_subscription(user_id: str, plan: str, days: int = 30):
    """Activate a subscription in the database."""
    set_pro(user_id, plan, days)

    # After successful payment activation, run quota-aware precheck setup.
    # If the user is still quota exhausted for some reason, return payment prompt logic.
    try:
        from core.precheck import get_user_quota

        quota = get_user_quota(user_id)
        # Nothing else required here; precheck checks quota before scanning.
        return {"status": "activated", "quota": quota, "plan": plan}
    except Exception:
        return {"status": "activated", "plan": plan}

