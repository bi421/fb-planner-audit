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
    def test_create_invoice_basic(self) -> None:
        invoice = create_invoice("user123", "basic")
        assert invoice["amount"] == 9
        assert invoice["currency"] == "USD"
        assert invoice["plan"] == "basic"
        assert invoice["status"] == "pending"

    def test_create_invoice_pro(self) -> None:
        invoice = create_invoice("user123", "pro")
        assert invoice["amount"] == 29

    def test_create_invoice_invalid_plan(self) -> None:
        with pytest.raises(ValueError, match="Invalid plan"):
            create_invoice("user123", "invalid")

    def test_create_invoice_empty_user_id(self) -> None:
        with pytest.raises(ValueError, match="user_id must not be empty"):
            create_invoice("", "pro")

    def test_verify_webhook_no_secret(self) -> None:
        result = verify_webhook({"timestamp": 12345}, "sig", secret="")
        assert result is False

    def test_verify_webhook_replay_protection(self) -> None:
        old_payload = {"timestamp": 0}
        result = verify_webhook(old_payload, "sig", secret="secret")
        assert result is False


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
