# 任务卡：F2 中文实体候选生成 — constrained-LLM 提议 + 确定性 validator

> 类型: 实现型任务卡（供新会话冷启动）
> F-stage: F2 (enrichment / entity anchoring)
> 创建: 2026-06-26
> 前置阅读: `docs/specs/2026-06-26-f2-anchor-hit-rate.md`（上一轮：为什么规则方案失败）

---

## 0. 一句话任务

给 F2 的 gap-候选生成新增一条 **constrained-LLM 提议路径**：用 DeepSeek 约束 JSON 从 block 文本提议「实体名 + 建议 ticker/market」，再用**确定性 validator** 硬校验（防幻觉、防已存在、防非实体），产出与现有规则路径同格式的候选，喂现有 review→apply→registry 闭环。**目标**：把 all-local 实体锚定命中率从当前 17.7% 继续往上拉，解决规则方案在对话型 KOL 语料上无法做的中文实体识别。

## 1. 为什么要做（背景，勿重复踩坑）

- F2 all-local 实体锚定命中率 16.5%→17.7%（上一轮手工插 6 实体）。瓶颈在**候选生成**：27 个规则候选仅 6 个可插（22%）。
- 上一轮（2026-06-26）实现了规则版中文实体抽取（bracket `【地平线】` + post-marker `[实体]纳入/上市/涨停` + 词缀剥离），**合成用例全对，但真实 3051-block 语料测定 precision ~6%（宽 marker）/ 零召回（严格 marker），已全部 revert**。
- 根因：对话型 KOL 截图里，规则无法区分 `地平线`（实体）与 `倒春寒`/`"隐性承诺"`（强调短语）——这是语义问题，规则无解。
- 这正是项目架构（`AGENTS.md` F1.5 段、`CLAUDE.md` §1.5）既定方向：**constrained LLM proposal + deterministic validator**，而非规则。本任务把该方向用到 F2 候选生成。

## 2. 现成范例（必须 mirror）

`src/finer/parsing/llm_topic_assembly_adapter.py` —— F1.5 的 constrained-LLM proposal adapter，**照抄其骨架**：

- `class LLMTopicAssemblyAdapter.__init__(llm_fn=None, deepseek_client=None, max_blocks=..., llm_timeout=...)` —— `llm_fn` 是**测试注入缝**（接收 messages 返回 JSON str），生产用 `DeepSeekClient.from_env()`。
- `LLMTopicProposal(BaseModel)` + `LLMTopicAssemblyPayload(BaseModel)`，均 `model_config = ConfigDict(strict=True, extra="forbid")`；`@model_validator` 做 source 校验（如 `validate_source_blocks`：proposal 只能引用真实 block_id）。
- `_build_messages()`：构造约束 payload（block 文本 + **allowed enum** + **example JSON output** + **output_schema**），SYSTEM_PROMPT 写死「只能用提供的值、Return JSON only」。
- `_call_llm()`：`DeepSeekClient.from_env(timeout=...).chat_json(messages, max_tokens=8192, thinking_enabled=True, reasoning_effort="high")` → `json.dumps`。
- `_parse_payload()`：`Payload.model_validate(data)`（strict 失败即报错重试/降级）。
- `_reconstruct_result()`：**确定性重建**——丢弃 LLM 越权/幻觉输出，只保留通过校验的部分。

LLM client：`from finer.llm import DeepSeekClient, DeepSeekClientError, DeepSeekConfigurationError`（`src/finer/llm/deepseek_client.py`）。

> 模型默认对齐范例（DeepSeek）。若评估后认为结构化更适合 Qwen-Max + `instructor`（`CLAUDE.md` §4），可在任务卡里记录决策后切换，但先跑通范例路线。

## 3. 集成点（数据流 + 接口，已核对）

