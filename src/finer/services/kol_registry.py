"""KOL Profile Registry — configs/creators/*.yaml 的只读注册表服务。

真相源 = `configs/creators/{creator_id}.yaml`（文件即真值，改档案 = 改
YAML）；本服务提供 TTL 重建缓存（默认 60s，模式同 audit_assembler）与
alias/平台身份解析。任何 F-stage 都可只读查询（与 config.py 同级的配置
读层）。Onboarding 一个新 KOL = 复制 `_template.yaml` 建档 + 渠道映射。

设计边界：
- 不落 data/（``data/kol_profiles/`` 归 annotation_store 的 KOL 速记）。
- 无写 API；档案变更靠编辑 YAML，TTL 到期自动生效。
- 与孤儿 KOLProfileManager（services/kol_profile.py，kol_{uuid} 主键）
  无关；仅借鉴其 ``{platform}:{account_id}`` 平台索引键结构。
- 加载失败隔离：单个坏 YAML 只丢该档案；trading_style 块单独校验，
  块无效时置 None 但保住档案其余字段（与 trading_style.py 的三态语义
  一致，test_kol_registry 钉住）。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from finer.paths import REPO_ROOT
from finer.schemas.kol_profile import CreatorProfile, DeclaredTradingStyle

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60.0


class KOLRegistry:
    """File-truth registry over configs/creators/*.yaml with a TTL cache."""

    def __init__(self, root: Path = REPO_ROOT, ttl_seconds: float = _DEFAULT_TTL_SECONDS):
        self._root = Path(root)
        self._ttl = ttl_seconds
        self._profiles: Dict[str, CreatorProfile] = {}
        self._resolve_index: Dict[str, str] = {}
        self._built_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Cache lifecycle
    # ------------------------------------------------------------------

    @property
    def _creators_dir(self) -> Path:
        return self._root / "configs" / "creators"

    def clear_cache(self) -> None:
        self._built_at = None

    def _ensure_fresh(self) -> None:
        now = time.monotonic()
        if self._built_at is not None and (now - self._built_at) < self._ttl:
            return
        self._rebuild()
        self._built_at = now

    def _rebuild(self) -> None:
        profiles: Dict[str, CreatorProfile] = {}
        directory = self._creators_dir
        if directory.exists():
            for path in sorted(directory.glob("*.yaml")):
                # Underscore stems are templates / pseudo-creators, never profiles.
                if path.stem.startswith("_"):
                    continue
                profile = self._load_one(path)
                if profile is not None:
                    profiles[profile.creator_id] = profile
        self._profiles = profiles
        self._resolve_index = self._build_resolve_index(profiles)

    @staticmethod
    def _load_one(path: Path) -> Optional[CreatorProfile]:
        """Load one creator YAML; failures drop the file, never the registry."""
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("kol_registry: unreadable creator YAML %s: %s", path.name, exc)
            return None
        if not isinstance(raw, dict):
            logger.warning("kol_registry: creator YAML %s is not a mapping", path.name)
            return None

        # creator_id truth is the filename stem; a divergent YAML field loses.
        yaml_id = raw.get("creator_id")
        if yaml_id and yaml_id != path.stem:
            logger.warning(
                "kol_registry: %s declares creator_id=%r; filename stem %r wins",
                path.name, yaml_id, path.stem,
            )
        raw["creator_id"] = path.stem

        # Validate the trading_style block in isolation: an invalid block must
        # not take down display_name and the rest of the profile.
        style_block = raw.pop("trading_style", None)
        declared: Optional[DeclaredTradingStyle] = None
        if isinstance(style_block, dict):
            try:
                declared = DeclaredTradingStyle.model_validate(style_block)
            except Exception as exc:
                logger.warning(
                    "kol_registry: invalid trading_style block in %s: %s", path.name, exc
                )

        try:
            profile = CreatorProfile.model_validate(raw)
        except Exception as exc:
            logger.warning("kol_registry: invalid creator profile %s: %s", path.name, exc)
            return None
        profile.trading_style = declared
        return profile

    @staticmethod
    def _build_resolve_index(profiles: Dict[str, CreatorProfile]) -> Dict[str, str]:
        """alias / display_name / handle / platform identity → creator_id."""
        index: Dict[str, str] = {}
        for cid, p in profiles.items():
            keys = [cid, p.display_name, p.handle, *p.aliases]
            keys.extend(
                f"{ident.platform}:{ident.account_id}"
                for ident in p.platform_identities
            )
            for key in keys:
                if not key:
                    continue
                index.setdefault(key.strip().lower(), cid)
        return index

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_profiles(self, include_disabled: bool = False) -> List[CreatorProfile]:
        self._ensure_fresh()
        profiles = list(self._profiles.values())
        if not include_disabled:
            profiles = [p for p in profiles if p.enabled]
        return profiles

    def get(self, creator_id: str) -> Optional[CreatorProfile]:
        """Exact creator_id lookup (no alias resolution)."""
        self._ensure_fresh()
        return self._profiles.get(creator_id)

    def resolve(self, key: str) -> Optional[str]:
        """alias / display_name / handle / '{platform}:{account_id}' → creator_id."""
        if not key:
            return None
        self._ensure_fresh()
        return self._resolve_index.get(key.strip().lower())

    def get_resolved(self, key: str) -> Optional[CreatorProfile]:
        """get(key), falling back to alias resolution."""
        profile = self.get(key)
        if profile is not None:
            return profile
        cid = self.resolve(key)
        return self._profiles.get(cid) if cid else None

    def display_name(self, creator_id: str) -> str:
        """Display name with the honest fallback: the raw creator_id."""
        profile = self.get(creator_id)
        if profile is not None and profile.display_name:
            return profile.display_name
        return creator_id

    def declared_style(self, creator_id: str) -> Optional[DeclaredTradingStyle]:
        profile = self.get(creator_id)
        return profile.trading_style if profile else None


# =============================================================================
# Per-root instances (REPO_ROOT singleton; tmp roots in tests get their own)
# =============================================================================

_instances: Dict[Path, KOLRegistry] = {}


def get_registry(root: Path = REPO_ROOT) -> KOLRegistry:
    root = Path(root).resolve()
    registry = _instances.get(root)
    if registry is None:
        registry = KOLRegistry(root=root)
        _instances[root] = registry
    return registry
