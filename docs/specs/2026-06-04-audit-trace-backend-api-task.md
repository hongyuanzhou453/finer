# 任务卡 — Audit Trace 后端 API（P4）

> 类型：后端 Agent 任务卡（可冷启动执行）
> 关联：`docs/specs/2026-06-04-dashboard-audit-trace-frontend.md` §7（前端已 fixtures 先行完成）
> 目标：实现两个只读端点，让前端 `/audit` 从 fixtures 切到真实数据
> 日期：2026-06-04

---

## 0. 任务声明（遵循 CLAUDE.md §10 / AGENTS.md）

| 项 | 内容 |
|---|---|
| Parallel line | Audit Trace Backend API |
| F-stage | **cross-stage read-only aggregator**（只读取 F2/F3/F4/F5 落盘产物并组装；不修改任何 pipeline 逻辑、不新增/改 schema） |
| 输入 schema | `trade_action_id`（path）、筛选 query 参数 |
| 输出 schema | `AuditTraceBundle` / `TradeActionSummary[]`（**必须与前端 `src/finer_dashboard/src/lib/contracts.ts` 字段名/类型逐字对齐**，见 §4） |
| 允许修改/新建 | `src/finer/api/routes/audit.py`（新建）、`src/finer/api/server.py`（仅注册 router）、`src/finer/services/audit_assembler.py`（新建，可选）、`tests/test_audit_api.py`（新建） |
| 禁止修改 | `src/finer/pipeline/**`、`extraction/**`、`policy/**`、`schemas/**`、`src/finer_dashboard/**`（前端契约已冻结） |
| 验收命令 | `pytest tests/test_audit_api.py -v`；`uvicorn finer.api.server:app` + curl（见 §8） |

**禁止**：不得复用 legacy `services/lineage.py`（`get_lineage_tracker`/`trace_back`）——那是旧的 content/segment/event 血缘，**不是** F3→F4→F5 canonical 链路。新端点直接按 id 读 F-stage 落盘文件组装。

---

## 1. 背景

前端 `/audit` 证据审计台已完成（fixtures 驱动），数据层 `src/finer_dashboard/src/lib/audit-api.ts` 通过 `NEXT_PUBLIC_AUDIT_USE_FIXTURES` 切换。后端实现本任务后，前端设 `NEXT_PUBLIC_AUDIT_USE_FIXTURES=false` 即接真实数据，**前端零改动**。

canonical pipeline `pipeline/golden_path.py` 已按 id 落盘各 stage 产物：

| Stage | 落盘路径 | 内容（`model_dump()`） | 代码 |
|---|---|---|---|
| F3 | `data/F3_intents/{intent_id}.json` | `NormalizedInvestmentIntent` | `golden_path.py:100-105` |
| F4 | `data/F4_policy_mapped/{policy_id}.json` | `PolicyMappingResult` | `golden_path.py:114-116` |
| F4 batch | `data/F4_policy_mapped/{envelope_id}.batch.json` | `PolicyMappedIntentBatch` | `golden_path.py:117-120` |
| F5 | `data/F5_executed/{trade_action_id}.json` | `TradeAction` | `golden_path.py:157-162` |
| F2 input | `data/F2_anchored/{envelope_id}.json` | `ContentEnvelope`（原文 + blocks） | `extraction.py:24` |

> ⚠️ 这些目录当前可能为空（尚未实跑 golden_path）。先用 `scripts/run_backtest_e2e.py` 或直接调 `run_golden_path(envelope)` 产出几条样本数据，再开发/自测。

---

## 2. 端点 1：`GET /api/audit/actions`

左栏动作清单。

