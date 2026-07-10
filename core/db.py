"""SQLite database layer for fb-planner-audit."""
from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, Optional

from core.config import get

logger = logging.getLogger(__name__)

DB_PATH: str = get("storage.db_path", "data/app.db")
_ALLOWED_TABLES = frozenset({"users", "audits", "subscriptions", "usage"})
_DEFAULT_TIMEOUT = 30


def _db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, DB_PATH)


def _conn() -> sqlite3.Connection:
    """Return a connection with row factory."""
    os.makedirs(os.path.dirname(_db_path()), exist_ok=True)
    con = sqlite3.connect(_db_path(), timeout=_DEFAULT_TIMEOUT)
    con.row_factory = sqlite3.Row
    return con


def _get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    con = _conn()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they do not exist."""
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        page_id TEXT,
        page_name TEXT,
        page_token TEXT,
        last_audit_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        url TEXT,
        risk_score INTEGER,
        issues_json TEXT,
        pdf_url TEXT,
        checked_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        is_pro INTEGER DEFAULT 0,
        plan TEXT,
        started_at TEXT,
        expires_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
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
    with _conn() as con:
        con.executescript(schema)
    logger.info("Database initialised at %s", _db_path())


def get_user(psid: str) -> Optional[Dict[str, Any]]:
    """Return user row dict or None."""
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (psid,)).fetchone()
        return dict(row) if row else None


def upsert_user(psid: str, **kwargs: Any) -> None:
    """Insert or update a user record."""
    if not psid:
        raise ValueError("psid must not be empty")
    allowed = {"page_id", "page_name", "page_token", "last_audit_at"}
    for k in kwargs:
        if k not in allowed:
            raise ValueError(f"Invalid user field: {k}")

    user = get_user(psid)
    if user is None:
        cols = ["id"] + list(kwargs.keys())
        vals: list[Any] = [psid] + list(kwargs.values())
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT INTO users ({','.join(cols)}) VALUES ({placeholders})"
    else:
        sets = ",".join(f"{k} = ?" for k in kwargs.keys())
        sql = f"UPDATE users SET {sets} WHERE id = ?"
        vals = list(kwargs.values()) + [psid]
    with _conn() as con:
        con.execute(sql, vals)
    logger.debug("User %s upserted", psid)


def save_audit(user_id: str, **kwargs: Any) -> int:
    """Insert an audit row and return the new id."""
    if not user_id:
        raise ValueError("user_id must not be empty")
    allowed = {"url", "risk_score", "issues_json", "pdf_url"}
    for k in kwargs:
        if k not in allowed:
            raise ValueError(f"Invalid audit field: {k}")

    cols = ["user_id"] + list(kwargs.keys())
    vals: list[Any] = [user_id] + list(kwargs.values())
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO audits ({','.join(cols)}) VALUES ({placeholders})"
    with _conn() as con:
        cur = con.execute(sql, vals)
        return cur.lastrowid


def get_user_subscription(psid: str) -> Optional[Dict[str, Any]]:
    """Return subscription row or None."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (psid,),
        ).fetchone()
        return dict(row) if row else None


def set_pro(psid: str, plan: str, days: int) -> None:
    """Activate a pro subscription for the given user."""
    if not psid or not plan:
        raise ValueError("psid and plan must not be empty")
    if days <= 0:
        raise ValueError("days must be positive")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)
    with _conn() as con:
        con.execute(
            "INSERT INTO subscriptions (user_id, is_pro, plan, started_at, expires_at) "
            "VALUES (?, 1, ?, ?, ?)",
            (psid, plan, now.isoformat(), expires.isoformat()),
        )
    logger.info("PRO activated for %s, plan=%s, expires=%s", psid, plan, expires.isoformat())


def iter_users() -> Generator[Dict[str, Any], None, None]:
    """Yield all users for background jobs."""
    with _conn() as con:
        rows = con.execute("SELECT * FROM users").fetchall()
        for row in rows:
            yield dict(row)
