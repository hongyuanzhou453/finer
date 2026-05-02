"""Tests for WeChat session store state machine."""

import time
import pytest
from finer.services.wechat_session_store import (
    WeChatSessionStore,
    LoginSession,
    LoginState,
)


class TestLoginStateTransitions:
    def test_created_to_qr_ready(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        assert store.get_session(session.session_id).state == LoginState.QR_READY

    def test_qr_ready_to_waiting_scan(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.WAITING_SCAN)
        assert store.get_session(session.session_id).state == LoginState.WAITING_SCAN

    def test_waiting_scan_to_scanned(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.WAITING_SCAN)
        store.transition(session.session_id, LoginState.SCANNED)
        assert store.get_session(session.session_id).state == LoginState.SCANNED

    def test_scanned_to_confirmed(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.WAITING_SCAN)
        store.transition(session.session_id, LoginState.SCANNED)
        store.transition(session.session_id, LoginState.CONFIRMED)
        assert store.get_session(session.session_id).state == LoginState.CONFIRMED

    def test_qr_ready_directly_to_confirmed(self):
        """User scans and confirms between polling intervals — skip intermediate states."""
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.CONFIRMED)
        assert store.get_session(session.session_id).state == LoginState.CONFIRMED

    def test_qr_ready_directly_to_scanned(self):
        """User scans between polling intervals — skip waiting_scan."""
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.SCANNED)
        assert store.get_session(session.session_id).state == LoginState.SCANNED

    def test_waiting_scan_directly_to_confirmed(self):
        """User confirms between polling intervals — skip scanned."""
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.WAITING_SCAN)
        store.transition(session.session_id, LoginState.CONFIRMED)
        assert store.get_session(session.session_id).state == LoginState.CONFIRMED

    def test_invalid_transition_raises(self):
        store = WeChatSessionStore()
        session = store.create_session()
        with pytest.raises(ValueError, match="Invalid transition"):
            store.transition(session.session_id, LoginState.CONFIRMED)

    def test_confirmed_is_terminal(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.WAITING_SCAN)
        store.transition(session.session_id, LoginState.SCANNED)
        store.transition(session.session_id, LoginState.CONFIRMED)
        s = store.get_session(session.session_id)
        assert s.is_terminal is True

    def test_expired_is_terminal(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.EXPIRED)
        s = store.get_session(session.session_id)
        assert s.is_terminal is True

    def test_failed_from_any_non_terminal(self):
        store = WeChatSessionStore()
        session = store.create_session()
        store.transition(session.session_id, LoginState.QR_READY)
        store.transition(session.session_id, LoginState.FAILED, "test error")
        s = store.get_session(session.session_id)
        assert s.state == LoginState.FAILED
        assert s.login_error == "test error"


class TestSessionStore:
    def test_create_session(self):
        store = WeChatSessionStore()
        session = store.create_session()
        assert session.session_id
        assert session.state == LoginState.CREATED
        assert session.ttl_seconds == 300

    def test_get_session_not_found(self):
        store = WeChatSessionStore()
        assert store.get_session("nonexistent") is None

    def test_session_expiry(self):
        store = WeChatSessionStore(default_ttl=1)
        session = store.create_session(ttl=1)
        store.transition(session.session_id, LoginState.QR_READY)
        time.sleep(1.1)
        s = store.get_session(session.session_id)
        assert s.state == LoginState.EXPIRED

    def test_get_active_session(self):
        store = WeChatSessionStore()
        s1 = store.create_session()
        store.transition(s1.session_id, LoginState.QR_READY)
        s2 = store.create_session()
        store.transition(s2.session_id, LoginState.QR_READY)
        store.transition(s2.session_id, LoginState.WAITING_SCAN)
        active = store.get_active_session()
        assert active.session_id == s2.session_id

    def test_get_active_session_none_when_all_terminal(self):
        store = WeChatSessionStore()
        s1 = store.create_session()
        store.transition(s1.session_id, LoginState.QR_READY)
        store.transition(s1.session_id, LoginState.FAILED)
        assert store.get_active_session() is None

    def test_get_confirmed_sessions(self):
        store = WeChatSessionStore()
        s1 = store.create_session()
        store.transition(s1.session_id, LoginState.QR_READY)
        store.transition(s1.session_id, LoginState.WAITING_SCAN)
        store.transition(s1.session_id, LoginState.SCANNED)
        store.transition(s1.session_id, LoginState.CONFIRMED)
        confirmed = store.get_confirmed_sessions()
        assert len(confirmed) == 1
        assert confirmed[0].session_id == s1.session_id

    def test_list_sessions(self):
        store = WeChatSessionStore()
        store.create_session()
        store.create_session()
        assert len(store.list_sessions()) == 2

    def test_remove_session(self):
        store = WeChatSessionStore()
        s = store.create_session()
        assert store.remove_session(s.session_id) is True
        assert store.get_session(s.session_id) is None
        assert store.remove_session("nonexistent") is False

    def test_purge_expired(self):
        store = WeChatSessionStore(default_ttl=1)
        s = store.create_session(ttl=1)
        store.transition(s.session_id, LoginState.QR_READY)
        store.transition(s.session_id, LoginState.FAILED)
        time.sleep(1.1)
        purged = store.purge_expired()
        assert purged == 1
        assert store.get_session(s.session_id) is None


class TestLoginSessionDataclass:
    def test_qr_data_uri(self):
        session = LoginSession(session_id="test")
        session.qr_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
        uri = session.build_qr_data_uri()
        assert uri.startswith("data:image/png;base64,")

    def test_qr_data_uri_cached(self):
        session = LoginSession(session_id="test")
        session.qr_image_bytes = b"test"
        uri1 = session.build_qr_data_uri()
        uri2 = session.build_qr_data_uri()
        assert uri1 == uri2

    def test_qr_data_uri_empty(self):
        session = LoginSession(session_id="test")
        assert session.build_qr_data_uri() == ""
