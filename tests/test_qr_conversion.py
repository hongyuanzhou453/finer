"""Tests for QR code bytes-to-data-URI conversion."""

import base64
import pytest
from finer.services.wechat_session_store import LoginSession


class TestQRConversion:
    def test_bytes_to_data_uri_png(self):
        session = LoginSession(session_id="test")
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        session.qr_image_bytes = raw
        uri = session.build_qr_data_uri(content_type="image/png")
        assert uri.startswith("data:image/png;base64,")
        b64_part = uri.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert decoded == raw

    def test_bytes_to_data_uri_jpeg(self):
        session = LoginSession(session_id="test")
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        session.qr_image_bytes = raw
        uri = session.build_qr_data_uri(content_type="image/jpeg")
        assert uri.startswith("data:image/jpeg;base64,")

    def test_empty_bytes_returns_empty(self):
        session = LoginSession(session_id="test")
        assert session.build_qr_data_uri() == ""

    def test_none_bytes_returns_empty(self):
        session = LoginSession(session_id="test")
        session.qr_image_bytes = None
        assert session.build_qr_data_uri() == ""

    def test_preserves_content(self):
        session = LoginSession(session_id="test")
        # Meaningful content
        content = b"<svg>test qr</svg>"
        session.qr_image_bytes = content
        uri = session.build_qr_data_uri(content_type="image/svg+xml")
        b64_part = uri.split(",", 1)[1]
        assert base64.b64decode(b64_part) == content

    def test_large_image(self):
        session = LoginSession(session_id="test")
        # Simulate a large QR image (10KB)
        raw = bytes(range(256)) * 40
        session.qr_image_bytes = raw
        uri = session.build_qr_data_uri()
        b64_part = uri.split(",", 1)[1]
        assert base64.b64decode(b64_part) == raw
