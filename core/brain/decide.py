from __future__ import annotations

from typing import Any, Dict, List

from .research import BrainResearcher
from .synthesize import synthesize
from .timing import smart_random_schedule, to_delay_ms


def decide_next_reel(payload: Dict) -> Dict:
    page_id = payload.get("page_id")
    last_reels = payload.get("last_reels")

    if not isinstance(last_reels, list):
        last_reels = []

    researcher = BrainResearcher()
    researches: List[Dict[str, Any]] = researcher.run_all(page_id=page_id, last_reels=last_reels)

    synth = synthesize(researches)

    publish_at = smart_random_schedule(best_hour=int(synth.get("best_hour", 19)))
    delay_ms = to_delay_ms(publish_at)

    fatigue = bool(synth.get("fatigue", False))
    template = synth.get("template_suggestion", "proven_hook_v1")
    must_change = synth.get(
        "must_change_suggestion", ["first_frame_text"]
    )


    return {
        "action": "create_reel",
        "template": template,
        "publish_at": publish_at.isoformat(),
        "delay_ms": delay_ms,
        "window": synth.get("best_window", "19:00-21:00"),
        "is_randomized": True,
        "must_change": must_change,
        "must_avoid_terms": synth.get("must_avoid_terms", []),
        "reason": synth.get("reason", ""),
        "confidence": synth.get("confidence", 0.3),
        "research_snapshot": researches,
        "human_approvable": True,
    }

