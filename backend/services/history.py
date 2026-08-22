"""Persistence (SQLite via aiosqlite): users + interview history."""
import json
import sqlite3
import time

import aiosqlite

_DB_PATH = None


def _row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


async def init_db(path: str):
    """Create tables and migrate the interviews table to include user_id."""
    global _DB_PATH
    _DB_PATH = path
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS interviews (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                role_title TEXT,
                company_name TEXT,
                created_at TEXT,
                overall_score REAL,
                summary TEXT,
                messages TEXT,
                report TEXT
            )
        """)
        # Migrate pre-auth databases: add the user_id column if missing.
        cursor = await db.execute("PRAGMA table_info(interviews)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "user_id" not in columns:
            await db.execute("ALTER TABLE interviews ADD COLUMN user_id INTEGER")
        await db.commit()


# ─── Users ────────────────────────────────────────────────

async def create_user(username: str, password_hash: str) -> int | None:
    """Create a user; returns the new id, or None if the username is taken."""
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            await db.commit()
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


async def get_user_by_username(username: str) -> dict | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = sqlite3.Row
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def get_user_by_id(user_id: int) -> dict | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = sqlite3.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


# ─── Interviews ───────────────────────────────────────────

async def save_interview(session_id: str, role_title: str, company_name: str,
                         messages: list, report: dict, user_id: int):
    """Persist a completed interview (transcript + report) for a user."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO interviews
            (id, user_id, role_title, company_name, created_at, overall_score, summary, messages, report)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_id,
                role_title or "面试",
                company_name or "",
                time.strftime("%Y-%m-%d %H:%M:%S"),
                report.get("overall_score"),
                report.get("summary", ""),
                json.dumps(messages, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
            ),
        )
        await db.commit()


async def list_interviews(user_id: int) -> list:
    """Return summary rows for a user's history list (newest first)."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = sqlite3.Row
        cursor = await db.execute(
            "SELECT id, role_title, company_name, created_at, overall_score, summary "
            "FROM interviews WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_interview(interview_id: str, user_id: int) -> dict | None:
    """Return a full history record owned by the user, or None."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = sqlite3.Row
        cursor = await db.execute(
            "SELECT * FROM interviews WHERE id = ? AND user_id = ?", (interview_id, user_id)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    d["messages"] = json.loads(d["messages"])
    d["report"] = json.loads(d["report"])
    return d


async def delete_interview(interview_id: str, user_id: int) -> bool:
    """Delete a user's history record; returns True if a row was removed."""
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM interviews WHERE id = ? AND user_id = ?", (interview_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def list_all_session_ids() -> set:
    """Return every interview id (all users) — used for orphan-audio cleanup."""
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM interviews")
        rows = await cursor.fetchall()
    return {r[0] for r in rows}
