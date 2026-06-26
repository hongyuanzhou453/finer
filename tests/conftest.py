"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# Configure pytest-asyncio
def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


# Provider credentials / base URLs that, if present, make the suite non-hermetic.
# A module imported at collection time (finer.cli → utils.* → load_dotenv) loads
# the real .env into os.environ, which would (a) let the F1 image/PDF standardizer
# fire LIVE Qwen-VL-OCR calls during unit tests and (b) pollute the cached vision
# registry's base_url (real MIMO_BASE_URL != default). We strip these per test so
# tests never hit the network or read real config; a test that needs a value sets
# it explicitly via monkeypatch (which overrides this autouse fixture).
_HERMETIC_ENV_VARS = (
    "DASHSCOPE_API_KEY",
    "MIMO_API_KEY",
    "MIMO_BASE_URL",
    "MIMO_VISION_BASE_URL",
)


@pytest.fixture(autouse=True)
def _hermetic_provider_env(monkeypatch):
    """Keep every test hermetic w.r.t. provider creds leaked in from the real .env."""
    for var in _HERMETIC_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # Drop the cached vision registry so it rebuilds from the cleaned env.
    try:
        import finer.model_config as mc

        monkeypatch.setattr(mc, "_vision_registry", None, raising=False)
    except Exception:
        pass
    yield
