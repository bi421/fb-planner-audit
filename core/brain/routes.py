from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from .decide import decide_next_reel
from .research import BrainResearcher

# NOTE: Avoid leaking exception messages to clients.



brain_bp = Blueprint("brain", __name__, url_prefix="/brain")


@brain_bp.route("/decide", methods=["POST"])
def brain_decide():
    if request.content_length and request.content_length > 10000:
        return jsonify({"ok": False, "error": "payload_too_large"}), 413

    try:
        data = request.get_json(silent=True) or {}
        decision = decide_next_reel(data)
        return jsonify({"ok": True, "decision": decision})
    except Exception:
        return jsonify({"ok": False, "error": "internal_error"}), 500


@brain_bp.route("/research/status", methods=["GET"])
def brain_research_status():
    try:
        results = BrainResearcher().run_all()
        return jsonify({"ok": True, "research": results})
    except Exception:
        return jsonify({"ok": False, "error": "internal_error"}), 500


@brain_bp.route("/health", methods=["GET"])
def brain_health():
    return jsonify({"ok": True, "service": "brain", "status": "ready"})