- **Query**：`kol_id?`、`ticker?`、`trace_status?`（`canonical|partial|non_canonical`）、`validation_status?`、`limit?`（默认 100）、`offset?`（默认 0）
- **数据源**：扫描 `data/F5_executed/*.json`，每个反序列化为 `TradeAction`，投影为 `TradeActionSummary`，按 query 过滤。
- **响应**：`{ "ok": true, "data": { "actions": TradeActionSummary[], "total": number } }`
- **缓存**：懒加载 + TTL 索引（遵循 CLAUDE.md §5 manifest 索引约定；可参考 `api/routes/f0_index.py` 的索引缓存模式）。Finer OS 启动默认不得递归扫描，索引按需构建。

---

## 3. 端点 2：`GET /api/audit/actions/{trade_action_id}/trace`

中栏 + 右栏的完整证据链。返回 `AuditTraceBundle`。

- **响应**：`{ "ok": true, "data": AuditTraceBundle }`
- **组装链路**（按 id 顺读，缺段置 `null`）：

```
trade_action_id
  └─ data/F5_executed/{trade_action_id}.json          → trade_action: TradeAction
       ├─ .intent_id   → data/F3_intents/{intent_id}.json        → intent: NormalizedInvestmentIntent | null
       ├─ .policy_id   → data/F4_policy_mapped/{policy_id}.json   → policy: PolicyMappingResult | null
       ├─ intent.envelope_id → data/F2_anchored/{envelope_id}.json → envelope（原文）+ evidence_spans
       └─ .evidence_span_ids → 从 envelope 过滤出对应 EvidenceSpan[]
```

- `intent_id` 缺失或文件不存在 → `intent = null`（链路在 F3 断裂）
- `policy_id` 缺失或文件不存在 → `policy = null`（F4 断裂）
- 三段齐全 → `trade_action.canonical_trace_status` 应已是 `"canonical"`（F5 schema 的 model_validator 自动算，直接透传）

---

## 4. 输出契约（与前端 contracts.ts 逐字对齐）

> 后端用 Pydantic 组装；字段名/类型必须与下方一致（前端已冻结）。

### `TradeActionSummary`（端点 1）
```
trade_action_id: str
ticker: str                      # = trade_action.target.ticker
company_name: str | None         # = target.company_name
direction: str                   # bullish|bearish|neutral|watchlist|risk_warning
summary: str                     # 见 §5 派生规则
canonical_trace_status: str      # canonical|partial|non_canonical
validation_status: str           # pending|verified|failed|under_review
kol_id: str | None               # 见 §5 映射
created_at: str (ISO)
backtest_return_pct: float | None
```

### `AuditTraceBundle`（端点 2）
```
trade_action: TradeAction            # F5 完整 model_dump（前端只用子集，全量透传即可）
intent: NormalizedInvestmentIntent | null
policy: PolicyMappingResult | null
evidence_spans: EvidenceSpan[]       # F2，可为 []（见 §6）
envelope: { envelope_id, source_text, source_published_at?, creator_id?, kol_id? }
```

> `NormalizedInvestmentIntent` / `PolicyMappingResult` / `TradeAction` / `EvidenceSpan` 直接用 `src/finer/schemas/` 的 `model_dump(mode="json")`，字段天然对齐（前端 contracts.ts 就是按这些 schema 镜像的）。`envelope` 是裁剪投影：从 `ContentEnvelope` 取 `envelope_id` + 拼接出 `source_text`。

---

## 5. 字段派生规则

| 字段 | 来源 / 规则 |
|---|---|
| `kol_id` | 优先 `trade_action.source.creator_id`；为空时回退 `intent.creator_id`。（本项目 creator = KOL；如后续区分需确认） |
| `summary` | TradeAction 无 `summary` 字段。派生：取 `trade_action.rationale`，截断至 ~40 字；为空时由首个 `action_chain[0]`（action_type + trigger_condition）拼一句。 |
| `backtest_return_pct` | `trade_action.backtest_result.return_pct`（若 `backtest_result` 存在），否则 `null`。 |
| `envelope.source_text` | 从 `ContentEnvelope` 的 blocks 拼接原文纯文本（与 F1 标准化保留的原文一致）。 |
| `envelope.kol_id` | 同 `kol_id` 规则。 |

