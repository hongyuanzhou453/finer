"""统计效力门（CRD-2）—— 决定一个分数能否、以及以什么姿态呈现给用户。

两道**相互独立**的门：

1. **样本充分性**：n 够不够让这个比率有意义（Wilson 区间 + 分档 + 覆盖率）。
2. **预测性主张许可**：这个指标有没有被证明能预测未来（跨期持续性）。

把两者混为一谈是本项目 2026-08-02 定位转向所纠正的错误：瑞银 n=435 的
历史超额估得**很准**（门 1 通过），但它**不能**预测未来超额（门 2 不通过）。
一个按历史超额排序的榜单，即使每个数字都统计显著，仍然是在宣称一件
数据不支持的事。

阈值真相源 = ``configs/significance.yaml``（文件即真值，TTL 缓存，模式同
``services/kol_registry.py``）。``predictive_claim`` 段由检验的**记录结果**
驱动，不是配置口味——未检验一律按不许可处理。
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Dict, Optional, get_args

import yaml

from finer.paths import REPO_ROOT
from finer.schemas.significance import (
    PredictiveClaimVerdict,
    SampleSufficiency,
)
from finer.schemas.trade_action import SIGNAL_CLASS_LITERAL

logger = logging.getLogger(__name__)

#: signal_class → 该口径命中率所对应的、在 ``configs/significance.yaml``
#: ``predictive_claim`` 段登记的指标名。
#:
#: **每个 signal_class 都必须映射到一个指标名，不能是 None。** ``assess()`` 在
#: ``metric`` 为 None 时返回 ``predictive_claim=None``，而前端的横幅条件是
#: ``claim && !claim.permitted``——None 于是让整块「不构成对未来的预测」声明
#: **消失**。缺口的表现恰好是免责声明不见了，这是最坏的失效方向。
#:
#: 此前两处调用点都写成 ``"broker_excess_win_rate" if signal_class ==
#: "broker_recommendation" else None``，于是 24 张板块记录卡全部 claim=None。
_METRIC_BY_SIGNAL_CLASS: Dict[str, str] = {
    "broker_recommendation": "broker_excess_win_rate",
    "broker_sector_view": "broker_sector_excess_win_rate",
    "kol_statement": "kol_excess_win_rate",
}

# 契约新增 signal_class 却忘了在此登记指标名时，**import 期就炸**——
# 不要让它静默退化成 metric=None（= 免责声明消失）。
_UNMAPPED_SIGNAL_CLASSES = set(get_args(SIGNAL_CLASS_LITERAL)) - set(_METRIC_BY_SIGNAL_CLASS)
if _UNMAPPED_SIGNAL_CLASSES:  # pragma: no cover - 契约扩张时的启动期护栏
    raise RuntimeError(
        f"SIGNAL_CLASS_LITERAL 新增了未映射的取值 {sorted(_UNMAPPED_SIGNAL_CLASSES)}；"
        "请在 significance.py 的 _METRIC_BY_SIGNAL_CLASS 登记指标名，"
        "并在 configs/significance.yaml 的 predictive_claim 段登记该指标。"
    )


def metric_for_signal_class(signal_class: Optional[str]) -> Optional[str]:
    """该口径命中率对应的预测性主张指标名。

    未知 signal_class 返回 None——但注意 ``assess(metric=None)`` 会让
    ``predictive_claim`` 缺席。所有**契约内**的取值都在表里，不会走到这里；
    走到这里说明数据里有契约外的脏值，那本身就该在上游被拦。
    """
    if signal_class is None:
        return None
    return _METRIC_BY_SIGNAL_CLASS.get(signal_class)

_DEFAULT_TTL_SECONDS = 60.0
_CONFIG_RELPATH = Path("configs") / "significance.yaml"

#: 配置缺失/损坏时的保守兜底：只显计数，且不许可任何预测性主张。
#: 「读不到阈值」绝不能退化成「放行」。
_FALLBACK = {
    "confidence": 0.95,
    "tiers": {},
    "coverage": {"min_ratio": 1.0},
    "predictive_claim": {},
}


def wilson_interval(
    successes: int, n: int, confidence: float = 0.95
) -> Optional[tuple]:
    """二项比例的 Wilson score 区间；``n == 0`` 返回 None。

    选 Wilson 而非正态近似：小样本与极端比例下正态近似会给出越界或过窄的
    区间，而本层最需要诚实的恰恰是小样本。
    """
    if n <= 0:
        return None
    z = _z_for(confidence)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _z_for(confidence: float) -> float:
    """常用置信水平的 z 值；其余用有理逼近（避免拖入 scipy 依赖）。"""
    table = {0.90: 1.6448536269, 0.95: 1.9599639845, 0.99: 2.5758293035}
    if confidence in table:
        return table[confidence]
    # Acklam 逆正态逼近的简化：双侧 → 单侧分位
    p = 1.0 - (1.0 - confidence) / 2.0
    # Beasley-Springer-Moro 常数
    a = [-39.6968302866538, 220.946098424521, -275.928510446969,
         138.357751867269, -30.6647980661472, 2.50662827745924]
    b = [-54.4760987982241, 161.585836858041, -155.698979859887,
         66.8013118877197, -13.2806815528857]
    c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184,
         -2.54973253934373, 4.37466414146497, 2.93816398269878]
    d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -((((( c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


class SignificanceGate:
    """``configs/significance.yaml`` 的只读门，带 TTL 重建缓存。"""

    def __init__(
        self, root: Path = REPO_ROOT, ttl_seconds: float = _DEFAULT_TTL_SECONDS
    ) -> None:
        self._root = Path(root)
        self._ttl = ttl_seconds
        self._config: Dict = dict(_FALLBACK)
        self._built_at: Optional[float] = None

    # ------------------------------------------------------------------
    # 配置生命周期
    # ------------------------------------------------------------------

    def _ensure(self) -> None:
        now = time.monotonic()
        if self._built_at is not None and (now - self._built_at) < self._ttl:
            return
        path = self._root / _CONFIG_RELPATH
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"{path} 顶层不是映射")
            self._config = loaded
        except (OSError, ValueError, yaml.YAMLError) as exc:
            # 读不到阈值时退到最保守档，绝不放行
            logger.error("significance.yaml 加载失败，退到保守兜底: %s", exc)
            self._config = dict(_FALLBACK)
        self._built_at = now

    # ------------------------------------------------------------------
    # 门 2：预测性主张
    # ------------------------------------------------------------------

    def predictive_claim(self, metric: str) -> PredictiveClaimVerdict:
        """未登记的指标一律不许可 —— 「没检验过」不等于「可以用」。"""
        self._ensure()
        entry = (self._config.get("predictive_claim") or {}).get(metric)
        if not isinstance(entry, dict):
            return PredictiveClaimVerdict(
                metric=metric,
                permitted=False,
                summary="该指标未在 configs/significance.yaml 登记；"
                        "未检验一律按不许可处理。",
            )
        return PredictiveClaimVerdict(
            metric=metric,
            permitted=bool(entry.get("permitted", False)),
            tested_at=entry.get("tested_at"),
            sample_size=entry.get("sample_size"),
            evidence=entry.get("evidence"),
            summary=(entry.get("summary") or "").strip() or None,
            scope_note=(entry.get("scope_note") or "").strip() or None,
        )

    # ------------------------------------------------------------------
    # 门 1（+ 挂载门 2）：样本充分性
    # ------------------------------------------------------------------

    def assess(
        self,
        *,
        successes: int,
        settled_n: int,
        total_n: Optional[int] = None,
        metric: Optional[str] = None,
    ) -> SampleSufficiency:
        """判定一个比率型指标的可呈现姿态。

        Args:
            successes: 命中条数。
            settled_n: 已结算条数（比率的分母）。
            total_n: 全部条数（含未结算）；缺省视同 settled_n。
            metric: 指标标识；给了就一并挂上预测性主张判定。
        """
        self._ensure()
        if settled_n < 0 or successes < 0 or successes > max(settled_n, 0):
            raise ValueError(
                f"非法计数: successes={successes}, settled_n={settled_n}"
            )
        total = settled_n if total_n is None else max(total_n, settled_n)
        confidence = float(self._config.get("confidence", 0.95))

        notes: list = []
        point = interval = None
        if settled_n > 0:
            point = successes / settled_n
            interval = wilson_interval(successes, settled_n, confidence)

        tier, policy = self._tier_for(settled_n)
        if tier == "insufficient":
            notes.append(
                f"样本不足（已结算 {settled_n} 条），不展示比率，仅显示计数。"
            )
        elif tier == "provisional":
            notes.append(
                f"样本偏少（已结算 {settled_n} 条），数字仅供参考，"
                "区间宽度请一并阅读。"
            )

        coverage = (settled_n / total) if total > 0 else None
        penalised = False
        min_ratio = float((self._config.get("coverage") or {}).get("min_ratio", 0.5))
        if coverage is not None and coverage < min_ratio:
            penalised = True
            tier, policy = self._downgrade(tier)
            notes.append(
                f"结算覆盖率仅 {coverage:.0%}（{settled_n}/{total}），"
                "能结算的部分可能系统性不同于全体，已降档呈现。"
            )

        verdict = self.predictive_claim(metric) if metric else None
        if verdict is not None and not verdict.permitted:
            notes.append(
                "本平台未观测到该指标的跨期持续性，"
                "它描述已发生的事实，不构成对未来的预测。"
            )

        return SampleSufficiency(
            settled_n=settled_n,
            total_n=total,
            successes=successes,
            point_estimate=point,
            wilson_low=interval[0] if interval else None,
            wilson_high=interval[1] if interval else None,
            ci_width=(interval[1] - interval[0]) if interval else None,
            confidence=confidence,
            coverage_ratio=coverage,
            coverage_penalised=penalised,
            tier=tier,
            display_policy=policy,
            predictive_claim=verdict,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _tier_for(self, settled_n: int) -> tuple:
        tiers = self._config.get("tiers") or {}
        best_name, best_min, best_policy = "insufficient", -1, "count_only"
        for name, spec in tiers.items():
            if not isinstance(spec, dict):
                continue
            threshold = spec.get("min_settled")
            if not isinstance(threshold, int) or settled_n < threshold:
                continue
            if threshold > best_min:          # 取满足条件里门槛最高的一档
                best_name = name
                best_min = threshold
                best_policy = spec.get("display_policy") or "show_with_warning"
        if best_name not in ("sufficient", "provisional", "insufficient"):
            logger.warning("未知分档名 %r，按 insufficient 处理", best_name)
            return "insufficient", "count_only"
        if best_policy not in ("show", "show_with_warning", "count_only"):
            logger.warning("未知呈现策略 %r，按 count_only 处理", best_policy)
            best_policy = "count_only"
        return best_name, best_policy

    @staticmethod
    def _downgrade(tier: str) -> tuple:
        return {
            "sufficient": ("provisional", "show_with_warning"),
            "provisional": ("insufficient", "count_only"),
        }.get(tier, ("insufficient", "count_only"))


_DEFAULT_GATE: Optional[SignificanceGate] = None


def get_significance_gate(root: Path = REPO_ROOT) -> SignificanceGate:
    """进程级共享门（TTL 缓存，模式同 kol_registry）。"""
    global _DEFAULT_GATE
    if _DEFAULT_GATE is None or _DEFAULT_GATE._root != Path(root):
        _DEFAULT_GATE = SignificanceGate(root=root)
    return _DEFAULT_GATE
