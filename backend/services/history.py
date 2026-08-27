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
                report TEXT,
                jd TEXT,
                coach TEXT
            )
        """)
        # Migrate pre-auth databases: add the user_id column if missing.
        cursor = await db.execute("PRAGMA table_info(interviews)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "user_id" not in columns:
            await db.execute("ALTER TABLE interviews ADD COLUMN user_id INTEGER")
        # Migrate older rows: add the jd column if missing (keeps re-interview data).
        if "jd" not in columns:
            await db.execute("ALTER TABLE interviews ADD COLUMN jd TEXT")
        # Migrate older rows: add the coach column if missing (coach debrief).
        if "coach" not in columns:
            await db.execute("ALTER TABLE interviews ADD COLUMN coach TEXT")

        # One-time migration: assign pre-auth orphan rows (user_id IS NULL) to
        # the reserved legacy owner account so they stay visible.
        cursor = await db.execute("SELECT id FROM users WHERE username = ?", ("qqqqq",))
        row = await cursor.fetchone()
        if row:
            owner_id = row[0]
        else:
            cursor = await db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("qqqqq", "$legacy$no-login", time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            owner_id = cursor.lastrowid
        await db.execute("UPDATE interviews SET user_id = ? WHERE user_id IS NULL", (owner_id,))
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
                         messages: list, report: dict | None, user_id: int,
                         jd: dict | None = None):
    """Persist a completed interview (transcript + report) for a user.

    `report` may be None (e.g. evaluation failed) — the row is still saved
    with an empty report so the transcript is never lost.
    `jd` is the {profile, plan, candidate} payload used to run the interview,
    kept so the user can re-interview the same position later.
    """
    report = report or {}
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO interviews
            (id, user_id, role_title, company_name, created_at, overall_score, summary, messages, report, jd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(jd, ensure_ascii=False) if jd else None,
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
    d["messages"] = json.loads(d["messages"]) if d["messages"] else []
    d["report"] = json.loads(d["report"]) if d["report"] else {}
    d["jd"] = json.loads(d["jd"]) if d["jd"] else None
    d["coach"] = json.loads(d["coach"]) if d["coach"] else None
    return d


async def save_coach(interview_id: str, user_id: int, coach: dict) -> bool:
    """Persist a generated coach debrief onto an owned history record."""
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE interviews SET coach = ? WHERE id = ? AND user_id = ?",
            (json.dumps(coach, ensure_ascii=False), interview_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


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


async def list_progress(user_id: int) -> list:
    """Group a user's interviews by (role_title, company_name) for trend views.

    Returns [{"role_title", "company_name", "attempts": [
        {"id", "created_at", "overall_score", "dimension_scores"}  # oldest first
    ]}] — one entry per distinct position, attempts sorted by time.
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = sqlite3.Row
        cursor = await db.execute(
            "SELECT id, role_title, company_name, created_at, overall_score, report "
            "FROM interviews WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        rows = await cursor.fetchall()
    groups: dict[tuple, dict] = {}
    for row in rows:
        d = _row_to_dict(row)
        report = json.loads(d["report"]) if d["report"] else {}
        key = (d.get("role_title") or "面试", d.get("company_name") or "")
        group = groups.setdefault(key, {
            "role_title": key[0],
            "company_name": key[1],
            "attempts": [],
        })
        group["attempts"].append({
            "id": d["id"],
            "created_at": d["created_at"],
            "overall_score": d["overall_score"],
            "dimension_scores": report.get("dimension_scores") or {},
        })
    return list(groups.values())