---

## 6. 已知缺口：evidence_spans（必须正视）

`golden_path.py` **不单独落盘 EvidenceSpan 本体**；F2 独立 resolver 也尚未实现（见 `2026-06-03-full-project-review.md` TD-02）。`intent.evidence_span_ids` 是引用，但 EvidenceSpan 对象当前无稳定落盘来源。

**MVP 处理（推荐）**：端点 2 返回 `evidence_spans: []`。前端已对空证据优雅降级（右栏显示"无 F2 锚定证据，legacy 直提"提示），不阻塞上线。

**完整方案（后续，需单独排期，不在本卡）**：
- 选项 A：`golden_path.py` 增补一行，把 F3 `extraction_result.evidence_spans` 落盘到 `data/F2_anchored/{envelope_id}.evidence.json`，trace API 读取并按 `evidence_span_ids` 过滤。
- 选项 B：F2 EvidenceResolver 落地后由其产出 EvidenceSpan（治本）。

> 本卡只要求 MVP（`evidence_spans: []` 或选项 A 二选一）。若选 A，仅可改 `golden_path.py` 的落盘段，不得改 F3/F4/F5 逻辑——但这会越过本卡的"禁止修改 pipeline"边界，**需先与负责人确认**。

---

## 7. Error Envelope（强制，CLAUDE.md / Line F）

- 使用 canonical envelope（`src/finer/errors/`）。`trade_action_id` 不存在 → `raise FinerNotFoundError(...)`（`errors/exceptions.py:105`）。
- 必带：`request_id`、`stage`（如 `"F5_audit"`）、`operation`（如 `"get_trace"`）、`retryable=false`、`fix_hint`。
- 参照现有 route 的抛错模式（如 `api/routes/extraction.py`、`f0_index.py`）。
- **details 禁止出现** token / secret / password / cookie / authorization / api_key。

---

## 8. 注册与验收

### 注册（server.py，照 `server.py:4` import + `:54` 注册模式）
```python
from finer.api.routes import ..., audit          # line 4 追加
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])  # 注册段追加
```

### 验收
```bash
# 1. 产出样本数据（若 data/F5_executed 为空）
python -m finer... run_golden_path  # 或 scripts/run_backtest_e2e.py

# 2. 单测
pytest tests/test_audit_api.py -v

# 3. 手动
curl 'localhost:8000/api/audit/actions?trace_status=canonical'
curl 'localhost:8000/api/audit/actions/{trade_action_id}/trace'

# 4. 端到端：前端 src/finer_dashboard/.env.local 设 NEXT_PUBLIC_AUDIT_USE_FIXTURES=false
#    npm run dev → /audit 显示真实数据
```

### 测试要点（tests/test_audit_api.py）
- 三态：canonical（F3+F4 齐）/ partial（缺 F4 文件）/ non_canonical（缺 F3+F4）→ bundle.intent/policy 正确为 null
- 列表筛选：trace_status / kol_id / ticker 生效
- not found：未知 trade_action_id → FinerNotFoundError envelope（含 request_id/fix_hint，无敏感字段）
- 字段对齐：bundle JSON 的 key 与前端 `AuditTraceBundle` 一致

---

## 9. 完成定义（DoD）

- [ ] 两端点实现，响应结构 = §4
- [ ] 缺段正确置 null（partial/non_canonical 可还原）
- [ ] error envelope 合规（§7）
- [ ] `pytest tests/test_audit_api.py -v` 全绿
- [ ] 前端 `NEXT_PUBLIC_AUDIT_USE_FIXTURES=false` 后 `/audit` 三态、筛选、`?kol=` 深链均工作
- [ ] 未触碰 pipeline/schema/前端文件（evidence 选项 A 除外，且需先确认）
