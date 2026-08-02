"""P1 — 定向实体验证（闭集）。

钉住三类行为：真命中要过、已实测的假阳性模式必须拒、结果与注册表扫描同构。
反例全部来自 2026-07-30 在真实语料上量到的失败模式，不是构造的稻草人。
"""

from __future__ import annotations

from finer.enrichment.targeted_anchor import (
    exchange_qualified,
    is_scrambled_window,
    verify_declared_target,
)


def _env(*block_texts: str) -> dict:
    return {
        "envelope_id": "env-tv-001",
        "source_record_id": "broker_tv_test",
        "raw_path": "/tmp/x.pdf",
        "blocks": [
            {"block_id": f"b{i}", "text": t} for i, t in enumerate(block_texts)
        ],
    }


# ---------------------------------------------------------------------------
# 真命中
# ---------------------------------------------------------------------------


def test_suffixed_symbol_in_clean_text_verifies():
    r = verify_declared_target(
        _env("We maintain Buy on 4091.T with a revised target price."), "4091.T"
    )
    assert r.status == "verified"
    assert r.anchor is not None and r.anchor.resolved_symbol == "4091.T"
    assert r.occurrences == 1
    assert r.anchor.metadata["layer"] == "targeted_verification"
    spans = r.spans_by_block["b0"]
    assert spans[0].text == "4091.T"
    assert spans[0].metadata["layer"] == "targeted_verification"


def test_t3_spelling_and_canonical_both_match():
    """T3 写的是 Bloomberg 方言，正文用 Reuters 形式 —— 归一化后两种都认。"""
    r = verify_declared_target(
        _env("AstraZeneca (AZN.L) remains our top pick in pharma."), "AZN.LN"
    )
    assert r.status == "verified"
    assert r.anchor.resolved_symbol == "AZN.L"


def test_declared_name_matches_when_symbol_absent():
    r = verify_declared_target(
        _env("Naturgy reported strong quarterly results in Spain."),
        "NTGY.MC",
        target_name="Naturgy",
    )
    assert r.status == "verified"
    assert "Naturgy" in r.matched_variants


def test_cjk_name_substring_match():
    r = verify_declared_target(
        _env("嘉能可宣布削减刚果铜矿产量，供给端进一步收紧。"),
        "GLEN.L",
        target_name="嘉能可",
    )
    assert r.status == "verified"


def test_bare_numeric_base_with_market_context():
    """裸数字码需要行情上下文（复用 numeric_alias_context_ok 的语义）。"""
    r = verify_declared_target(_env("目标价上调，8309（东京上市）受益于利率环境。"), "8309.T")
    # 无论该上下文门判定如何，带后缀形式缺席时结果必须是确定性的两态之一
    assert r.status in ("verified", "no_occurrence")


# ---------------------------------------------------------------------------
# 已实测的假阳性模式 —— 必须拒绝
# ---------------------------------------------------------------------------


def test_abbreviation_chain_rejected():
    """C.T.V.M.（摩根士丹利巴西实体）绝不能命中 target C.T。"""
    r = verify_declared_target(
        _env("Disseminated in Brazil by Morgan Stanley C.T.V.M. S.A. located at Av."),
        "C.T",
    )
    assert r.status != "verified"


def test_scrambled_pdf_text_rejected():
    """反转乱序残片（sacinhceT … erahs ruE）是实测过的批量假阳性来源。

    原型是 NE.T（Technip Energies 被反转），此处用可归一化的 7203.T 复现同一
    窗口特征 —— 要点是乱序窗口里的合法代码也必须拒。
    """
    scrambled = "…sacinhceT 7203.T MBS CEOOC yelroW eriaM aesbuS mepiaS roulF erahs ruE"
    r = verify_declared_target(_env(scrambled), "7203.T")
    assert r.status == "no_occurrence"
    assert r.rejected.get("scrambled_window", 0) >= 1


