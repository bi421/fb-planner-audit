"""Text precheck and metadata-rich risky-claim scanning."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from core import db

_RISKY: list[dict[str, Any]] | None = None
_NEGATIONS = ("биш", "not", "no", "never", "don't", "doesn't", "can't", "cannot")
_DEFAULT_POLICY = "https://transparency.meta.com/policies/ad-standards/"


def _load_risky_words() -> list[dict[str, Any]]:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "risky_words.json")
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    entries: list[dict[str, Any]] = []
    if isinstance(raw, list):
        source = raw
    elif isinstance(raw, dict) and isinstance(raw.get("entries"), list):
        source = raw["entries"]
    elif isinstance(raw, dict):
        source = []
        for key, lang, severity in (
            ("mn_high", "mn", "high"), ("mn_medium", "mn", "medium"),
            ("en_high", "en", "high"), ("en_medium", "en", "medium"),
            ("mongolian", "mn", "medium"), ("english", "en", "medium"),
        ):
            for value in raw.get(key, []) or []:
                source.append({"word": value, "lang": lang, "severity": severity})
    else:
        raise ValueError("Unexpected risky_words.json format")
    for item in source:
        if isinstance(item, str):
            item = {"word": item, "lang": "mn", "severity": "medium"}
        if not isinstance(item, dict) or not str(item.get("word", "")).strip():
            continue
        entries.append({
            "word": str(item["word"]).strip(),
            "lang": item.get("lang", "mn"),
            "severity": item.get("severity", "medium"),
            "policy_link": item.get("policy_link", _DEFAULT_POLICY),
            "suggestion": item.get("suggestion", "Амлалтыг баримтаар нотлогдох, төвийг сахисан хэллэгээр солино уу."),
        })
    return entries


def _get_risky_words() -> list[dict[str, Any]]:
    global _RISKY
    if _RISKY is None:
        _RISKY = _load_risky_words()
    return _RISKY


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _load_risky_lists() -> dict[str, list[str]]:
    """Compatibility helper for existing callers/tests."""
    words = _get_risky_words()
    return {
        "mongolian": [x["word"] for x in words if x["lang"] in ("mn", "mongolian")],
        "english": [x["word"] for x in words if x["lang"] in ("en", "english")],
    }


def scan_text(text: str) -> dict[str, Any]:
    """Return matched phrases with severity and actionable replacement guidance."""
    normalized = _normalize_text(text)
    if not normalized:
        return {"risk_score": 0, "reasons": [], "status": "ok", "found_words": []}
    tokens = re.findall(r"[\wа-яөүё']+", normalized, flags=re.IGNORECASE)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in _get_risky_words():
        term = _normalize_text(entry["word"])
        if not term or term in seen:
            continue
        # Phrase matching is necessary for claims such as "100% баталгаатай".
        if term not in normalized:
            continue
        seen.add(term)
        preceding = normalized[max(0, normalized.find(term) - 35):normalized.find(term)]
        negated = any(re.search(r"\b" + re.escape(n) + r"\b", preceding) for n in _NEGATIONS)
        finding = dict(entry)
        finding["matched_text"] = entry["word"]
        finding["negated_context"] = bool(negated)
        found.append(finding)
    if not found:
        return {"risk_score": 0, "reasons": [], "status": "ok", "found_words": []}
    score = min(100, sum((22 if x["severity"] == "high" else 12) * (0.25 if x["negated_context"] else 1) for x in found))
    reasons = [
        f"{'negated risky claim' if x['negated_context'] else 'risky claim detected'} ({x['lang']}): {x['word']}"
        for x in found
    ]
    return {
        "risk_score": int(round(score)),
        "reasons": reasons,
        "status": "warn" if score >= 35 else "ok",
        "found_words": found,
    }


def get_user_quota(user_id: str) -> int:
    return db.get_user_quota(user_id)


def record_precheck_usage(user_id: str, plan: str = "", meta: dict | None = None) -> None:
    # Legacy API retained; scans are now persisted in the durable scans table.
    db.record_scan(user_id, str((meta or {}).get("input_text", "")), [])


def check_quota_and_scan(user_id: str, text: str) -> dict[str, Any]:
    quota = get_user_quota(user_id)
    if quota <= 0:
        return {"status": "paid_required", "message": "Таны шалгах эрх дууссан. Үргэлжлүүлэхийн тулд багцаа сонгоно уу."}
    result = scan_text(text)
    db.record_scan(user_id, text, result.get("found_words", []))
    result["quota_remaining"] = max(0, quota - 1)
    return result
