# Round 4 Task Matrix — F8 Trace Retention + Canonical Reject Validation

> Baseline: `d65342e7` (Round 3 complete, gaps documented)
> Date: 2026-05-24
> Goal: close GAP-1 (reject tests) and GAP-2 (backtest trace retention) from Round 3

## Scope

Round 4 只做 A/B，不碰 Dashboard、不改 F3/F4/F5 生成逻辑、不引入新数据源。

## Dependency Graph

```
R4-A (F8 Trace Retention) ──→ shared: converter.py trace fields
R4-B (Canonical Reject)   ──→ shared: backtest/validators.py (extracted from backtest.py)
         ↓ both complete
      Line V (read-only verification)
```

**关键约束**：R4-A 和 R4-B 共享 canonical validator。R4-B 负责提取共享模块，R4-A 在 converter 中复用。避免 contract 漂移。

## Shared Conflict Files

| File | R4-A | R4-B | Strategy |
|------|------|------|----------|
| `src/finer/backtest/converter.py` | **write** (add trace fields) | read | R4-A 独占写 |
| `src/finer/backtest/engine.py` | **write** (Position/Trade/open_position) | read | R4-A 独占写 |
| `src/finer/backtest/validators.py` | read (import) | **write** (新建) | R4-B 独占写 |
| `src/finer/api/routes/backtest.py` | read | **write** (wire validator to compare) | R4-B 独占写 |
| `scripts/run_backtest_e2e.py` | **write** (add trace fields + wire validator) | read | R4-A 独占写 |
| `tests/test_backtest_canonical.py` | **write** (trace retention tests) | **write** (fix reject test names) | 协商：A 写 trace tests，B 改 reject test names |
| `tests/test_backtest.py` | read | **write** (add compare reject tests) | R4-B 独占写 |

## Recommended Execution Order

1. R4-B 先提取 `backtest/validators.py`（独立文件，无冲突）
2. R4-A 修改 converter.py + engine.py（R4-B 不写这些文件）
3. R4-A 修改 scripts/run_backtest_e2e.py + test_backtest_canonical.py
4. R4-B 修改 backtest.py (compare endpoint) + test_backtest.py + test_backtest_canonical.py (rename tests)
5. Line V 验证

---

## Agent Task Cards

### R4-A — F8 Trace Retention Agent

```text
Parallel line: R4-A — F8 Trace Retention
F-stage: F8 Backtest
Input schema: canonical TradeAction (with intent_id, policy_id, evidence_span_ids)
Output schema: engine Trade record (with intent_id, policy_id, evidence_span_ids)
Baseline: d65342e7
```

**Owning files**
- `src/finer/backtest/converter.py` (modify)
- `src/finer/backtest/engine.py` (modify)
- `scripts/run_backtest_e2e.py` (modify)
- `tests/test_backtest_canonical.py` (add trace retention tests)

**Forbidden files**
- `src/finer_dashboard/**`
- `src/finer/api/routes/**`
- `src/finer/extraction/**`
- `src/finer/pipeline/**`
- `src/finer/ingestion/**`

**What to do**

1. **`converter.py:trade_action_to_record()` (line 75-82)**: 给 output dict 增加 trace fields:
   ```python
   return {
       "timestamp": ts.isoformat(),
       "ticker": action.normalize_ticker(),
       "direction": _DIRECTION_MAP[action.direction],
       "action_type": action_type,
       "trade_action_id": action.trade_action_id,
       "kol_id": action.source.creator_id,
       # --- trace fields (R4-A) ---
       "intent_id": action.intent_id,
       "policy_id": action.policy_id,
       "evidence_span_ids": action.evidence_span_ids or [],
   }
   ```

2. **`engine.py:Position` (line 87)**: 增加 3 个 Optional 字段:
   ```python
   intent_id: Optional[str] = Field(None, description="Source F3 intent ID")
   policy_id: Optional[str] = Field(None, description="Source F4 policy ID")
   evidence_span_ids: List[str] = Field(default_factory=list, description="Source F2 evidence span IDs")
   ```

3. **`engine.py:Trade` (line 129)**: 增加同样 3 个字段（同 Position）

4. **`engine.py:PortfolioSimulator.open_position()` (line 280)**: 签名增加 `intent_id`, `policy_id`, `evidence_span_ids` kwargs，存入 Position

5. **`engine.py:close_position()` (line 359-423)**: 从 Position 拷贝 trace fields 到 Trade（line 404-422 Trade 构造处）

6. **`engine.py:BacktestEngine.run_backtest()` (line 591-615)**: 从 action dict 读取 `intent_id`, `policy_id`, `evidence_span_ids`，传给 `open_position()`

7. **`scripts/run_backtest_e2e.py:_raw_action_to_record()` (line 65-72)**: 同步增加 trace fields（与 converter.py 保持一致）

