"""Pydantic models for fb-planner-audit."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str = "fb-planner-audit"
    env: str = "dev"


class FBConfig(BaseModel):
    verify_token: str = "fbplanneraudit_verify"
    app_secret: Optional[str] = None
    page_id: Optional[str] = None
    page_token: Optional[str] = None
    webhook_url: Optional[str] = None


class AdminConfig(BaseModel):
    telegram_user_id: int = 0
    telegram_bot_token: str = ""


class SchedulerConfig(BaseModel):
    interval_minutes: int = 10


class StorageConfig(BaseModel):
    db_path: str = "data/app.db"


class PolicyUpdaterConfig(BaseModel):
    timeout_seconds: int = 15
    version: str = "auto"


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    fb: FBConfig = Field(default_factory=FBConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    policy_updater: PolicyUpdaterConfig = Field(default_factory=PolicyUpdaterConfig)


class RiskScanResult(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    reasons: List[str] = Field(default_factory=list)
    status: str = "ok"
    risky_words: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class AuditIssue(BaseModel):
    type: str
    message: str


class AuditResult(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    issues: List[AuditIssue] = Field(default_factory=list)
    checked_at: str
    horizon_days: int = 30
    url: Optional[str] = None


class Invoice(BaseModel):
    amount: int
    currency: str
    invoice_id: str
    plan: str
    status: str


class UserQuota(BaseModel):
    remaining: int
    plan: str = ""
    is_pro: bool = False
