"""SQLite database layer for fb-planner-v2."""
import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional

from core.config import get

logger = logging.getLogger(__name__)

DB_PATH = get("storage.db_path", "data/app.db")


def _conn():
    """Return a connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
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
    """
    with _conn() as con:
        con.executescript(schema)
    logger.info("Database initialised at %s", DB_PATH)


def get_user(psid: str) -> Optional[dict]:
    """Return user row dict or None."""
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (psid,)).fetchone()
        return dict(row) if row else None


def upsert_user(psid: str, **kwargs):
    """Insert or update a user record."""
    user = get_user(psid)
    if user is None:
        cols = ["id"] + list(kwargs.keys())
        vals = [psid] + list(kwargs.values())
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT INTO users ({','.join(cols)}) VALUES ({placeholders})"
    else:
        sets = ",".join(f"{k} = ?" for k in kwargs.keys())
        sql = f"UPDATE users SET {sets} WHERE id = ?"
        vals = list(kwargs.values()) + [psid]
    with _conn() as con:
        con.execute(sql, vals)
    logger.debug("User %s upserted", psid)


def save_audit(user_id: str, **kwargs) -> int:
    """Insert an audit row and return the new id."""
    cols = ["user_id"] + list(kwargs.keys())
    vals = [user_id] + list(kwargs.values())
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO audits ({','.join(cols)}) VALUES ({placeholders})"
    with _conn() as con:
        cur = con.execute(sql, vals)
        return cur.lastrowid


def get_user_subscription(psid: str) -> Optional[dict]:
    """Return subscription row or None."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (psid,),
        ).fetchone()
        return dict(row) if row else None


def set_pro(psid: str, plan: str, days: int):
    """Activate a pro subscription for the given user."""
    now = datetime.utcnow()
    expires = now + timedelta(days=days)
    with _conn() as con:
        con.execute(
            "INSERT INTO subscriptions (user_id, is_pro, plan, started_at, expires_at) "
            "VALUES (?, 1, ?, ?, ?)",
            (psid, plan, now.isoformat(), expires.isoformat()),
        )
    logger.info("PRO activated for %s, plan=%s, expires=%s", psid, plan, expires.isoformat())
