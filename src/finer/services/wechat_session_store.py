"""WeChat Session Store — In-memory login session management with state machine.

Manages QR login sessions for WeChat official account authentication.
Each session follows a deterministic state machine:
    created → qr_ready → waiting_scan → scanned → confirmed | expired | failed
"""

from __future__ import annotations

import base64
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LoginState(str, Enum):
    """Login session state."""
    CREATED = "created"
    QR_READY = "qr_ready"
    WAITING_SCAN = "waiting_scan"
    SCANNED = "scanned"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    FAILED = "failed"


# Valid state transitions
_TRANSITIONS: dict[LoginState, set[LoginState]] = {
    LoginState.CREATED: {LoginState.QR_READY, LoginState.FAILED},
    LoginState.QR_READY: {LoginState.WAITING_SCAN, LoginState.SCANNED, LoginState.CONFIRMED, LoginState.EXPIRED, LoginState.FAILED},
    LoginState.WAITING_SCAN: {LoginState.SCANNED, LoginState.CONFIRMED, LoginState.EXPIRED, LoginState.FAILED},
    LoginState.SCANNED: {LoginState.CONFIRMED, LoginState.EXPIRED, LoginState.FAILED},
    LoginState.CONFIRMED: set(),
    LoginState.EXPIRED: set(),
    LoginState.FAILED: set(),
}


@dataclass
class LoginSession:
    """A single login session with state machine."""
    session_id: str
    state: LoginState = LoginState.CREATED
    exporter_session_id: Optional[str] = None
    qr_image_bytes: Optional[bytes] = None
    qr_data_uri: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    login_error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + self.ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_terminal(self) -> bool:
        return self.state in (LoginState.CONFIRMED, LoginState.EXPIRED, LoginState.FAILED)

    def build_qr_data_uri(self, content_type: str = "image/png") -> str:
        """Build a browser-displayable data URI from QR image bytes."""
        if self.qr_data_uri:
            return self.qr_data_uri
        if not self.qr_image_bytes:
            return ""
        b64 = base64.b64encode(self.qr_image_bytes).decode("ascii")
        self.qr_data_uri = f"data:{content_type};base64,{b64}"
        return self.qr_data_uri


class WeChatSessionStore:
    """In-memory store for WeChat login sessions.

    Thread-safe for single-process use. For multi-process deployments,
    replace with Redis or similar backing store.
    """

    def __init__(self, default_ttl: int = 300):
        self._sessions: dict[str, LoginSession] = {}
        self._default_ttl = default_ttl

    def create_session(self, ttl: Optional[int] = None) -> LoginSession:
        """Create a new login session."""
        session_id = secrets.token_urlsafe(16)
        session = LoginSession(
            session_id=session_id,
            ttl_seconds=ttl or self._default_ttl,
        )
        self._sessions[session_id] = session
        logger.info(f"Created session {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[LoginSession]:
        """Get a session by ID. Returns None if not found or expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired and not session.is_terminal:
            self._transition(session, LoginState.EXPIRED, "TTL expired")
        return session

    def transition(
        self,
        session_id: str,
        new_state: LoginState,
        error: Optional[str] = None,
    ) -> LoginSession:
        """Transition a session to a new state.

        Raises:
            ValueError: If session not found or transition invalid.
        """
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        self._transition(session, new_state, error)
        return session

    def _transition(
        self,
        session: LoginSession,
        new_state: LoginState,
        error: Optional[str] = None,
    ) -> None:
        allowed = _TRANSITIONS.get(session.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {session.state.value} → {new_state.value}"
            )
        session.state = new_state
        session.updated_at = time.time()
        if error:
            session.login_error = error
        if new_state == LoginState.EXPIRED:
            session.login_error = error or "Session expired"
        logger.info(f"Session {session.session_id}: {session.state.value} → {new_state.value}")

    def get_active_session(self) -> Optional[LoginSession]:
        """Get the most recent non-terminal session."""
        candidates = [
            s for s in self._sessions.values()
            if not s.is_terminal and not s.is_expired
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.updated_at)

    def get_confirmed_sessions(self) -> list[LoginSession]:
        """Get all confirmed sessions."""
        return [
            s for s in self._sessions.values()
            if s.state == LoginState.CONFIRMED
        ]

    def list_sessions(self) -> list[LoginSession]:
        """List all sessions."""
        return list(self._sessions.values())

    def remove_session(self, session_id: str) -> bool:
        """Remove a session. Returns True if found."""
        return self._sessions.pop(session_id, None) is not None

    def purge_expired(self) -> int:
        """Remove expired terminal sessions. Returns count removed."""
        to_remove = [
            sid for sid, s in self._sessions.items()
            if s.is_terminal and s.is_expired
        ]
        for sid in to_remove:
            del self._sessions[sid]
        return len(to_remove)