def test_boilerplate_block_rejected_entirely():
    r = verify_declared_target(
        _env(
            "Disclaimer: this report is distributed in Singapore by XYZ 4091.T entity."
        ),
        "4091.T",
    )
    assert r.status == "no_occurrence"
    assert r.rejected.get("boilerplate_block") == 1


_ROSTER = (
    "Explanation of Equity Research Ratings, Designations and Analyst(s) Coverage "
    "Universe: Boss, Matthew R: Abercrombie & Fitch (ANF), Acushnet Holdings Corp. "
    "(GOLF), Amer Sports (AS), American Eagle Outfitters (AEO), PACCAR Inc. (PCAR),"
)


def test_coverage_roster_rejected():
    """券商覆盖名单列几十家不相干公司；命中它不等于本篇对它有观点。"""
    r = verify_declared_target(_env(_ROSTER), "GOLF.N")
    assert r.status == "no_occurrence"
    assert r.rejected.get("coverage_roster", 0) >= 1


def test_roster_gate_is_span_local_not_block_level(
):
    """同一块里封面页 + 披露名单并存时，只拒名单命中，封面锚点必须活着。

    F1 的券商块常达数千字符，整块拒会连真锚点一起毁掉（实测毁 10 条封面锚点
    且精度增益为零）—— 这条测试就是钉住那个教训。
    """
    r = verify_declared_target(
        _env(
            "PACCAR Inc NASDAQ: PCAR Overweight Price Target $135. " + "x" * 300
            + " " + _ROSTER
        ),
        "PCAR.OQ",
    )
    assert r.status == "verified"
    assert r.occurrences == 1  # 只有封面那一处
    assert r.rejected.get("coverage_roster", 0) >= 1


def test_roster_gate_covers_priced_enumeration_form():
    """杰富瑞的「Other Companies Mentioned」在括号里塞了行情和评级。

    第一版正则要求括号紧闭，漏掉了这类写法 —— 审计轮 4 唯一的假阳性。
    """
    r = verify_declared_target(
        _env(
            "Other Companies Mentioned in This Report: "
            "• Armstrong World Industries, Inc. (AWI: $196.57, HOLD) "
            "• CRH (CRH: $112.46, BUY) "
            "• Carlisle Companies Incorporated (CSL: $338.01, HOLD)"
        ),
        "CRH.N",
    )
    assert r.status == "no_occurrence"
    assert r.rejected.get("coverage_roster", 0) >= 1


def test_roster_gate_also_covers_dotted_form():
    """点分写法出现在名单里同样要拒（审计实测残留 0.28% 走的就是这条路）。"""
    r = verify_declared_target(
        _env("Coverage: Petrobras (PETR3.SA), Vale (VALE3.SA), Itau (ITUB4.SA),"),
        "PETR3.SA",
    )
    assert r.status == "no_occurrence"
    assert r.rejected.get("coverage_roster", 0) >= 1


def test_single_letter_symbol_too_ambiguous():
    """Macy's (M) 这类单字母码在闭集下也救不了 —— 直接拒。"""
    r = verify_declared_target(_env("M reported earnings. M is up."), "M")
    assert r.status == "symbol_too_ambiguous"


def test_unnormalizable_symbol_is_explicit():
    r = verify_declared_target(_env("whatever text"), "FOO.ZZZZQ")
    assert r.status == "symbol_not_normalizable"


def test_substring_inside_larger_token_not_matched():
    """词边界：4091.T 不得从 14091.TW 里抠出来。"""
    r = verify_declared_target(_env("Code 14091.TW is a different listing."), "4091.T")
    assert r.status == "no_occurrence"


# ---------------------------------------------------------------------------
# 裸代码的交易所限定门（分开「合法裸代码」与「被误抽的技术名词」）
# ---------------------------------------------------------------------------
#
# 下列写法全部取自真实研报正文（2026-07-30 no_occurrence 桶诊断）。


