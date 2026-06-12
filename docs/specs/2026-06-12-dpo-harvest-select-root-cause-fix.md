# DPO draft 上游根因修复：calibrate 透传幻觉 ticker + 候选混入非投资内容

> 日期: 2026-06-12 · F-stage: F+ Training Loop · 状态: 已实现并验证

## 概述

修复 `pairs_draft.jsonl` 60 条 `ticker not grounded` 的两个 draft 生成阶段根因——`harvest_rejected.py:calibrate()` 透传基座幻觉 ticker（22 条错锚，如把泡泡玛特填成 `002857.SZ`、禾赛填成 `HES`）、`select_dpo_hq_candidates.py` 候选筛选混入非投资内容（11 条无标的，如飞书闲聊靠链接英文串误命中 ticker 正则）——并离线重算当前 152 条 draft，把 60 条错误 ticker 收敛为诚实的 `UNRESOLVED`（原值留存 `meta.ticker_guess`），防止下一批 draft 再产生同类脏数据。

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/harvest_rejected.py` | 修改 | 新增 `UNRESOLVED_TICKER` 常量；`calibrate()` committal+ungrounded 不透传幻觉 ticker，置 UNRESOLVED + 保留方向/conviction 0.3；`harvest()` 组装 meta 时补 `ticker_guess` |
| `scripts/select_dpo_hq_candidates.py` | 修改 | 新增 `STRICT_CODE_RE` + `groundable_entity_hits()` + `_groundable_key()` 归一化；`classify()` 用 groundable 判 multi + 无标的 committal 降级 abstain；`collect_candidates()` 纯闲聊硬过滤 |
| `scripts/recalibrate_draft.py` | 新增 | 一次性离线重算当前 draft（零 API 成本，不覆盖原文件） |
| `tests/test_harvest_calibrate.py` | 修改 | +2 测试：ungrounded→UNRESOLVED、harvest meta.ticker_guess |
| `tests/test_select_candidates.py` | 新增 | 4 测试：裸字母排除、无标的降级、有标的保留、闲聊剔除 |
| `data/dpo/hq_v1/pairs_draft.recalibrated.jsonl` | 新增（数据，不入 git） | 重算结果，待人工对比确认后替换 |
| `data/dpo/hq_v1/pairs_draft_triage.md` 等 | 新增（数据，不入 git） | 前序诊断 + 60 条分诊清单 |

## 架构影响

- 属 F+ Training 线，**不触及 F0-F8 主链路**代码与 API/前端契约。
- 数据契约：chosen 仍恰好 6 键；新增 ticker 哨兵 `UNRESOLVED`（区别于 `NONE`="无标的观望"，表"有方向但标的待人工锚定"）；`meta` 新增可选 `ticker_guess`（meta 是开放字段，不影响 `validate_dpo_hq.py` 的 chosen schema 校验）。
- `validate_dpo_hq.py` 对 committal+UNRESOLVED 仍报 `not grounded`（line 90 仅豁免 `NONE`），正确提示人工补标的——这是期望行为，不是回归。
- `to_bailian.py` 仅 JSON 序列化 chosen，不校验 ticker 枚举；UNRESOLVED 的 pair 在人工签核阶段 edit/reject，不会带 UNRESOLVED 进最终 cleaned 上传包。

## 关键决策

1. **哨兵用 `UNRESOLVED` 而非 `NONE`**：`validate_dpo_hq.ticker_grounded` 对 `NONE` 豁免 grounding 检查（会让 committal 静默放行），对 `UNRESOLVED` 仍 flag。`validate_structure` 只要求 ticker 非空字符串，UNRESOLVED 合法。
2. **保留方向、只换 ticker**：遵循既有 spec 决策3「ungrounded committal 不清零方向，交人工裁决」——根因不在方向，在透传幻觉 ticker。方向/conviction 0.3 不变，幻觉 ticker→UNRESOLVED，原始猜测进 `meta.ticker_guess`（紫金 `601899` 等正确猜测不丢，错锚 `002857` 也留痕供核对）。猜测不写进 rationale，保持训练文本干净。
3. **groundable 只认强标的信号**：严格 A股/港股代码 + entity_registry 中文别名，**排除裸 `[A-Z]{2,5}`**（TICKER_RE 会把飞书链接 `feishu.cn/docx/X26ud…` 的英文串误命中）。`_groundable_key()` 归一化 `601899 ≡ 601899.SH`，防单一标的因代码+registry 双命中被误判 multi_context。
4. **无标的 committal 降级 abstain**（保留为观望训练样本）而非剔除；只有「无强标的 + 无价格 + 无任何多空/观望信号」的纯闲聊才硬剔。
5. **当前 draft 离线重算不覆盖原文件**（写 `.recalibrated` 供确认，命中「批量重写数据」红线由用户拍板替换）；select 改动**只对下一批候选生效，不重跑当前候选池**（避免浪费已生成 draft + 重复花 DashScope）。

## 验证结果

| 验证项 | 命令/方式 | 结果 |
|---|---|---|
| 单元测试 + annotation 回归 | `pytest test_harvest_calibrate + test_select_candidates + test_annotation_store + test_annotation_api` | **46 passed** |
| mock harvest 新行为 | `harvest_rejected.py --mock --limit 20` | 20/20 ungrounded committal → UNRESOLVED + meta.ticker_guess（BABA/AAPL） |
| 离线重算 | `recalibrate_draft.py` | 152 条，evidence 缺失 0；**60 条 ticker→UNRESOLVED**（全留 meta.ticker_guess） |
| 重算后复跑伪 accept-all 诊断 | `validate_dpo_hq.py --min-size 120 --max-size 160` | errors 仍 60（待锚，预期）；60 条 not-grounded 的 chosen.ticker **`{'UNRESOLVED': 60}`，无错误具体代码残留** |

重算样例：`002148.SZ→UNRESOLVED(guess=002148.SZ)`、`HES→UNRESOLVED`、`601899→UNRESOLVED`、`未明确→UNRESOLVED`。

## 未解决项

1. **当前 `pairs_draft.jsonl` 未替换**：重算结果在 `pairs_draft.recalibrated.jsonl`，待用户对比确认后手动替换（批量重写数据红线）。
2. **select 改动未重跑候选池**（下批生效）：下次生成候选时需观察 committal 配额是否因「无标的降级 abstain」而填不满，必要时增源或调 quota。
3. **人工全量签核仍未开始**（设计如此）：60 条 UNRESOLVED 需按 `pairs_draft_triage.md` + `meta.ticker_guess` 逐条 edit 补标的 / 登记 registry-gap / reject；reject ≥2 条后行数回到 ≤150，validate 默认 size 闸口自然通过。
4. 纯 neutral（`is_committal=False`）的 ungrounded ticker 不被改也不被 validate flag（无害边界）；被改的 60 条均为 committal（含 direction=neutral 但 action_chain 含 committal action 的）。
