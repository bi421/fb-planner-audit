"""Text precheck and risky-word scanning for fb-planner-audit."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "data", "app.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _ensure_usage_table() -> None:
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                plan TEXT,
                action TEXT,
                usage_type TEXT,
                meta_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )


def _load_risky_words() -> Dict[str, List[str]]:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "data", "risky_words.json")

    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        if any(k in raw for k in ("mn_high", "mn_medium", "en_high")):
            mn_high = raw.get("mn_high") or []
            mn_medium = raw.get("mn_medium") or []
            en_high = raw.get("en_high") or []
            mn = [str(x).strip() for x in (mn_high + mn_medium) if str(x).strip()]
            en = [str(x).strip() for x in en_high if str(x).strip()]
            return {"mongolian": mn, "english": en}

        mongolian = raw.get("mongolian") or raw.get("mongol") or []
        english = raw.get("english") or raw.get("eng") or []
        mongolian = [str(x).strip() for x in mongolian if str(x).strip()]
        english = [str(x).strip() for x in english if str(x).strip()]
        return {"mongolian": mongolian, "english": english}

    if isinstance(raw, list):
        words = [str(x).strip() for x in raw if str(x).strip()]
        return {"mongolian": words, "english": words}

    raise ValueError("Unexpected risky_words.json format")


_RISKY: Optional[Dict[str, List[str]]] = None


def _get_risky_lists() -> Dict[str, List[str]]:
    global _RISKY
    if _RISKY is None:
        _RISKY = _load_risky_words()
    return _RISKY


_NEGATIONS = ["биш", "not", "no", "never", "don't", "doesn't", "can't", "cannot"]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[\wа-яөүё']+", text, flags=re.IGNORECASE)


def _is_negation_token(tok: str) -> bool:
    tok_norm = _normalize_text(tok)
    return tok_norm in set(_normalize_text(x) for x in _NEGATIONS)


def scan_text(text: str) -> Dict[str, Any]:
    """Scan text for risky words and return risk assessment."""
    normalized = _normalize_text(text)
    if not normalized:
        return {"risk_score": 0, "reasons": [], "status": "ok"}

    risky = _get_risky_lists()
    mongolian_terms = risky.get("mongolian", [])
    english_terms = risky.get("english", [])

    tokens = _tokenize(normalized)

    mong_set = set(t.lower() for t in mongolian_terms if t)
    eng_set = set(t.lower() for t in english_terms if t)

    neg_window = 3
    hits: List[Tuple[str, str, bool]] = []

    for i, tok in enumerate(tokens):
        tok_l = tok.lower()
        is_risky = tok_l in mong_set or tok_l in eng_set
        if not is_risky:
            continue

        lang = "mongolian" if tok_l in mong_set else "english"
        start = max(0, i - neg_window)
        prev = tokens[start:i]
        is_negated = any(_is_negation_token(p) for p in prev)
        hits.append((tok_l, lang, is_negated))

    if not hits:
        return {"risk_score": 0, "reasons": [], "status": "ok"}

    base = 18
    negated_multiplier = 0.25

    raw_score = 0.0
    reasons: List[str] = []

    for term, lang, negated in hits:
        if negated:
            raw_score += base * negated_multiplier
            reasons.append(f"negated risky term ({lang}): {term}")
        else:
            raw_score += base
            reasons.append(f"risky term detected ({lang}): {term}")

    risk_score = int(max(0, min(100, round(raw_score))))
    status = "warn" if risk_score >= 40 else "ok"

    return {"risk_score": risk_score, "reasons": reasons, "status": status}


def get_user_quota(user_id: str) -> int:
    """Return remaining precheck quota for user."""
    _ensure_usage_table()

    with _conn() as con:
        sub = con.execute(
            "SELECT expires_at FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    if sub and sub["expires_at"]:
        try:
            expires_at = datetime.fromisoformat(sub["expires_at"])
            if datetime.now(timezone.utc) < expires_at:
                return 1_000_000
        except Exception:
            pass

    FREE_LIMIT = 5
    with _conn() as con:
        used = con.execute(
            "SELECT COUNT(*) as c FROM usage WHERE user_id = ? AND usage_type = 'precheck'",
            (user_id,),
        ).fetchone()["c"]

    remaining = max(0, FREE_LIMIT - int(used))
    return remaining


def _write_usage(user_id: str, plan: str, action: str, usage_type: str, meta: Optional[dict] = None) -> None:
    _ensure_usage_table()

    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    with _conn() as con:
        con.execute(
            "INSERT INTO usage (user_id, plan, action, usage_type, meta_json, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (user_id, plan, action, usage_type, meta_json),
        )


def record_precheck_usage(user_id: str, plan: str = "", meta: Optional[dict] = None) -> None:
    """Record a precheck usage event."""
    _write_usage(user_id=user_id, plan=plan, action="scan_text", usage_type="precheck", meta=meta)


def check_quota_and_scan(user_id: str, text: str) -> Dict[str, Any]:
    """Check quota and scan text if allowed."""
    quota = get_user_quota(user_id)
    if quota <= 0:
        return {"status": "paid_required", "message": "Төлбөр төлнө үү"}

    plan = ""
    with _conn() as con:
        sub = con.execute(
            "SELECT plan FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if sub and sub["plan"]:
        plan = sub["plan"]

    record_precheck_usage(user_id=user_id, plan=plan, meta={"quota_before": quota})
    return scan_text(text)
