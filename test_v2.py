"""Tests for fb-planner-audit core modules."""
from __future__ import annotations

from typing import Any, Dict

import pytest

from core.precheck import scan_text, _load_risky_words
from core.audit import check_text_risk, generate_plan, run_audit
from core.qpay import create_invoice, verify_webhook
from core.models import Settings, RiskScanResult


@pytest.fixture
def risky_words() -> Dict[str, Any]:
    return _load_risky_words()


class TestPrecheck:
    def test_empty_text_returns_zero_risk(self) -> None:
        result = scan_text("")
        assert result["risk_score"] == 0
        assert result["status"] == "ok"

    def test_clean_text_returns_low_risk(self) -> None:
        result = scan_text("энд аюулгүй текстийг бичье")
        assert result["risk_score"] == 0
        assert result["status"] == "ok"

    def test_risky_mongolian_word_detected(self, risky_words: Dict[str, Any]) -> None:
        text = "энэ бүтээгдэхүүн нь үнэгүй мөнгө өгдөг"
        result = scan_text(text)
        assert result["risk_score"] > 0
        assert any("үнэгүй" in str(r).lower() for r in result.get("reasons", []))

    def test_risky_english_word_detected(self) -> None:
        text = "get rich quick with free money"
        result = scan_text(text)
        assert result["risk_score"] > 0

    def test_negation_reduces_score(self) -> None:
        text = "энд үнэгүй мөнгө байхгүй"
        result = scan_text(text)
        assert result["risk_score"] < 100

    def test_score_between_0_and_100(self) -> None:
        for text in ["", "clean text", "үнэгүй", "free money guaranteed"]:
            result = scan_text(text)
            assert 0 <= result["risk_score"] <= 100

    def test_returns_required_keys(self) -> None:
        result = scan_text("test text")
        assert "risk_score" in result
        assert "reasons" in result
        assert "status" in result


class TestAudit:
    def test_check_text_risk_returns_dict(self) -> None:
        result = check_text_risk("test")
        assert isinstance(result, dict)
        assert "risk_level" in result
        assert "score" in result

    def test_generate_plan_returns_markdown(self) -> None:
        plan = generate_plan("test_page")
        assert isinstance(plan, str)
        assert "# Marketing Plan" in plan
        assert "test_page" in plan

    def test_run_audit_returns_audit_result(self) -> None:
        result = run_audit("https://example.com")
        assert isinstance(result, dict)
        assert "risk_score" in result
        assert "issues" in result
        assert "checked_at" in result

    def test_run_audit_without_url(self) -> None:
        result = run_audit("")
        assert result["risk_score"] == 0
        assert len(result["issues"]) > 0


class TestQPay:
    def test_create_invoice_uses_real_qpay_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from core import qpay
        monkeypatch.setattr(qpay, "_credentials", lambda: ("client", "secret", "invoice-code"))
        monkeypatch.setattr(qpay, "_api_post", lambda path, payload: {
            "invoice_id": "qpay-123", "qr_image": "base64qr", "qPay_shortUrl": "https://qpay.mn/i/123", "urls": []
        })
        invoice = create_invoice(9900, "Starter plan", user_id="user123", plan="starter")
        assert invoice["amount"] == 9900
        assert invoice["currency"] == "MNT"
        assert invoice["invoice_id"] == "qpay-123"
        assert invoice["qpay_short_url"] == "https://qpay.mn/i/123"
        assert invoice["status"] == "pending"

    def test_create_invoice_rejects_invalid_amount(self) -> None:
        with pytest.raises(ValueError, match="amount"):
            create_invoice(0, "Starter")

    def test_create_invoice_requires_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from core import qpay
        monkeypatch.delenv("QPAY_CLIENT_ID", raising=False)
        monkeypatch.delenv("QPAY_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("QPAY_INVOICE_CODE", raising=False)
        with pytest.raises(qpay.QPayError, match="must be configured"):
            create_invoice(9900, "Starter")

    def test_verify_webhook_no_secret(self) -> None:
        assert verify_webhook({"timestamp": 12345}, "sig", secret="") is False

    def test_verify_webhook_replay_protection(self) -> None:
        assert verify_webhook({"timestamp": 0}, "sig", secret="secret") is False

    def test_verify_webhook_valid_hmac(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import hashlib
        import hmac
        import json
        import time
        payload = {"timestamp": int(time.time()), "invoice_id": "inv-1"}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(b"test-secret", canonical.encode(), hashlib.sha256).hexdigest()
        assert verify_webhook(payload, signature, secret="test-secret") is True
        assert verify_webhook(payload, "invalid", secret="test-secret") is False


class TestModels:
    def test_settings_defaults(self) -> None:
        settings = Settings()
        assert settings.app.name == "fb-planner-audit"
        assert settings.fb.verify_token == "fbplanneraudit_verify"
        assert settings.storage.db_path == "data/app.db"

    def test_risk_scan_result_validation(self) -> None:
        result = RiskScanResult(risk_score=50, reasons=["test"], status="ok")
        assert result.risk_score == 50
        assert result.status == "ok"

    def test_risk_scan_result_score_bounds(self) -> None:
        with pytest.raises(Exception):
            RiskScanResult(risk_score=101, reasons=[], status="ok")
