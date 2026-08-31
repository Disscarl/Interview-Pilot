"""Session management — in-memory store for active interviews.

Sessions are kept alive across a brief disconnect so the client can reconnect
and resume; stale sessions are swept on `create` after a TTL to avoid leaks.
"""
import asyncio
import time
from typing import Dict, Optional

from models.interview import InterviewState

SESSION_TTL_SECONDS = 600  # keep an abandoned session for reconnect this long


class SessionManager:
    """Thread-safe in-memory session store with TTL cleanup."""

    def __init__(self):
        self._sessions: Dict[str, InterviewState] = {}
        self._last_seen: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    def _sweep_locked(self) -> None:
        now = time.time()
        for sid in list(self._sessions):
            if now - self._last_seen.get(sid, now) > SESSION_TTL_SECONDS:
                self._sessions.pop(sid, None)
                self._last_seen.pop(sid, None)
                self._locks.pop(sid, None)

    async def get_lock(self, session_id: str) -> asyncio.Lock:
        """Return the per-session lock used to serialize graph writes (L10).

        Two connections to the same session (two tabs, or a reconnect racing
        the old socket) would otherwise mutate shared state concurrently.
        """
        async with self._lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock

    async def create(
        self, session_id: str, scenario_id: str, role_title: str = "",
        jd: Optional[dict] = None, user_id: int = 0,
    ) -> Optional[InterviewState]:
        """Create a new interview session (idempotent — reuse existing session).

        Returns None if the session already exists but belongs to a different
        user (prevents cross-user hijack of an in-progress interview).
        """
        async with self._lock:
            self._sweep_locked()
            existing = self._sessions.get(session_id)
            if existing is not None:
                if existing.user_id != user_id:
                    return None
                self._last_seen[session_id] = time.time()
                return existing
            state = InterviewState(
                session_id=session_id,
                scenario_id=scenario_id,
                user_id=user_id,
                role_title=role_title,
                jd_profile=(jd or {}).get("profile"),
                jd_plan=(jd or {}).get("plan"),
                candidate_profile=(jd or {}).get("candidate"),
            )
            self._sessions[session_id] = state
            self._last_seen[session_id] = time.time()
            return state

    async def get(self, session_id: str) -> Optional[InterviewState]:
        """Get an existing session, refreshing its last-seen timestamp."""
        state = self._sessions.get(session_id)
        if state is None:
            return None
        self._last_seen[session_id] = time.time()
        return state

    async def delete(self, session_id: str):
        """Remove a session."""
        async with self._lock:
            self._sessions.pop(session_id, None)
            self._last_seen.pop(session_id, None)
            self._locks.pop(session_id, None)

    async def exists(self, session_id: str) -> bool:
        return session_id in self._sessions


# Global singleton
session_manager = SessionManager()
