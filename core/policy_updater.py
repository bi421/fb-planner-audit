import json
import logging
import re
from dataclasses import dataclass
from typing import List, Tuple

import requests

from core.config import get

logger = logging.getLogger(__name__)


@dataclass
class PolicySource:
    name: str
    url: str


SOURCES: List[PolicySource] = [
    PolicySource(name="frc", url="https://www.frc.mn"),
    PolicySource(name="meta", url="https://transparency.meta.com"),
]


def _safe_read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _safe_write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _extract_words_from_html(html: str, *, min_len: int = 2) -> List[str]:
    """Very lightweight word extraction fallback.

    If the policy sources use complex pages, parsing may fail; in that case we return
    an empty list.
    """

    if not html:
        return []

    # Extract Mongolian/English-ish quoted terms.
    candidates = set()

    # quotes: "..." or '...'
    for m in re.finditer(r"[\"']([^\"']{min_len,80})[\"']", html):
        pass

    # Simpler fallback: gather long tokens that look like phrases.
    tokens = re.findall(r"[A-Za-zА-Яа-яөүёЁ0-9][A-Za-zА-Яа-яөүёЁ0-9\s\-]{2,60}", html)
    for t in tokens:
        s = " ".join(t.split()).strip()
        if len(s) < min_len:
            continue
        # discard obvious nav/UI noise
        if any(x in s.lower() for x in ["privacy", "terms", "cookie", "contact", "about"]):
            continue
        candidates.add(s)

    return sorted(candidates)


def _merge_policy_words(existing: dict, new_words: List[str], *, version: str) -> dict:
    """Merge new words into existing data.

    Maps extracted tokens to mn_high/en_high/ mn_medium using a heuristic.
    """

    mn_high = existing.get("mn_high", [])
    mn_medium = existing.get("mn_medium", [])
    en_high = existing.get("en_high", [])

    # heuristic: if contains Mongolian letters -> mn
    for w in new_words:
        lw = w.lower()
        if re.search(r"[а-яөүё]", lw):
            # decide high vs medium by presence of money/guarantee indicators
            if any(x in lw for x in ["free", "баталгаатай", "баталгаатай", "guaranteed", "profit", "мөнгө", "хурдан"]):
                mn_high.append(w)
            else:
                mn_medium.append(w)
        elif re.search(r"[a-z]", lw):
            en_high.append(w)

    # de-dup preserve order
    def dedup(seq: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    updated = {
        "mn_high": dedup(mn_high),
        "mn_medium": dedup(mn_medium),
        "en_high": dedup(en_high),
        "version": version,
        "source": existing.get("source", "policy_updater"),
    }

    return updated


def update() -> Tuple[int, int]:
    """Fetch policy sources, extract risky words, and update data/risky_words.json.

    Returns: (added_count, attempted_sources_count)
    """

    base_dir = __file__.rsplit("/", 1)[0].rsplit("\\", 1)[-1]
    # determine repo root from this file location
    # core/policy_updater.py -> fb-planner-v2
    import os

    repo_root = os.path.dirname(os.path.dirname(__file__))
    json_path = os.path.join(repo_root, "data", "risky_words.json")

    existing = _safe_read_json(json_path)

    attempted = 0
    extracted_all: List[str] = []

    timeout = int(get("policy_updater.timeout_seconds", 15))

    for src in SOURCES:
        attempted += 1
        try:
            r = requests.get(src.url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if not r.ok:
                logger.warning("policy updater: %s fetch failed: %s", src.name, r.status_code)
                continue
            words = _extract_words_from_html(r.text)
            extracted_all.extend(words)
        except Exception as exc:
            logger.exception("policy updater: failed to fetch %s: %s", src.name, exc)

    # de-dup
    extracted_all = sorted(set(extracted_all))

    before_total = (
        len(existing.get("mn_high", [])) + len(existing.get("mn_medium", [])) + len(existing.get("en_high", []))
    )

    version = get("policy_updater.version", "auto")
    updated = _merge_policy_words(existing, extracted_all, version=version)

    _safe_write_json(json_path, updated)

    after_total = len(updated.get("mn_high", [])) + len(updated.get("mn_medium", [])) + len(updated.get("en_high", []))
    added = max(0, after_total - before_total)

    logger.info("policy updater: attempted=%s extracted=%s added=%s", attempted, len(extracted_all), added)
    return added, attempted

