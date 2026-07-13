"""F2 sector→ETF proxy registry — configs/sector_proxies.yaml 的只读解析服务.

真相源 = ``configs/sector_proxies.yaml``（文件即真值，改映射 = 改 YAML）。
本服务提供 TTL 重建缓存（模式同 services/kol_registry）与
``resolve_sector_proxy()``：把 entity_registry 的 sector 占位符号
（如 储能→ENERGY_STORAGE）解析为可交易 ETF 代理工具。

设计边界：
- F2 归属：sector→可交易工具是实体锚定的延伸（entity → tradable
  instrument），不是 F4 policy 判断。F5 runner 在 sector 门处只读查询。
- 解析结果必须携带完整溯源（config 版本 + 规则路径），供 TradeAction
  metadata 审计——proxy 出来的 action 永远能回答「为什么买的是这只 ETF」。
- 无写 API；映射变更靠编辑 YAML，TTL 到期自动生效。
- 加载失败隔离：坏 YAML / 坏条目只丢该条目，不炸 F5。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from finer.entity_registry import matches_tradable_format
from finer.paths import REPO_ROOT

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60.0
_CONFIG_RELPATH = Path("configs") / "sector_proxies.yaml"


@dataclass(frozen=True)
class SectorProxyInstrument:
    """One tradable proxy instrument for a sector."""

    symbol: str
    market: str
    name: str
    priority: int


@dataclass(frozen=True)
class SectorProxyResolution:
    """A resolved sector→proxy mapping with full audit provenance."""

    sector_symbol: str
    sector_name: str
    proxy_symbol: str
    proxy_market: str
    proxy_name: str
    rule: str
    config_version: int

    def audit_metadata(self) -> Dict[str, object]:
        """Provenance block for TradeAction.metadata — the audit answer to
        「这只 ETF 是替谁上场的」."""
        return {
            "sector_symbol": self.sector_symbol,
            "sector_name": self.sector_name,
            "proxy_symbol": self.proxy_symbol,
            "proxy_name": self.proxy_name,
            "rule": self.rule,
            "config_version": self.config_version,
        }


class SectorProxyRegistry:
    """File-truth registry over configs/sector_proxies.yaml with a TTL cache."""

    def __init__(self, root: Path = REPO_ROOT, ttl_seconds: float = _DEFAULT_TTL_SECONDS):
        self._root = Path(root)
        self._ttl = ttl_seconds
        self._proxies: Dict[str, Dict[str, object]] = {}
        self._version: int = 0
        self._built_at: Optional[float] = None

    @property
    def _config_path(self) -> Path:
        return self._root / _CONFIG_RELPATH

    def clear_cache(self) -> None:
        self._built_at = None

    def _ensure_fresh(self) -> None:
        now = time.monotonic()
        if self._built_at is not None and (now - self._built_at) < self._ttl:
            return
        self._rebuild()
        self._built_at = now

    def _rebuild(self) -> None:
        proxies: Dict[str, Dict[str, object]] = {}
        version = 0
        path = self._config_path
        if path.exists():
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as exc:  # noqa: BLE001 - bad YAML degrades to empty registry
                logger.warning("sector_proxy: unreadable %s: %s", path, exc)
                raw = {}
            if isinstance(raw, dict):
                try:
                    version = int(raw.get("version") or 0)
                except (TypeError, ValueError):
                    logger.warning(
                        "sector_proxy: non-integer version %r in %s; using 0",
                        raw.get("version"), path,
                    )
                blocks = raw.get("proxies") or {}
                if not isinstance(blocks, dict):
                    logger.warning("sector_proxy: proxies block in %s is not a mapping", path)
                    blocks = {}
                for sector_symbol, block in blocks.items():
                    # A hand-edited entry must never crash F5: any per-entry
                    # failure drops that entry only (file-truth contract).
                    try:
                        entry = self._load_entry(str(sector_symbol), block)
                    except Exception as exc:  # noqa: BLE001 - isolate operator config errors
                        logger.warning(
                            "sector_proxy: dropping %s (invalid entry: %s)",
                            sector_symbol, exc,
                        )
                        entry = None
                    if entry is not None:
                        proxies[str(sector_symbol)] = entry
        self._proxies = proxies
        self._version = version

    @staticmethod
    def _load_entry(sector_symbol: str, block: object) -> Optional[Dict[str, object]]:
        """Validate one sector block; failures drop the entry, never the registry."""
        if not isinstance(block, dict):
            logger.warning("sector_proxy: %s block is not a mapping", sector_symbol)
            return None
        instruments: List[SectorProxyInstrument] = []
        raw_instruments = block.get("instruments") or []
        if not isinstance(raw_instruments, list):
            logger.warning("sector_proxy: %s instruments is not a list", sector_symbol)
            return None
        for idx, inst in enumerate(raw_instruments):
            if not isinstance(inst, dict):
                continue
            symbol = str(inst.get("symbol") or "").strip()
            market = str(inst.get("market") or "").strip()
            name = str(inst.get("name") or "").strip()
            if not symbol or not market:
                logger.warning(
                    "sector_proxy: %s instrument #%d missing symbol/market", sector_symbol, idx
                )
                continue
            # 代理必须是真实可交易代码——占位符号（ENERGY_STORAGE）混进
            # instruments 是配置错误，加载时拒绝。
            if not matches_tradable_format(symbol):
                logger.warning(
                    "sector_proxy: %s instrument %r is not a tradable symbol format",
                    sector_symbol, symbol,
                )
                continue
            try:
                priority = int(inst.get("priority") or (idx + 1))
            except (TypeError, ValueError):
                logger.warning(
                    "sector_proxy: %s instrument %r has non-integer priority %r; using order %d",
                    sector_symbol, symbol, inst.get("priority"), idx + 1,
                )
                priority = idx + 1
            instruments.append(
                SectorProxyInstrument(
                    symbol=symbol,
                    market=market,
                    name=name or symbol,
                    priority=priority,
                )
            )
        if not instruments:
            return None
        instruments.sort(key=lambda i: i.priority)
        return {
            "sector_name": str(block.get("sector_name") or sector_symbol),
            "instruments": instruments,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def resolve(
        self,
        sector_symbol: Optional[str],
        *,
        market: Optional[str] = None,
    ) -> Optional[SectorProxyResolution]:
        """Resolve a sector placeholder symbol to its tradable proxy.

        ``market`` narrows to instruments of that market when any exist;
        otherwise the highest-priority instrument wins. Unknown sector →
        None (caller keeps its rejection path).
        """
        if not sector_symbol:
            return None
        self._ensure_fresh()
        entry = self._proxies.get(sector_symbol)
        if entry is None:
            return None
        instruments: List[SectorProxyInstrument] = entry["instruments"]  # type: ignore[assignment]
        pool = [i for i in instruments if market and i.market == market] or instruments
        chosen = pool[0]
        return SectorProxyResolution(
            sector_symbol=sector_symbol,
            sector_name=str(entry["sector_name"]),
            proxy_symbol=chosen.symbol,
            proxy_market=chosen.market,
            proxy_name=chosen.name,
            rule=f"{_CONFIG_RELPATH.as_posix()}#{sector_symbol}/{chosen.symbol}",
            config_version=self._version,
        )

    def known_sectors(self) -> List[str]:
        self._ensure_fresh()
        return sorted(self._proxies)


# =============================================================================
# Per-root instances (REPO_ROOT singleton; tmp roots in tests get their own)
# =============================================================================

_instances: Dict[Path, SectorProxyRegistry] = {}


def get_sector_proxy_registry(root: Path = REPO_ROOT) -> SectorProxyRegistry:
    root = Path(root).resolve()
    registry = _instances.get(root)
    if registry is None:
        registry = SectorProxyRegistry(root=root)
        _instances[root] = registry
    return registry


def resolve_sector_proxy(
    sector_symbol: Optional[str],
    *,
    market: Optional[str] = None,
    root: Path = REPO_ROOT,
) -> Optional[SectorProxyResolution]:
    """Module-level convenience over the REPO_ROOT singleton."""
    return get_sector_proxy_registry(root).resolve(sector_symbol, market=market)
