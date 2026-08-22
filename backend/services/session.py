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
        self._lock = asyncio.Lock()

    def _sweep_locked(self) -> None:
        now = time.time()
        for sid in list(self._sessions):
            if now - self._last_seen.get(sid, now) > SESSION_TTL_SECONDS:
                self._sessions.pop(sid, None)
                self._last_seen.pop(sid, None)

    async def create(
        self, session_id: str, scenario_id: str, role_title: str = "",
        jd: Optional[dict] = None, user_id: int = 0,
    ) -> InterviewState:
        """Create a new interview session (idempotent — reuse existing session)."""
        async with self._lock:
            self._sweep_locked()
            if session_id in self._sessions:
                self._last_seen[session_id] = time.time()
                return self._sessions[session_id]
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

    async def exists(self, session_id: str) -> bool:
        return session_id in self._sessions


# Global singleton
session_manager = SessionManager()
