from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
RISKY_PATH = REPO_ROOT / "data" / "risky_words.json"

_policy_cache: Dict[str, Any] = {"data": None, "expires_at": 0}


def get_cached_policies() -> Tuple[Dict[str, Any], bool]:
    """Return cached risky_words.json content.

    Cache TTL: 6 hours.
    - If cache is fresh, return cached data.
    - If cache is stale, attempt policy_updater.update() then reload file.
    - On update failure, return old cache if available.

    Returns: (data, is_from_cache)
    """

    global _policy_cache

    ttl_seconds = 6 * 60 * 60  # 21600
    now = time.time()

    cached_data = _policy_cache.get("data")
    expires_at = float(_policy_cache.get("expires_at") or 0)

    # Fresh cache
    if cached_data is not None and now < expires_at:
        return cached_data, True

    try:
        # Lazy import to avoid overhead at module import time
        from core import policy_updater  # type: ignore

        # Update remote sources and persist data/risky_words.json
        policy_updater.update()

        # Reload file after update
        try:
            with open(RISKY_PATH, "r", encoding="utf-8") as fh:
                raw = json.load(fh) or {}
        except FileNotFoundError:
            raw = {}

        # Store in cache
        _policy_cache["data"] = raw
        _policy_cache["expires_at"] = now + ttl_seconds
        return raw, False
    except Exception:
        # Fall back to old cached data (if any)
        if cached_data is not None:
            return cached_data, True
        # No cache available
        return {}, True


class BrainResearcher:
    def policy_research(self) -> Dict[str, Any]:
        """Research risky terms from the latest fetched policies."""
        try:
            raw, _from_cache = get_cached_policies()

            risky_terms: List[str] = []
            for key in ("mn_high", "en_high", "mn_medium"):
                terms = raw.get(key, [])
                if isinstance(terms, list):
                    risky_terms.extend([str(x) for x in terms])

            # Deduplicate while preserving first-seen order
            seen: set[str] = set()
            deduped: List[str] = []
            for t in risky_terms:
                if t in seen:
                    continue
                seen.add(t)
                deduped.append(t)

            return {
                "source": "policy",
                "risky_terms": deduped,
                "summary": f"Collected {len(deduped)} risky terms from policy sources.",
                "confidence": 0.8,
            }
        except Exception:
            return {
                "source": "policy",
                "risky_terms": [],
                "summary": "Policy research failed; using fallback.",
                "confidence": 0.3,
            }

    def timing_research(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Infer best posting hour using recent audit history."""
        try:
            from core.db import _conn  # type: ignore

            con = _conn()
            try:
                rows = con.execute(
                    "SELECT checked_at FROM audits ORDER BY checked_at DESC LIMIT 50"
                ).fetchall()
            finally:
                con.close()

            best_hour = 19
            if rows:
                hours: List[int] = []
                for r in rows:
                    val = r[0]
                    if not val:
                        continue
                    try:
                        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                        hours.append(dt.hour)
                    except Exception:
                        continue

                if hours:
                    freq: Dict[int, int] = {}
                    for h in hours:
                        freq[h] = freq.get(h, 0) + 1
                    best_hour = max(freq.items(), key=lambda x: x[1])[0]

            best_window = f"{best_hour:02d}:00-{(best_hour + 2) % 24:02d}:00"

            return {
                "source": "timing",
                "best_hour": best_hour,
                "best_window": best_window,
                "summary": f"Suggested best hour based on recent audits: {best_hour}:00.",
                "confidence": 0.65,
            }
        except Exception:
            return {
                "source": "timing",
                "best_hour": 19,
                "best_window": "19:00-21:00",
                "summary": "Timing research failed; using fallback window.",
                "confidence": 0.3,
            }

    def creative_research(self, last_reels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Detect creative fatigue by counting duplicate first_frame_hash values."""
        try:
            if not last_reels:
                return {
                    "source": "creative",
                    "fatigue": False,
                    "summary": "No recent reels provided.",
                    "confidence": 0.55,
                }

            hashes: List[str] = []
            if isinstance(last_reels, list):
                for r in last_reels:
                    if not isinstance(r, dict):
                        continue
                    h = r.get("first_frame_hash")
                    if h is None:
                        continue
                    hashes.append(str(h))

            freq: Dict[str, int] = {}
            for h in hashes:
                freq[h] = freq.get(h, 0) + 1

            duplicates = sum(max(0, c - 1) for c in freq.values())
            fatigue = duplicates > 3

            return {
                "source": "creative",
                "fatigue": fatigue,
                "summary": "Duplicate-first-frame detection based on last reels.",
                "confidence": 0.6 if fatigue else 0.7,
            }
        except Exception:
            return {
                "source": "creative",
                "fatigue": False,
                "summary": "Creative research failed; using fallback.",
                "confidence": 0.3,
            }

    def run_all(
        self, page_id: Optional[str] = None, last_reels: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        try:
            return [
                self.policy_research(),
                self.timing_research(page_id=page_id),
                self.creative_research(last_reels=last_reels),
            ]
        except Exception:
            return [
                self.policy_research(),
                {
                    "source": "timing",
                    "best_hour": 19,
                    "best_window": "19:00-21:00",
                    "summary": "Timing research failed; using fallback.",
                    "confidence": 0.3,
                },
                self.creative_research(last_reels=last_reels),
            ]

