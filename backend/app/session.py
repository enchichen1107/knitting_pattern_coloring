"""In-memory session store with TTL eviction.

A session caches the uploaded image bytes and the classification grid so
that /colorize can render fast without re-uploading or re-classifying.

Swap this dict for Redis when going multi-user — no caller changes.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field


SESSION_TTL_SECONDS = 60 * 60  # 1 hour idle eviction


@dataclass
class Session:
    image_bytes: bytes
    rows: int
    cols: int
    symbols: int
    labels: list[str]
    grid: list[list[str]]
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self, ttl_seconds: float = SESSION_TTL_SECONDS) -> None:
        self._sessions: dict[str, Session] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def create(self, session: Session) -> str:
        sid = uuid.uuid4().hex
        with self._lock:
            self._sweep_locked()
            self._sessions[sid] = session
        return sid

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            self._sweep_locked()
            s = self._sessions.get(session_id)
            if s is not None:
                s.last_used_at = time.time()
            return s

    def _sweep_locked(self) -> None:
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_used_at > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]


# Module-level singleton — fine for single-process uvicorn.
store = SessionStore()