```
backfill_f2_anchor.py: _gap_candidates_for_block(item, block, reason)
   ├─ 现有: upper-token 规则路径 (candidate_type="known_format_upper_token")
   ├─ 现有: cn-cue 规则路径     (candidate_type="cn_entity_phrase")  ← 保留，不替换
   └─ 【新增】LLM 提议路径       (candidate_type="llm_entity_proposal")
        → 产出 dict，字段对齐 GAP_CANDIDATE_REVIEW_FIELDS (backfill_f2_anchor.py:43)
          = alias_candidate, source_record_id, block_id, raw_path,
            context_snippet, reason, candidate_type, score, review_status
        ↓
scripts/build_f2_gap_review_batch.py --candidates-in <jsonl> --out <review.jsonl>  (加 review_status="" 列)
        ↓ 人工 / agent 填 review_status=approved + suggested_ticker + market
scripts/apply_f2_gap_reviews.py --review-in <review.jsonl>  → AnnotationStore.append_registry_gap()
        ↓ 写 data/dpo/registry_gaps.jsonl  ← 注意：这只是追踪/DPO，不改锚定
   【关键】要真正拉命中率，approved 实体最终须进 src/finer/entity_registry.py 的 ENTITY_REGISTRY
            （alias → (ticker, market, etype)），entity_anchoring.scan_text 扫的是这个 dict。
```

F2 真相源与消费：
- `src/finer/entity_registry.py`：`ENTITY_REGISTRY: Dict[str, Tuple[ticker, market, etype]]`、`resolve(name)`。markets: US/HK/CN/TW/KR/COMMODITY/CRYPTO；etypes: ticker/index/etf/sector/commodity/crypto。HK 用 `3908.HK`，CN 用 `601995.SH`/`002891.SZ`，US 裸 `GS`。
- `src/finer/enrichment/entity_anchoring.py`：`scan_text(text)->List[Hit]`、`anchor_entities_deterministic(blocks)->List[EntityAnchor]`、`build_f2_deterministic_envelope(...)`。
- 只读测量基线：`python scripts/backfill_f2_anchor.py --scope all-local --dry-run --gap-candidates-out /tmp/x.jsonl`（当前命中率 17.7%、零锚文档 68、registry_gap_candidate 179 块）。

## 4. 要做什么

### Phase 1 — 提议器 + validator（核心，纯代码 + mock 测试，无红线）
1. 新模块 `src/finer/enrichment/llm_entity_proposal.py`（或 parsing 下，按 F2 归属放 enrichment）：
   - `LLMEntityProposal(BaseModel, strict, extra=forbid)`：`alias`、`suggested_ticker`、`market`、`entity_type`、`confidence`、`evidence_quote`（必须是 block 文本子串）。
   - `LLMEntityProposalPayload(BaseModel)`：`proposals: list[LLMEntityProposal]`、`reasoning_summary`。
   - `class LLMEntityProposalAdapter(llm_fn=None, deepseek_client=None, ...)`：mirror 范例。SYSTEM_PROMPT 约束「只提议在文本中真实出现的、可在公开市场交易的实体名；不要提议指标(EPS/PB)、时间、货币、指数泛称、组织(OPEC)、用户名、基金；不确定 ticker 留空；Return JSON only」。
2. **确定性 validator**（LLM 不可信，逐条硬校验，全部通过才成候选）：
   - `evidence_quote` 与 `alias` 必须逐字出现在 source block text（防幻觉实体名）。
   - `alias not in ENTITY_REGISTRY`（去重，已有的不重复提）。
   - `suggested_ticker` 格式校验：`^\d{4,6}\.(HK|SH|SZ)$` 或 `^[A-Z]{1,5}$`；market ∈ 允许集；留空也允许（人工补）。
   - 复用已有非实体 stoplist：拒绝命中 `_NOISY_UPPER_TOKENS` / `_CN_GENERIC_CANDIDATE_TERMS` / 指标时间货币集 的 alias。
   - 可选(P1)：交叉验证 `services/finance_skills_client.py` 确认 ticker 真实存在。
3. 单测 `tests/test_llm_entity_proposal.py`：用 `llm_fn` 注入 mock JSON（含 1 个真实实体 + 1 个幻觉 + 1 个已存在 + 1 个指标噪声），断言 validator 只放行真实那个。**不打真实 LLM**（mirror 范例测试 + `tests/conftest.py` hermetic 夹具）。

### Phase 2 — 接入候选流（小改 backfill）
4. `_gap_candidates_for_block` 增加 LLM 路径（默认关闭，`--llm-proposals` flag 开启；no key/无配置时干净跳过，mirror `adapter.is_configured()`），产出 `candidate_type="llm_entity_proposal"` 候选。
5. **小样本 precision 验证**：在 71 零锚文档 + 179 registry_gap 块的子集上跑 LLM 路径，人工核对提议 precision。**达标线建议 precision ≥ 60%**（远高于规则的 6%）。写一个 eval 脚本 mirror `scripts/eval_ocr_accuracy.py` 的报告风格。

