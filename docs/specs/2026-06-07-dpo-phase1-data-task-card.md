# 任务卡 · DPO 环 A 阶段 1：训练数据生成（半真实 bootstrap）

> 交给一个 agent 冷启动执行。所有脚本已存在并验证，本卡只运行脚本 + 产数据，**不写任何代码**。
> 关联：`docs/specs/2026-06-07-dpo-bailian-training-line.md`（方法论 §4 半真实、§13 Runbook）。

## 元信息

| 项 | 值 |
|---|---|
| 任务线 | F+ Training / DPO 环 A 数据生成 |
| F-stage | F+（Training Loop）数据准备；**消费** F0 raw transcripts，不改 F0–F8 主链路 |
| 类型 | 数据运维执行（跑既有脚本，**零代码改动**） |
| 输入 | `data/dpo/candidates.jsonl`（已存在）或 `data/raw/**/chat_history_*.md` |
| 输出 | `data/dpo/pairs.jsonl`、`data/dpo/data.jsonl` |

## 授权与前置（执行前逐条校验，任一不满足 → 立即停止并报告）

1. **[闸② 支出授权]** 用户交付本卡即授权本卡内 DashScope 调用（基座 `qwen3-8b`，约 150~450 次，预计 **¥1 以内**）。仅限本卡的 harvest/推理，不得做其他付费调用。
2. **[KEY]** 环境变量 `DASHSCOPE_API_KEY` 必须已设置。agent **只校验是否存在（len>0），严禁打印其值，严禁读取或修改 `.env`**。若未设置：立即停止，报告"请先 `export DASHSCOPE_API_KEY=...` 再执行本卡"，**不要尝试任何其他取 key 途径**。
3. **[CWD]** 工作目录 = `/Users/zhouhongyuan/Desktop/finer`（先 `pwd` 确认）。
4. **[PY]** 一律用 `.venv/bin/python`。

## 允许修改 / 禁止修改

**允许写**：仅 `data/dpo/**` 下数据文件（`candidates.jsonl`、`pairs.jsonl`、`data.jsonl`）+ `/tmp/**` 临时文件。

**禁止碰**：
- `scripts/**`、`src/**`、`docs/**`、`tests/**`、任何 `.py`/`.ts` 代码（脚本有问题只报告，不准改）
- `.env`、任何密钥/配置
- SQLite 表结构、不得批量删除任何已有数据
- 不得改写 F0–F8 业务代码或 schema

## 执行步骤

```bash
# 0) 前置校验
pwd   # 须为 /Users/zhouhongyuan/Desktop/finer
.venv/bin/python -c "import os;assert os.environ.get('DASHSCOPE_API_KEY'),'KEY 缺失';print('KEY ok')"

# 1) 生成候选(留 buffer 防 harvest 丢弃后不足 100；min-signal=2 真实可出 ~153 段)
.venv/bin/python scripts/select_passages.py --out data/dpo/candidates.jsonl --limit 150 --min-signal 2

# 2) 试跑 5 条 —— 成本与质量检查点(必做，先别全量)
.venv/bin/python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl --out /tmp/pairs5.jsonl --model qwen3-8b --limit 5
#    报告: 成功/失败、降级观望数、保留对子数; 贴 1~2 条 rejected vs chosen 给用户看校准是否合理

# 3) 全量 harvest
.venv/bin/python scripts/harvest_rejected.py --in data/dpo/candidates.jsonl --out data/dpo/pairs.jsonl --model qwen3-8b
#    若"保留偏好对" < 100: 报告，并重试一次 --temperature 0.9(诱发更多过度承诺); 仍不足则报告请求加候选, 不准改脚本

# 4) 转百炼 DPO ChatML
.venv/bin/python scripts/to_bailian.py --in data/dpo/pairs.jsonl --out data/dpo/data.jsonl
```

## 验收命令（agent 自验，全绿才算完成）

```bash
.venv/bin/python - <<'PY'
import json
recs=[json.loads(l) for l in open("data/dpo/data.jsonl",encoding="utf-8")]
assert len(recs)>=100, f"data.jsonl 仅 {len(recs)} 行 (<100，不足百炼 DPO 下限)"
for i,r in enumerate(recs):
    assert r["messages"][0]["role"]=="system" and r["messages"][-1]["role"]=="user", f"行{i} messages 结构错"
    for k in ("chosen","rejected"):
        assert isinstance(r[k],dict) and r[k]["role"]=="assistant" and isinstance(r[k]["content"],str), f"行{i} {k} 非 assistant 对象"
    assert r["chosen"]["content"]!=r["rejected"]["content"], f"行{i} chosen==rejected"
import collections
dirs=collections.Counter(json.loads(r["chosen"]["content"]).get("direction","?") for r in recs)
print(f"PASS: {len(recs)} 行合法百炼 DPO ChatML; chosen 方向分布={dict(dirs)}")
PY
```

## 质量报告（给用户）

完成后报告：保留偏好对数、观望(watchlist)在 chosen 中的占比、direction 分布、抽样 3 条（原文片段 + rejected + chosen）、`data/dpo/data.jsonl` 是否通过验收、可否上传百炼。

## 红线

- **不编造**：harvest/推理失败如实报告，**严禁用 mock/--mock 数据冒充真实结果**（本卡禁止用 `--mock`，那是无 key 时验证 harness 用的）。
- **密钥**：不打印、不外泄 `DASHSCOPE_API_KEY`，不读 `.env`。
- **范围**：只跑脚本、只写 `data/dpo/**`；任何代码/schema 不碰。
- **边界**：阶段 1 止于 `data/dpo/data.jsonl`。**不做**百炼上传/训练/部署/评测（阶段 2-3 是用户手动 + 后续卡）。

## 完成标志

`data/dpo/data.jsonl` 通过验收命令（≥100 行合法 ChatML，chosen≠rejected），并向用户交付质量报告 + 抽样样例。
