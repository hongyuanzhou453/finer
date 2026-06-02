"""Tests for authentication middleware."""

from __future__ import annotations

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finer.errors import ErrorCode
from finer.api.middleware.auth import (
    AuthConfig,
    APIKeyAuthMiddleware,
    create_jwt_token,
    get_auth_config,
    setup_auth_middleware,
)


@pytest.fixture
def app_no_auth():
    """Create app with authentication disabled."""
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/protected")
    def protected():
        return {"message": "protected"}

    return app


@pytest.fixture
def app_with_api_key():
    """Create app with API key authentication."""
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/protected")
    def protected():
        return {"message": "protected"}

    @app.delete("/api/sensitive/{item_id}")
    def delete_item(item_id: str):
        return {"deleted": item_id}

    config = AuthConfig(
        enabled=True,
        api_key="test-api-key-123",
        whitelist=["/api/health", "/openapi.json"],
    )
    setup_auth_middleware(app, config)

    return app


def test_auth_disabled_by_default():
    """Test that authentication is disabled by default."""
    config = get_auth_config()
    assert config.enabled is False


def test_no_auth_allows_all(app_no_auth):
    """Test that with no auth, all endpoints are accessible."""
    client = TestClient(app_no_auth)

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    response = client.get("/api/protected")
    assert response.status_code == 200


def test_api_key_auth_requires_header(app_with_api_key):
    """Test that protected endpoints require API key."""
    client = TestClient(app_with_api_key)

    # Whitelisted endpoint should work
    response = client.get("/api/health")
    assert response.status_code == 200

    # Protected endpoint without API key should fail
    response = client.get("/api/protected")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == ErrorCode.SYS_AUTH_001.value


def test_api_key_auth_valid_key(app_with_api_key):
    """Test that valid API key allows access."""
    client = TestClient(app_with_api_key)

    response = client.get(
        "/api/protected",
        headers={"X-API-Key": "test-api-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "protected"


def test_api_key_auth_invalid_key(app_with_api_key):
    """Test that invalid API key is rejected."""
    client = TestClient(app_with_api_key)

    response = client.get(
        "/api/protected",
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["error"]["message"]


def test_delete_requires_sensitive_auth(app_with_api_key):
    """Test that DELETE operations require additional auth."""
    client = TestClient(app_with_api_key)

    # DELETE with just API key should fail
    response = client.delete(
        "/api/sensitive/test-item",
        headers={"X-API-Key": "test-api-key-123"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == ErrorCode.SYS_PERM_001.value
    assert "Sensitive operation" in response.json()["error"]["message"]

    # DELETE with sensitive auth should work
    response = client.delete(
        "/api/sensitive/test-item",
        headers={
            "X-API-Key": "test-api-key-123",
            "X-Sensitive-Auth": "test-api-key-123"
        }
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == "test-item"


def test_jwt_auth():
    """Test JWT token authentication."""
    pytest.importorskip("jwt", reason="pyjwt not installed")
    app = FastAPI()

    @app.get("/api/protected")
    def protected():
        return {"message": "protected"}

    config = AuthConfig(
        enabled=True,
        jwt_secret="test-jwt-secret-123",
        jwt_algorithm="HS256",
        whitelist=[],
    )
    setup_auth_middleware(app, config)

    client = TestClient(app)

    # Create valid token
    token = create_jwt_token(
        user_id="test-user",
        secret="test-jwt-secret-123",
        algorithm="HS256",
        expire_hours=1
    )

    # Access with valid token
    response = client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    # Access with invalid token
    response = client.get(
        "/api/protected",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401


def test_env_config():
    """Test configuration from environment variables."""
    # Set environment variables
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["API_KEY"] = "env-api-key-123"

    try:
        # Need to clear lru_cache
        get_auth_config.cache_clear()
        config = get_auth_config()

        assert config.enabled is True
        assert config.api_key == "env-api-key-123"

    finally:
        # Clean up
        os.environ.pop("AUTH_ENABLED", None)
        os.environ.pop("API_KEY", None)
        get_auth_config.cache_clear()


def test_invalid_config_raises():
    """Test that invalid config raises error when validated."""
    config = AuthConfig(
        enabled=True,
        api_key="",
        jwt_secret=""
    )
    with pytest.raises(ValueError, match="AUTH_ENABLED=true"):
        config.validate()
