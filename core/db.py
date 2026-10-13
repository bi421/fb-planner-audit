"""Supabase Postgres persistence for fb-planner-audit.

Set SUPABASE_URL and SUPABASE_KEY (server-side service-role key) in Render.
Apply supabase/schema.sql in the Supabase SQL Editor before deploying.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)
_client: Client | None = None


def _conn() -> Client:
    """Return a cached Supabase client; fail closed when not configured."""
    global _client
    if _client is not None:
        return _client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured; SQLite fallback is disabled")
    _client = create_client(url, key)
    return _client


def init_db() -> None:
    """Verify database configuration. Schema is provisioned via supabase/schema.sql."""
    client = _conn()
    client.table("users").select("psid").limit(1).execute()
    logger.info("Supabase Postgres connection verified")


def _user_compat(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out.setdefault("id", out.get("psid"))
    return out


def get_user(psid: str) -> Optional[Dict[str, Any]]:
    if not psid:
        return None
    rows = _conn().table("users").select("*").eq("psid", psid).limit(1).execute().data
    return _user_compat(rows[0] if rows else None)


def upsert_user(psid: str, **kwargs: Any) -> None:
    if not psid:
        raise ValueError("psid must not be empty")
    allowed = {"page_id", "page_name", "page_token", "last_audit_at", "tier", "quota_used", "quota_limit", "expires_at"}
    unknown = set(kwargs) - allowed
    if unknown:
        raise ValueError(f"Invalid user field(s): {', '.join(sorted(unknown))}")
    payload = {"psid": psid, **kwargs}
    _conn().table("users").upsert(payload, on_conflict="psid").execute()


def save_audit(user_id: str, **kwargs: Any) -> int:
    if not user_id:
        raise ValueError("user_id must not be empty")
    allowed = {"url", "risk_score", "issues_json", "pdf_url", "input_text", "risky_words_found"}
    unknown = set(kwargs) - allowed
    if unknown:
        raise ValueError(f"Invalid audit field(s): {', '.join(sorted(unknown))}")
    if not get_user(user_id):
        upsert_user(user_id)
    issues = kwargs.get("risky_words_found")
    if issues is None:
        raw = kwargs.get("issues_json", "[]")
        try:
            issues = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            issues = [{"message": str(raw)}]
    result = _conn().table("scans").insert({
        "user_id": user_id,
        "input_text": str(kwargs.get("input_text") or kwargs.get("url") or "")[:10000],
        "risky_words_found": issues if isinstance(issues, (list, dict)) else [str(issues)],
    }).execute()
    return int(result.data[0]["id"]) if result.data else 0


def get_user_subscription(psid: str) -> Optional[Dict[str, Any]]:
    user = get_user(psid)
    if not user:
        return None
    return {
        "user_id": psid,
        "plan": user.get("tier", "free"),
        "is_pro": user.get("tier", "free") != "free",
        "expires_at": user.get("expires_at"),
    }


def set_pro(psid: str, plan: str, days: int) -> None:
    if not psid or plan not in {"starter", "agency"}:
        raise ValueError("psid and supported plan (starter/agency) are required")
    if days <= 0:
        raise ValueError("days must be positive")
    limits = {"starter": 50, "agency": 500}
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    upsert_user(psid, tier=plan, quota_used=0, quota_limit=limits[plan], expires_at=expires.isoformat())
    logger.info("Subscription activated for %s, plan=%s, expires=%s", psid, plan, expires.isoformat())


def get_user_quota(user_id: str) -> int:
    user = get_user(user_id)
    if not user:
        upsert_user(user_id)
        return 5
    expires = user.get("expires_at")
    tier = user.get("tier", "free")
    if tier != "free" and expires:
        try:
            dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < dt:
                return max(0, int(user.get("quota_limit", 0)) - int(user.get("quota_used", 0)))
        except (TypeError, ValueError):
            logger.warning("Invalid subscription expiry for user %s", user_id)
    used = int(user.get("quota_used", 0) or 0)
    return max(0, 5 - used)


def record_scan(user_id: str, input_text: str, findings: list[dict[str, Any]] | list[str]) -> None:
    user = get_user(user_id)
    if not user:
        upsert_user(user_id)
        user = get_user(user_id) or {"quota_used": 0, "tier": "free"}
    quota = get_user_quota(user_id)
    if quota <= 0:
        raise PermissionError("Scan quota exceeded")
    _conn().table("scans").insert({
        "user_id": user_id,
        "input_text": (input_text or "")[:10000],
        "risky_words_found": findings,
    }).execute()
    _conn().table("users").update({"quota_used": int(user.get("quota_used", 0) or 0) + 1}).eq("psid", user_id).execute()


def iter_users() -> Generator[Dict[str, Any], None, None]:
    response = _conn().table("users").select("*").execute()
    for row in response.data or []:
        yield _user_compat(row) or {}
