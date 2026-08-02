"""定向实体验证 — 闭集地核实 T3 声明的标的是否真实出现在正文中（P1）。

背景（`docs/specs/2026-07-30-next-actions-plan.md` P1）：F2 的 ``scan_text`` 只匹配
实体注册表别名，从不识别正文里的裸 ticker——2,503 条搁浅 bri intent 中 91.6% 的
代码格式合法却锚不到。而**开放集**的裸 ticker 扫描已实测不安全：法律声明缩写
（``C.T.V.M.`` → 伪命中 ``C.T``）、PDF 乱序残片（``sacinhceT NE.T``）、单双字母码
会批量产生假锚点，假锚点比缺锚点危害大（污染可审计性）。

本模块因此只做**闭集验证**：每次调用只核实一条 T3 已声明的标的（symbol + 可选
name），候选集大小为 1-2，且 T3 抽取本身构成独立证据源。这是把 A3 的「声明式」
原则用到证据层——T3 说了什么，就只验证那一件事。

上下文门（全部确定性、可单测）：
  * 词边界匹配，且拒绝缩写链（命中后紧跟 ``.字母``，如 C.T.V.M. 中的 C.T）；
  * 乱序窗口拒绝：±60 字符窗口内 ≥2 个「小写字母串+尾大写」token
    （``sacinhceT``/``ruE`` 是反转英文的特征签名，正常英文几乎不存在）；
  * 免责声明/法律段落整块拒绝（关键词表）；覆盖名单（``(ANF), (GOLF), (AS)``
    式枚举）按 **span 局部**窗口拒绝，避免连带毁掉同块的封面锚点；
  * 裸字母 base 只认交易所限定写法（``TSX: FTS`` / ``CP-TSX`` / ``NAVI US``），
    单字母符号直接判 too_ambiguous；裸数字 base 走 ``numeric_alias_context_ok``
    或同样的交易所限定；
  * 名称匹配要求 ASCII ≥4 字符 / CJK ≥2 字符，且 name ≠ symbol。

命中产出与 F2 注册表扫描同构的 ``EntityAnchor`` + ``EvidenceSpan``（复用同一
id 方案与 span 构造器），``metadata.layer = "targeted_verification"`` 保证可与
注册表锚点区分、可整体回滚。未命中返回明确状态，绝不伪造。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from finer.enrichment.entity_anchoring import (
    Hit,
    _evidence_span_for_hit,
    _stable_id,
    numeric_alias_context_ok,
)
from finer.enrichment.ticker_normalization import normalize_broker_ticker
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan

__all__ = [
    "BOILERPLATE_MARKERS",
    "TargetedVerification",
    "exchange_qualified",
    "in_coverage_roster",
    "is_scrambled_window",
    "verify_declared_target",
]

#: 整块拒绝的法律/免责声明标记（小写比较；短而保守，宁缺勿滥）。
BOILERPLATE_MARKERS: Tuple[str, ...] = (
    "disclaimer",
    "免责声明",
    "distributed in",
    "distributed by",
    "regulated by",
    "incorporated under",
    "c.t.v.m.",
    "研究报告仅供",
    "本报告的版权",
)

#: 监管披露里的「覆盖范围」名单会列出几十家**不相干**公司，形如
#: ``Abercrombie & Fitch (ANF), Acushnet Holdings Corp. (GOLF), Amer Sports (AS)``。
#: 命中它只证明该券商覆盖这只票，不证明本篇对它有观点 —— 拿它当证据会让 F5
#: 产出「有证据支撑」的错误 action。
#:
#: 判定必须是 **span 局部**而非整块：F1 的券商块常达数千字符，封面页与披露段
#: 同处一块，整块拒会连真锚点一起毁掉（实测毁 10 条封面锚点、精度增益为零）。
#: 三种真实写法都要认（括号紧闭 / 括号内带行情 / 带市场码），例：
#:   ``(ANF),``            —— 摩根大通 Coverage Universe
#:   ``(AWI: $196.57, HOLD)`` —— 杰富瑞 Other Companies Mentioned in This Report
#:   ``(CRH LN: p8,270.00, BUY)``
_ROSTER_ENTRY = re.compile(
    r"\([A-Z0-9][A-Z0-9.]{0,8}(?:\s[A-Z]{2})?\s*[:,)]"
)
_ROSTER_WINDOW = 120
_ROSTER_ENTRY_THRESHOLD = 2

#: 反转英文 token 的签名：小写串后跟一个大写字母结尾（sacinhceT / ruE / erahs）。
_REVERSED_TOKEN = re.compile(r"\b[a-z]{2,}[A-Z]\b")

_SCRAMBLE_WINDOW = 60
_SCRAMBLE_TOKEN_THRESHOLD = 2

_NAME_MIN_ASCII = 4
_NAME_MIN_CJK = 2

#: 交易所 / Bloomberg 市场限定符。研报正文里裸代码几乎总带其中之一
#: （``TSX: FTS``、``NYSE: BLCO``、``CP-TSX``、``BNTX-NSDQ``、``NAVI US``），
#: 而误抽的技术名词（``EUV``）从不带 —— 这是分开二者的判别特征。
_EXCHANGE_TOKENS = frozenset(
    """
    NYSE NASDAQ NSDQ NAS AMEX ARCA OTC TSX TSXV CSE LSE AIM SEHK HKEX HKSE
    ASX NZX TSE JPX OSE SGX KRX KOSPI KOSDAQ TWSE TPEX BSE NSE JSE SIX
    EPA AMS BIT BME MCE OMX OSL CPH HEL WSE MOEX B3 BMV BVL SSE SZSE
    SHSE SHA SHE CHIX EURONEXT XETRA FWB
    US CN HK JP TT KS IN AU SP LN FP GR IM SM NA BB SS SW NO DC FH CT
    """.split()
)
#: 限定符与代码之间允许的分隔（``: `` / ``-`` / 空格 / ``.``）。
_EXCH_LEFT = re.compile(r"\b([A-Z]{2,9})\s*[:\-]\s*$")
_EXCH_RIGHT = re.compile(r"^\s*[:\-\s]\s*([A-Z]{2,9})\b")

_CJK_RE = re.compile(r"[㐀-鿿]")


@dataclass
class TargetedVerification:
    """一次闭集验证的结果。"""

    status: str  # verified | no_occurrence | symbol_not_normalizable | symbol_too_ambiguous
    anchor: Optional[EntityAnchor] = None
    spans_by_block: Dict[str, List[EvidenceSpan]] = field(default_factory=dict)
    matched_variants: List[str] = field(default_factory=list)
    occurrences: int = 0
    rejected: Dict[str, int] = field(default_factory=dict)  # gate -> count


def is_scrambled_window(text: str, start: int, end: int) -> bool:
    """±60 字符窗口是否呈现 PDF 乱序抽取特征（反转英文签名）。"""
    lo = max(0, start - _SCRAMBLE_WINDOW)
    hi = min(len(text), end + _SCRAMBLE_WINDOW)
    return len(_REVERSED_TOKEN.findall(text[lo:hi])) >= _SCRAMBLE_TOKEN_THRESHOLD


def _is_boilerplate_block(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BOILERPLATE_MARKERS)


def _symbol_variants(target_symbol: str) -> Optional[Tuple[str, List[str], str, str]]:
    """(canonical_symbol, 匹配变体列表, market, base) 或 None（不可归一化）。

    变体只含**带后缀**的完整形式；裸 base 单独走更严的上下文门。
    """
    normalized = normalize_broker_ticker(target_symbol)
    if normalized is None or not normalized.symbol:
        return None
    variants = {target_symbol.strip(), normalized.symbol}
    base = normalized.symbol.split(".")[0]
    return normalized.symbol, sorted(v for v in variants if "." in v), (
        normalized.market or ""
    ), base


def _boundary_pattern(literal: str) -> re.Pattern:
    return re.compile(
        r"(?<![A-Za-z0-9.])" + re.escape(literal) + r"(?![A-Za-z0-9])"
    )


def _abbreviation_chain(text: str, end: int) -> bool:
    """命中之后紧跟 ``.字母`` → 属于更长的点分缩写（C.T.V.M.），拒绝。"""
    return end + 1 < len(text) and text[end] == "." and text[end + 1].isalpha()


def in_coverage_roster(text: str, start: int, end: int) -> bool:
    """命中是否落在「(代码), (代码), …」式的覆盖名单枚举里。

    只看 ±120 字符窗口，因此封面页与披露段同处一块时不会误伤封面锚点。
    """
    lo = max(0, start - _ROSTER_WINDOW)
    hi = min(len(text), end + _ROSTER_WINDOW)
    return len(_ROSTER_ENTRY.findall(text[lo:hi])) >= _ROSTER_ENTRY_THRESHOLD


def exchange_qualified(text: str, start: int, end: int) -> Optional[str]:
    """裸代码是否被交易所/市场限定符紧邻限定；是则返回该限定符。

    命中形如 ``TSX: FTS`` / ``NYSE: BLCO`` / ``CP-TSX`` / ``BNTX-NSDQ`` /
    ``FTS CN`` 时返回 ``"TSX"`` 等 token（真值），否则返回 None。这是研报标注
    股票代码的书写惯例，普通英文散文不会产生 —— 因此可作为裸代码的**正向**
    高精度接受条件，无需放宽通用上下文门。

    返回 token 而非布尔，是因为 ``normalize_broker_ticker`` 对**任何**裸代码都
    兜底盖 ``market="US"``（``COLOB`` 实为哥本哈根、``ALX`` 实为澳交所），而正文
    里的限定符正是纠正它所需的证据。本模块只把 token 记进 anchor metadata
    （``exchange_hint``），不改 ``resolved_symbol`` —— 改代码归一化是 F2 另一层
    的职责，需独立评审。
    """
    left = _EXCH_LEFT.search(text[max(0, start - 12):start])
    if left and left.group(1) in _EXCHANGE_TOKENS:
        return left.group(1)
    right = _EXCH_RIGHT.match(text[end:end + 12])
    if right and right.group(1) in _EXCHANGE_TOKENS:
        return right.group(1)
    return None


def verify_declared_target(
    envelope: Dict[str, Any],
    target_symbol: str,
    target_name: Optional[str] = None,
) -> TargetedVerification:
    """在信封正文中闭集验证一条 T3 声明的标的。

    Args:
        envelope: F2/F1 信封 dict（含 blocks）。
        target_symbol: T3 声明的代码（如 ``4091.T``）。
        target_name: T3 声明的公司名；与 symbol 相同或过短时忽略。

    Returns:
        TargetedVerification。``verified`` 时携带可直接并入信封的
        anchor + spans（id 方案与注册表扫描一致，重跑幂等）。
    """
    parsed = _symbol_variants(target_symbol)
    if parsed is None:
        return TargetedVerification(status="symbol_not_normalizable")
    canonical, dotted_variants, market, base = parsed

    base_is_numeric = base.isdigit()
    if not base_is_numeric and len(base) < 2:
        return TargetedVerification(status="symbol_too_ambiguous")

    name = (target_name or "").strip()
    name_usable = bool(name) and name != target_symbol and name != canonical
    if name_usable:
        if _CJK_RE.search(name):
            name_usable = len(_CJK_RE.findall(name)) >= _NAME_MIN_CJK
        else:
            name_usable = len(name) >= _NAME_MIN_ASCII

    source_record_id = (
        envelope.get("source_record_id") or envelope.get("envelope_id") or "unknown"
    )
    raw_path = envelope.get("raw_path") or envelope.get("source_uri") or ""

    spans_by_block: Dict[str, List[EvidenceSpan]] = {}
    matched: List[str] = []
    occurrences: List[Dict[str, Any]] = []
    rejected: Dict[str, int] = {}
    span_ids: List[str] = []

    def _reject(gate: str) -> None:
        rejected[gate] = rejected.get(gate, 0) + 1

    def _accept(
        block: Dict[str, Any], alias: str, start: int, end: int,
        exchange_hint: Optional[str] = None,
    ) -> None:
        hit = Hit(alias, canonical, market, "stock", start, end)
        span = _evidence_span_for_hit(
            block, hit, source_record_id=source_record_id, raw_path=raw_path
        )
        # 与注册表扫描的区分标记（可过滤、可回滚）
        span.metadata["layer"] = "targeted_verification"
        block_id = block.get("block_id") or ""
        spans_by_block.setdefault(block_id, []).append(span)
        span_ids.append(span.evidence_span_id)
        if alias not in matched:
            matched.append(alias)
        occurrence = {
            "block_id": block_id, "alias": alias,
            "char_start": start, "char_end": end,
        }
        if exchange_hint:
            occurrence["exchange_hint"] = exchange_hint
        occurrences.append(occurrence)

    for block in envelope.get("blocks") or []:
        text = block.get("text") or ""
        if not text:
            continue
        if _is_boilerplate_block(text):
            _reject("boilerplate_block")
            continue

        # 1) 带后缀的完整形式（含 T3 原文与 canonical 两种写法）
        for variant in dotted_variants:
            for m in _boundary_pattern(variant).finditer(text):
                if _abbreviation_chain(text, m.end()):
                    _reject("abbreviation_chain")
                    continue
                if is_scrambled_window(text, m.start(), m.end()):
                    _reject("scrambled_window")
                    continue
                if in_coverage_roster(text, m.start(), m.end()):
                    _reject("coverage_roster")
                    continue
                _accept(block, variant, m.start(), m.end())

        # 2) 裸 base——更严的上下文门
        for m in _boundary_pattern(base).finditer(text):
            if _abbreviation_chain(text, m.end()):
                _reject("abbreviation_chain")
                continue
            if is_scrambled_window(text, m.start(), m.end()):
                _reject("scrambled_window")
                continue
            if in_coverage_roster(text, m.start(), m.end()):
                _reject("coverage_roster")
                continue
            qualified = exchange_qualified(text, m.start(), m.end())
            if base_is_numeric:
                if not qualified and not numeric_alias_context_ok(
                    text, m.start(), m.end()
                ):
                    _reject("numeric_context")
                    continue
            elif not qualified:
                # 裸字母代码只认交易所限定写法。通用 bare_alias_context_ok 是为
                # 开放集注册表扫描设计的，在这里会放进 ``an EUV prototype`` 这类
                # 把技术名词当代码的误抽 —— 闭集下宁可漏，不可假。
                _reject("bare_context")
                continue
            _accept(block, base, m.start(), m.end(), exchange_hint=qualified)

        # 3) 声明的公司名
        if name_usable:
            if _CJK_RE.search(name):
                idx = text.find(name)
                while idx != -1:
                    _accept(block, name, idx, idx + len(name))
                    idx = text.find(name, idx + 1)
            else:
                for m in _boundary_pattern(name).finditer(text):
                    if is_scrambled_window(text, m.start(), m.end()):
                        _reject("scrambled_window")
                        continue
                    _accept(block, name, m.start(), m.end())

    if not occurrences:
        return TargetedVerification(
            status="no_occurrence", rejected=rejected
        )

    anchor = EntityAnchor(
        entity_type="stock",
        raw_text=max(matched, key=len),
        resolved_symbol=canonical,
        market=market or None,
        confidence=0.9,  # 定向验证：低于注册表精确命中的 1.0，可按 layer 审计
        evidence_span_id=span_ids[0],
        metadata={
            "layer": "targeted_verification",
            "match": "declared_symbol",
            "aliases": matched,
            "occurrences": occurrences,
            "evidence_span_ids": span_ids,
            "anchor_id": _stable_id(
                "anchor", source_record_id, canonical, "targeted_verification"
            ),
        },
    )
    return TargetedVerification(
        status="verified",
        anchor=anchor,
        spans_by_block=spans_by_block,
        matched_variants=matched,
        occurrences=len(occurrences),
        rejected=rejected,
    )