def test_exchange_prefix_forms_accepted():
    for text, symbol in (
        ("Fortis divests FortisTCI. TSX: FTS | CAD 68.71 | Sector Perform", "FTS"),
        ("Xiidra TRx growth was +8.3% y/y NYSE: BLCO | USD 14.59 | Outperform", "BLCO"),
        ("Outperform LSE: HTG; GBp 328.50 September 1, 2025 Hunting PLC", "HTG"),
    ):
        r = verify_declared_target(_env(text), symbol)
        assert r.status == "verified", symbol
        assert r.matched_variants == [symbol]


def test_exchange_suffix_forms_accepted():
    for text, symbol in (
        ("Canadian Pacific Kansas City Limited CP-TSX Rating Price", "CP.TSX"),
        ("BioNTech SE BNTX-NSDQ Rating Price: Sep-4 Target Biotechnology", "BNTX.NSDQ"),
        ("Gibson Energy GEI-TSX Rating Energy Infrastructure", "GEI.TSX"),
    ):
        r = verify_declared_target(_env(text), symbol)
        assert r.status == "verified", symbol


def test_bloomberg_country_code_suffix_accepted():
    r = verify_declared_target(
        _env("Rating and price target history for: Fortis Inc., FTS CN as of 04-Sep"),
        "FTS",
    )
    assert r.status == "verified"


def test_mis_extracted_acronym_in_prose_rejected():
    """T3 把技术名词「极紫外光」抽成了 ticker EUV —— 散文里的 EUV 必须拒。

    这是本门存在的理由：它与上面 7 个合法样本的唯一稳定差别就是
    有没有交易所限定语法。
    """
    r = verify_declared_target(
        _env("China built an EUV prototype in early 2025. Our local channel check"),
        "EUV",
    )
    assert r.status == "no_occurrence"
    assert r.rejected.get("bare_context", 0) >= 1


def test_exchange_hint_is_recorded_without_touching_resolved_symbol():
    """``normalize_broker_ticker`` 对裸代码一律兜底盖 US（COLOB 实为哥本哈根）。

    正文里的限定符是纠正它的证据，必须留痕；但改 symbol 归一化是另一层的事，
    本模块只记不改 —— 否则 P1 会悄悄改变 canonical 身份。
    """
    r = verify_declared_target(_env("Coloplast B CSE: COLOB Buy, target DKK 900"), "COLOB")
    assert r.status == "verified"
    assert r.anchor.resolved_symbol == "COLOB"        # 不改
    assert r.anchor.market == "US"                     # 归一化器的既有行为
    assert r.anchor.metadata["occurrences"][0]["exchange_hint"] == "CSE"  # 但留痕


def test_exchange_qualified_unit():
    t = "TSX: FTS trades at"
    assert exchange_qualified(t, t.index("FTS"), t.index("FTS") + 3)
    p = "an EUV prototype"
    assert not exchange_qualified(p, p.index("EUV"), p.index("EUV") + 3)
    # 非交易所的大写缩写不得冒充限定符
    q = "GDP: FTS is unrelated"
    assert not exchange_qualified(q, q.index("FTS"), q.index("FTS") + 3)


# ---------------------------------------------------------------------------
# 同构与幂等
# ---------------------------------------------------------------------------


def test_span_ids_deterministic_across_calls():
    env = _env("Buy 4091.T. We reiterate our view on 4091.T today.")
    a = verify_declared_target(env, "4091.T")
    b = verify_declared_target(env, "4091.T")
    ids_a = [s.evidence_span_id for spans in a.spans_by_block.values() for s in spans]
    ids_b = [s.evidence_span_id for spans in b.spans_by_block.values() for s in spans]
    assert ids_a == ids_b and len(ids_a) == 2  # 两次出现，稳定 id → 合并幂等


def test_scramble_detector_unit():
    assert is_scrambled_window("aaa sacinhceT xx ruE bbb", 8, 10)
    assert not is_scrambled_window("Technip Energies reported EUR revenue.", 8, 10)