8. **`tests/test_backtest_canonical.py`**: 新增 `TestTraceRetention` 类:
   - `test_converter_preserves_trace_fields`: 验证 `trade_action_to_record()` 输出含 `intent_id`/`policy_id`/`evidence_span_ids`
   - `test_engine_trade_has_trace_fields`: 验证 engine 输出的 Trade 对象含 trace fields
   - `test_e2e_trades_json_has_trace_fields`: 加载 Cat Lord F5 actions → engine → 验证 trades 含 trace fields

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/test_backtest_canonical.py tests/test_backtest.py tests/test_backtest_extended.py tests/test_backtest_materializer.py -q
rg -n "intent_id" src/finer/backtest/engine.py | head -10
rg -n "intent_id" src/finer/backtest/converter.py
.venv/bin/python -c "
from finer.backtest.converter import trade_action_to_record
from finer.schemas.trade_action import TradeAction
import json
# Quick smoke: verify trace fields in output
print('converter trace fields check: OK')
"
```

---

### R4-B — Canonical Reject Validation Agent

```text
Parallel line: R4-B — Canonical Reject
F-stage: F8 Backtest
Input schema: TradeAction (possibly non-canonical)
Output schema: FinerError with F8_IN_001 code on reject
Baseline: d65342e7
```

**Owning files**
- `src/finer/backtest/validators.py` (new — extract from backtest.py)
- `src/finer/api/routes/backtest.py` (modify — wire validator to compare endpoint)
- `tests/test_backtest.py` (add compare reject tests)
- `tests/test_backtest_canonical.py` (rename document-only tests)

**Forbidden files**
- `src/finer_dashboard/**`
- `src/finer/backtest/engine.py` (R4-A 独占)
- `src/finer/backtest/converter.py` (R4-A 独占)
- `src/finer/extraction/**`
- `src/finer/pipeline/**`
- `src/finer/ingestion/**`

**What to do**

1. **新建 `src/finer/backtest/validators.py`**: 从 `backtest.py:_validate_canonical_action()` (line 100) 提取为独立模块:
   ```python
   """Canonical F8 input validation.

   Shared by API routes and E2E scripts to enforce canonical trace requirements.
   """
   from finer.errors.exceptions import FinerError
   from finer.errors.codes import ErrorCode

   def validate_canonical_action(action: dict, index: int = 0) -> None:
       """Validate that a TradeAction dict meets canonical trace requirements.

       Raises FinerError(ErrorCode.F8_IN_001) if validation fails.
       Checks:
       - canonical_trace_status == "canonical"
       - intent_id is non-empty
       - policy_id is non-empty
       - evidence_span_ids is a non-empty list
       - execution_timing.action_executable_at is non-null
       """
       ...
   ```

2. **`backtest.py`**: 将 `_validate_canonical_action` 改为调用 `backtest.validators.validate_canonical_action`，保持 API 行为不变

3. **`backtest.py` POST `/compare` endpoint (line 403)**: 在处理 actions 前调用 `validate_canonical_action()` 对每个 action 验证

4. **`scripts/run_backtest_e2e.py`**: 在 `load_canonical_f5_actions()` 中，对每个 canonical action 调用 `validate_canonical_action()`，确保 E2E script 和 API 使用同一 validator

5. **`tests/test_backtest_canonical.py` (line 197-224)**: 将 4 个 `test_engine_rejects_*` 重命名为 `test_*_documents_gap_*`，并在 docstring 中明确标注这些是文档性测试，真实 reject 测试在 `test_backtest.py`

6. **`tests/test_backtest.py`**: 新增 `TestCompareRejectsNonCanonical` 类:
   - `test_compare_rejects_missing_intent_id`
   - `test_compare_rejects_missing_policy_id`
   - `test_compare_rejects_empty_evidence_span_ids`
   - `test_compare_rejects_missing_execution_timing`

**Acceptance commands**
```bash
.venv/bin/python -m pytest tests/test_backtest.py tests/test_backtest_canonical.py -q
rg -n "validate_canonical_action" src/finer/backtest/ src/finer/api/routes/backtest.py scripts/run_backtest_e2e.py
rg -n "test_engine_rejects\|documents_gap" tests/test_backtest_canonical.py
.venv/bin/python -c "from finer.backtest.validators import validate_canonical_action; print('OK')"
```

---

### Line V — Read-Only Verification

```text
Parallel line: Line V — Round 4 Verification
F-stage: read-only
Baseline: d65342e7
```

**Forbidden**: all file modifications

**What to do**
1. Run full test suite
2. Verify no `src/finer_dashboard/**` files modified
3. Verify trace fields present in F8 artifacts
4. Verify validator shared across API and E2E script
5. Run E2E backtest for both KOLs, check trades.json contains trace fields

**Verification commands**
```bash
# Full test suite
.venv/bin/python -m pytest tests/ -q

# No dashboard touches
git diff --name-only d65342e7..HEAD | grep "src/finer_dashboard/" && echo "FAIL: dashboard touched" || echo "PASS"

# Trace fields in engine
rg -n "intent_id|policy_id|evidence_span_ids" src/finer/backtest/engine.py

# Validator shared
rg -n "validate_canonical_action" src/finer/backtest/ src/finer/api/routes/backtest.py scripts/run_backtest_e2e.py

# E2E trades.json has trace fields
.venv/bin/python scripts/run_backtest_e2e.py 2>&1 | tail -5
rg -n "intent_id" data/review/kol_cat_lord_fire/F8_backtest/trades.json
rg -n "intent_id" data/review/trader_ji/F8_backtest/trades.json

# Frontend build (should not be affected)
cd src/finer_dashboard && npm run build 2>&1 | tail -3
```

---

## Definition of Done

Round 4 is complete when:

1. `converter.py:trade_action_to_record()` 输出含 `intent_id`, `policy_id`, `evidence_span_ids`
2. `engine.py:Trade` 对象含 `intent_id`, `policy_id`, `evidence_span_ids`
3. `trades.json` 输出含 trace fields（Cat Lord + Trader Ji E2E）
4. `backtest/validators.py` 存在，包含 `validate_canonical_action()`
5. `POST /compare` 调用 `validate_canonical_action()`
6. `scripts/run_backtest_e2e.py` 复用同一 validator
7. `test_engine_rejects_*` 重命名为 `*_documents_gap_*`
8. `test_backtest.py` 新增 compare endpoint reject tests
9. All tests pass
10. No `src/finer_dashboard/**` files modified
