from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Literal

import yaml


@dataclass
class BBDownServiceConfig:
    """BBDown service configuration."""

    api_url: str = "http://localhost:12450"
    auto_start: bool = True
    cookie: Optional[str] = None
    download_dir: str = "data/raw/bilibili"


@dataclass
class MiMoASRConfig:
    """MiMo ASR service configuration.

    Uses MiMo Open Platform API (https://platform.xiaomimimo.com/)
    with OpenAI-compatible format for audio transcription.
    """

    api_url: str = "https://api.xiaomimimo.com/v1/audio/transcriptions"
    api_key: Optional[str] = None
    model: str = "whisper-1"
    timeout: float = 300.0
    chunk_size_mb: float = 25.0
    language: str = "zh"


@dataclass
class FunASRConfig:
    """FunASR local inference configuration.

    Runs on M2 Mac (Apple Silicon) without CUDA.
    Models are downloaded from ModelScope.
    """

    model: str = "paraformer-zh-streaming"  # Lightweight model (~220MB)
    model_revision: str = "v2.0.4"
    language: str = "zh"
    device: str = "cpu"  # Use CPU for M2 Mac


@dataclass
class ASRConfig:
    """Unified ASR configuration supporting multiple backends."""

    backend: Literal["funasr", "mimo_api"] = "funasr"
    funasr: FunASRConfig = None
    mimo_api: MiMoASRConfig = None

    def __post_init__(self):
        if self.funasr is None:
            self.funasr = FunASRConfig()
        if self.mimo_api is None:
            self.mimo_api = MiMoASRConfig()


@dataclass
class WeChatServiceConfig:
    """WeChat integration configuration.

    The exporter base URL has a single source of truth: ``configs/wechat.yaml``.
    The default below must match that file's ``exporter_url`` so there is no
    port disagreement when the YAML is absent.
    """

    exporter_url: str = "http://localhost:3001"
    source_type: str = "hybrid"  # direct_api, exporter_service, hybrid
    prefer_exporter: bool = True
    cache_credentials: bool = True
    # Optional explicit path to the wx_video_download binary (WeChat Channels
    # downloader). Left unset by default: the channels importer resolves the
    # binary via PATH / WX_CHANNELS_DOWNLOAD_BIN env / this field / vendored copy.
    channels_downloader_bin: Optional[str] = None


def load_creator_config(root: Path, creator_id: str) -> dict[str, Any]:
    config_path = root / "configs" / "creators" / f"{creator_id}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"creator config not found: {config_path}")
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def load_feishu_config(root: Path) -> dict[str, Any]:
    """Load Feishu file management configuration from configs/feishu.yaml."""
    config_path = root / "configs" / "feishu.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Feishu config not found: {config_path}\n"
            "Run 'python scripts/setup_feishu.py' to initialize."
        )
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def load_bbdown_config(root: Path) -> BBDownServiceConfig:
    """Load BBDown configuration from environment variables."""
    return BBDownServiceConfig(
        api_url=os.getenv("BBDOWN_API_URL", "http://localhost:12450"),
        auto_start=os.getenv("BBDOWN_AUTO_START", "true").lower() == "true",
        cookie=os.getenv("BBDOWN_COOKIE"),
        download_dir=os.getenv("BBDOWN_DOWNLOAD_DIR", "data/raw/bilibili"),
    )


def load_mimo_asr_config(root: Path) -> MiMoASRConfig:
    """Load MiMo ASR configuration from environment variables."""
    return MiMoASRConfig(
        api_url=os.getenv("MIMO_ASR_URL", "https://api.xiaomimimo.com/v1/audio/transcriptions"),
        api_key=os.getenv("MIMO_ASR_API_KEY") or os.getenv("MIMO_API_KEY"),
        model=os.getenv("MIMO_ASR_MODEL", "whisper-1"),
        timeout=float(os.getenv("MIMO_ASR_TIMEOUT", "300")),
        chunk_size_mb=float(os.getenv("MIMO_ASR_CHUNK_SIZE_MB", "25")),
        language=os.getenv("MIMO_ASR_LANGUAGE", "zh"),
    )


def load_funasr_config(root: Path) -> FunASRConfig:
    """Load FunASR configuration from environment variables."""
    return FunASRConfig(
        model=os.getenv("FUNASR_MODEL", "paraformer-zh-streaming"),
        model_revision=os.getenv("FUNASR_MODEL_REVISION", "v2.0.4"),
        language=os.getenv("FUNASR_LANGUAGE", "zh"),
        device=os.getenv("FUNASR_DEVICE", "cpu"),
    )


def load_asr_config(root: Path) -> ASRConfig:
    """Load unified ASR configuration.

    Default backend is 'funasr' for M2 Mac compatibility.
    """
    backend = os.getenv("ASR_BACKEND", "funasr")
    return ASRConfig(
        backend=backend,
        funasr=load_funasr_config(root),
        mimo_api=load_mimo_asr_config(root),
    )


def load_wechat_service_config(root: Path) -> WeChatServiceConfig:
    """Load WeChat service configuration from YAML or defaults."""
    config_path = root / "configs" / "wechat.yaml"
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return WeChatServiceConfig(
            exporter_url=data.get("exporter_url", WeChatServiceConfig.exporter_url),
            source_type=data.get("source_type", "hybrid"),
            prefer_exporter=data.get("prefer_exporter", True),
            cache_credentials=data.get("cache_credentials", True),
            channels_downloader_bin=data.get("channels_downloader_bin"),
        )
    return WeChatServiceConfig(
        exporter_url=os.getenv("WECHAT_EXPORTER_URL", WeChatServiceConfig.exporter_url),
        source_type=os.getenv("WECHAT_SOURCE_TYPE", "hybrid"),
    )


@dataclass
class PipelineAutoDriveConfig:
    """Config for the in-server incremental pipeline auto-driver (roadmap ①).

    Default OFF: enabling it makes the API server perform real LLM-backed
    F1/F2/F3/F5 work and settle (apply) on a timer, so it must be an explicit
    opt-in rather than a side effect of starting the server.
    """

    enabled: bool = False
    interval_seconds: int = 300
    limit: Optional[int] = None
    run_settle: bool = True
    initial_delay_seconds: float = 5.0


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_pipeline_autodrive_config() -> PipelineAutoDriveConfig:
    """Build auto-driver config from environment variables.

    FINER_PIPELINE_AUTODRIVE          enable the background driver (default off)
    FINER_PIPELINE_DRIVE_INTERVAL     seconds between passes (default 300)
    FINER_PIPELINE_DRIVE_LIMIT        max content_ids per pass (default: all)
    FINER_PIPELINE_DRIVE_SETTLE       run F8 settle each pass (default on)
    FINER_PIPELINE_DRIVE_INITIAL_DELAY  delay before the first pass (default 5s)
    """
    limit_raw = os.getenv("FINER_PIPELINE_DRIVE_LIMIT")
    return PipelineAutoDriveConfig(
        enabled=_env_flag("FINER_PIPELINE_AUTODRIVE", False),
        interval_seconds=int(os.getenv("FINER_PIPELINE_DRIVE_INTERVAL", "300")),
        limit=int(limit_raw) if limit_raw not in (None, "") else None,
        run_settle=_env_flag("FINER_PIPELINE_DRIVE_SETTLE", True),
        initial_delay_seconds=float(os.getenv("FINER_PIPELINE_DRIVE_INITIAL_DELAY", "5")),
    )
