from __future__ import annotations

from typing import Dict, List


def synthesize(research_results: List[Dict]) -> Dict:
    policy: Dict = {}
    timing: Dict = {}
    creative: Dict = {}

    for item in research_results or []:
        if not isinstance(item, dict):
            continue
        src = item.get("source")
        if src == "policy":
            policy = item
        elif src == "timing":
            timing = item
        elif src == "creative":
            creative = item

    must_avoid_terms = policy.get("risky_terms", [])
    if not isinstance(must_avoid_terms, list):
        must_avoid_terms = []

    best_hour = timing.get("best_hour", 19)
    best_window = timing.get("best_window", "19:00-21:00")

    fatigue = bool(creative.get("fatigue", False))

    action_hint = "change_template" if fatigue else "keep_template"

    must_change_suggestion = (
        ["first_frame_text", "first_frame_image", "cta"]
        if fatigue
        else ["first_frame_text"]
    )

    template_suggestion = "question_hook_v2" if fatigue else "proven_hook_v1"


    summaries: List[str] = []
    for d in (policy, timing, creative):
        s = d.get("summary")
        if isinstance(s, str) and s.strip():
            summaries.append(s.strip())

    must_avoid_preview: List[str] = must_avoid_terms[:3]
    must_avoid_part = f"Must avoid: {', '.join(must_avoid_preview)}" if must_avoid_preview else "Must avoid: none"

    reason = " | ".join(summaries + [must_avoid_part])

    confidences: List[float] = []
    for d in (policy, timing, creative):
        c = d.get("confidence")
        if isinstance(c, (int, float)):
            confidences.append(float(c))

    confidence = sum(confidences) / len(confidences) if confidences else 0.3

    return {
        "best_hour": best_hour,
        "best_window": best_window,
        "must_avoid_terms": must_avoid_terms,
        "action_hint": action_hint,
        "must_change_suggestion": must_change_suggestion,
        "template_suggestion": template_suggestion,
        "fatigue": fatigue,

        "reason": reason,
        "confidence": confidence,
    }