### Phase 3 — 放量 + registry 插入（红线，必须用户确认）
6. 全量跑 LLM 候选 → review batch → 人工/agent 核验 → 插入 `entity_registry.py` → 重测命中率 delta。**registry/数据写入、批量跑 LLM 是 CLAUDE.md 红线，先停下问用户**。

## 5. 约束与红线（CLAUDE.md / AGENTS.md）

- **F-stage**：只动 F2（`enrichment/`）+ `backfill_f2_anchor.py` 候选生成 + 测试。不碰 F0/F1/F3+。
- **红线先问**：改 `entity_registry.py`（registry 写入）、批量调用 LLM（烧 token）、批量重建/重锚定 → 必须先获用户确认。Phase 1/2 的代码+mock 测试无红线，可直接做。
- **LLM 纪律**：prompt 不硬编码 key；密钥走 env；`llm_fn` 测试缝必须有，单测不打真实 API。
- **LLM 只提议、不决定**：validator + 人工 review + registry 插入保持确定性。任何 LLM 输出未过 validator 不得进候选流。
- **保留规则路径**：upper-token / cn-cue 规则路径对 cue 命中的中文名和 ticker 仍有用，LLM 路径是**增量并存**不是替换。
- **契约零改动**：候选 JSONL 字段、`EntityAnchor`/`ContentEnvelope`/registry-gap 格式不变。
- **验证命令**：`pytest tests/ -v`（全量须绿）；F2 子集 `pytest tests/test_llm_entity_proposal.py tests/test_backfill_f2_anchor.py tests/test_entity_anchoring.py tests/test_apply_f2_gap_reviews.py tests/test_build_f2_gap_review_batch.py -q`。

## 6. 已知陷阱

- **registry_gaps.jsonl ≠ 锚定**：`apply_f2_gap_reviews.py` 只写 `data/dpo/registry_gaps.jsonl`，不改 `ENTITY_REGISTRY`、不影响命中率。要拉命中率必须把 approved 实体进 `entity_registry.py` 源（见 4.Phase3）。
- **测试 fixture 耦合**：往 registry 加实体后，凡是把该实体当「gap 候选」断言的测试会失败（已有先例：`曹操出行` 插入后 `test_backfill_f2_anchor` 3 个测试需改用虚构实体如 `云图出行`）。插实体时同步查 `rg <alias> tests/`。
- **all-local 低命中率部分结构性**：拖累主体是 maodaren/9you 对话截图（2653 块 @11.6%，实体密度天然低）；curated-pdf 是 53.2%。LLM 路径在对话 cohort 上限也有限，别期望一把拉到 50%。先在高价值块（registry_gap_candidate）上验证 ROI。
- **幻觉 ticker**：LLM 极易编造 ticker（如把 A 股代码张冠李戴）。validator 的 `evidence_quote` 子串校验 + 格式校验 + 可选 finance-skills 交叉验证是硬门，别省。
- **边界实体**：`MSCI`(指数 vs MSCI Inc 歧义)、`GC0W`(纽约金主连 commodity)、`NV`(=英伟达但 2 字母易误锚) 这类让 LLM 显式标 entity_type + 低 confidence，人工兜底。

## 7. 启动检查清单（新会话第一步）

1. `pwd` 应为 `/Users/zhouhongyuan/Desktop/finer`；`git branch` 确认在 `docs/f0-review-fixes` 或新建分支。
2. 读 `docs/specs/2026-06-26-f2-anchor-hit-rate.md`（上轮结论）+ 本卡。
3. 读范例 `src/finer/parsing/llm_topic_assembly_adapter.py` 全文 + `src/finer/llm/deepseek_client.py` 的 `chat_json` 签名。
4. 跑基线只读测量记录当前数字：`python scripts/backfill_f2_anchor.py --scope all-local --dry-run --gap-candidates-out /tmp/base.jsonl`。
5. 从 Phase 1 开始（纯代码 + mock 测试），到 Phase 3 前停下找用户确认。
6. 任务 >10 min 完成后按 `CLAUDE.md` §12 产出审阅文档。
