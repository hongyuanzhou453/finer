# Canonical Trace Quality — F3/F4 落盘 + 真实 rationale + 实体优先级

> 2026-06-25 · F3/F4/F5 · branch `feat/canonical-trace-quality`

## 概述 (Overview)

两件事：② 让 canonical route 把 F3 intents / F4 policy mappings 落盘，点亮审计台的
Intent/Policy 卡，并把 TradeAction 的占位 rationale 换成真实文案；③ 调查"ticker 偏指数/主题"。
② 已完成并验证。③ 经数据核实属**误诊**：索引/板块目标不是被误解析的个股，而是 KOL 在专门
段落里对大盘/板块的真实观点，已由 `instrument_type` 如实标注；本次加了实体类型优先级作为
防御性护栏（防止未来"个股被同段指数遮蔽"），但对当前数据零影响。

## 变更清单 (Changes)

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/pipeline/canonical_runner.py` | 修改 | ② `run_canonical_from_envelope` 增加 `persist_dir` 参数 + `_persist_canonical_artifacts`（写 F3_intents/F4_policy_mapped 每-id sidecar）；`_build_action_rationale` 取代 `"<hint> via <uuid>"` 占位串 |
| `src/finer/api/routes/extraction.py` | 修改 | ② route 传 `persist_dir=output_path.parent`，F3/F4 落到 assembler 读取的根目录 |
| `src/finer/extraction/intent_extractor.py` | 修改 | ③ `_find_entities_in_text` 按 (类型优先级, 名称长度) 排序，tradeable(stock/etf/crypto) 优先于 sector/index/macro |
| `tests/test_canonical_from_envelope.py` | 修改 | +3 测试：F3/F4 落盘→assembler 点亮卡片、无 persist_dir 不写、rationale 人类可读 |
| `tests/test_intent_extractor.py` | 修改 | +2 测试：stock 优先于 index、纯 index 仍解析 |
| `docs/specs/2026-06-25-canonical-trace-quality-f3f4-persist-rationale.md` | 新增 | 本文档 |

## 架构影响 (Architecture Impact)

- **② 审计台链路补全**：之前 route 只落 F5，trace bundle 的 `intent`/`policy` 恒 null →
  Intent/Policy 卡空。现在 F3/F4 落 `data/F3_intents/{intent_id}.json`、
  `data/F4_policy_mapped/{policy_id}.json`（assembler 既有读路径），两卡点亮。
- **persist_dir 设计**：非破坏性可选参数。route 传根目录；其它 5 个 `run_canonical_from_envelope`
  调用点（含 deprecated wrapper + 测试）默认 None → 行为不变、保持只读。
- **rationale**：由 `direction + target + action_hint + 证据片段` 组合（如
  `"bullish EWY · add_position｜依据：抄底"`），人工审计/复核可读。
- **③ 实体优先级**：`_find_entities_in_text` 现在让个股/ETF 排在 index/sector 前，
  `found[0]` 取最具体的 tradeable 实体。`instrument_type`（line 534，既有）继续如实标注
  index→`index_future`、sector→`unspecified`。

## 关键决策 (Key Decisions)

1. **②持久化放 runner 内 + 可选 persist_dir，而非改返回签名。** 5 个调用点期望
   `List[TradeAction]`；加可选参数零破坏。route 负责传根目录（I/O 边界仍在 route 侧控制）。
2. **③ 是误诊，如实报告而非假装修复。** 数据核实：67 个 index/sector intent **全部**来自
   无个股共现的专门段落（0 个"个股被遮蔽"）。所以 16×000001.SH、4×OPTICAL_MODULE 是 KOL 对
   大盘/板块的真实观点，不是解析错误。`instrument_type` 已如实标注，数据不撒谎。
3. **实体优先级护栏仍保留。** 它正确（个股共现时应优先个股）、有测试、零副作用，能防未来
   "个股被同段指数遮蔽"。只是当前数据无此情形，故不改变 16/4 计数。
4. **是否过滤 index/sector action 是产品决策，留给用户。** 砍掉=丢失真实大盘/板块观点；
   保留=审计/回测含非个股标的（但已被 instrument_type 标注，可在审计/回测层按类型筛选）。

## 验证结果 (Verification)

执行环境：worktree `/Users/zhouhongyuan/Desktop/finer-trace-quality`
（`feat/canonical-trace-quality`，基于 `docs/f0-review-fixes` HEAD `87b7bea3`），
临时重生成至 `/tmp/regen_trace`（未动真实数据）。

**② F3/F4 落盘 + rationale（临时重生成真实 14 个 F2）**
```
F3_intents written: 160 | F4_policy_mapped written: 160 | actions: 59
audit list total: 59 | Intent card: POPULATED | Policy card: POPULATED
rationale sample: 'bullish EWY · add_position｜依据：抄底'
```

**③ ticker 分布（修复代码下）**
```
000001.SH(上证): 16 (was 16) | theme tickers: 4 (was 4)   ← 实体护栏对本数据零影响
index/sector intents: 67，其中"与个股共现应优先个股": 0，"纯 index/sector 段落(合法)": 67
```

**测试**
```
pytest tests/test_canonical_from_envelope.py tests/test_intent_extractor.py -q -> 38 passed
全量 pytest tests/ -q -> 2793 passed, 70 skipped, 3 failed
```
3 个失败为预存 `mimo_vision_config` / `live_mimo_multimodal` flake（多次确认无关）。
新增 5 个测试全过，无新增回归。

## 未解决项 (Open Issues)

- **需重生成真实 `data/F5_executed` + 新建 `data/F3_intents`、`data/F4_policy_mapped`**
  （批量重建，需用户确认）：现仅临时重生成至 `/tmp/regen_trace` 验证。重生成后真实审计台
  Intent/Policy 卡才点亮、rationale 才更新。
- **③ index/sector action 的产品取舍（待用户决策）**：是否把 index/sector 观点排除出
  default 个股回测视图、或标 `requires_manual_review`、或仅在审计层按 `instrument_type` 筛选。
  目前如实保留 + 标注。
- **rationale 仍是结构化模板**：用 direction+target+action+证据片段拼装，非 LLM 自然语言。
  够审计可读；若要叙述式文案需走 `llm_guided` 策略（当前 programmatic）。
