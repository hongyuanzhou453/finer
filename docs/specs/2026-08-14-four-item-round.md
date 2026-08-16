# 四项收口轮：比率泄漏、导航、币种归一、T3 保真抽检

> 基线：`d61252b4`（三分支合并推送后）。本轮全部落在 `main`，宣传站已部署。
> 前置勘察见 `memory/next-steps-2026-08-13.md`；同型缺陷模式见
> `memory/gates-that-fail-open.md`。

## 1. 概述

四项按用户指定顺序完成：公开站比率泄漏（已部署）、Dashboard 导航与深链、
币种别名归一、T3 抽取保真度抽检 n=150。**抽检结论：逐字段错误率
0.00%–0.79%，95% 上界约 3–4%**，比此前唯一证据（n=40，上界 10.7%）收紧一半以上。

一条贯穿本轮的模式：**四处缺陷都是「门写对了，但开在门外或开反了方向」**，
且信号全绿——测试通过、linter 退出码 0、类型检查无警告。

## 2. 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/export_site_records_snapshot.py` | 修改 | `_strip_ratios_when_count_only()`：count_only 卡的比率字段置 null |
| `src/finer_site/src/demo/records/types.ts` | 修改 | `mean_return` 等改 `number \| null` |
| `src/finer_site/src/components/records/primitives.tsx` | 修改 | `fmtSignedPct`/`returnColor` 显式挡 null |
| `src/finer_site/src/components/records/RecordCardWall.tsx` | 修改 | 均值收益移进 count_only 门内 |
| `src/finer_site/src/components/records/CreatorRecordView.tsx` | 修改 | 同上（第二处泄漏点） |
| `src/finer_site/src/components/demo/demo-workbench.tsx` | 修改 | `RATIO_MIN_SAMPLE=15` 门 |
| `src/finer_site/src/app/kol-check/page.tsx` | 修改 | 旧口径文案收尾 |
| `src/finer_site/src/components/kol-check/KolCheckReport.tsx` | 修改 | 同上 |
| `src/finer_site/public/records-data/**` | 重导 | as_of 2026-08-10（真实冻结日） |
| `tests/test_site_records_snapshot.py` | 新增 | 对**真实发布物**全量扫描，3 条 |
| `src/finer_dashboard/src/components/layout/sidebar.tsx` | 修改 | +/discover +/ticker；/radar 降级 |
| `src/finer_dashboard/src/app/audit/page.tsx` | 修改 | 深链下推后端 + 未命中明说 |
| `src/finer/credibility/consensus.py` | 修改 | `normalize_currency()`、子单位分桶、平局不聚合 |
| `tests/test_credibility_views.py` | 修改 | +5 条币种测试 |

## 3. 逐项结果

### 3.1 公开站比率泄漏（已部署 finer.t800.click）

`CardRatioBlock` / `HeaderRatio` 挡住了命中率，但紧接着的 `<dl>` 在门**外面**
无条件渲染「均值收益（历史）」——均值收益也是比率。已发布快照实测：

- 34 张 count_only 卡中 **24 张印出真实均值收益**（KeyBanc n_settled=1 → **+58.0%**）
- **10 张 mean_return 为 null，被印成「0.0%」**（`Math.abs(null)=0`，凭空造数）

四层同修：数据层（导出器置 null，最稳——快照发出去不再重算）、类型层
（`number | null` 让 tsc 逼出空值分支）、格式化层、渲染层。

同批发现并修掉的两处同类：`/demo` 的五个 `win_rate` 里**四个在算术上根本不可能**
（n=2 只能是 0/50/100%，却写着 0.72/0.51/0.6/0.58）；`/kol-check` 的
「晨星/体检/战绩/自述 vs 实盘/逢低抄底」旧框架残留词。

线上验收：`/records` 34 张 count_only 卡比率实值 **0 张**；`/demo` 无
`N.N% · n=<10`；`/kol-check` 五个旧词全 0。

### 3.2 Dashboard 导航

- `/discover`、`/ticker` **全仓零入站链接**（`rg` 零命中）——为新定位建的两页
  没有任何路径能走到。已加入侧边栏并置首位。
- `/radar` 按「信誉分」降序、无 sufficiency/区间/声明，却挂 LIVE 且排在最前。
  已降至末位、去 LIVE、标「旧口径」。**页面本身未改造，去留待拍板。**
- `/audit` 深链**静默回落 `data[0]`**：客户端匹配 `?kol=`，而现役 4,919 条
  action 里第 1000 条之后的信源永远匹配不上，匹配不上就展示列表第一条。
  改为下推后端（三个 query 参数早已实现，后端零改动）+ 未命中明确提示。

### 3.3 币种归一

`(currency or "?").upper()` 一行三个问题：

| 问题 | 实测影响 |
|---|---|
| 同币种不同写法算「不符」 | 104 条 excluded 中 52 条（41 只票） |
| `GBp` 被 upper 成 `GBP` | 便士/镑差 100 倍；43 只非 `.L` 英股不受后缀门保护 |
| `max()` 平局取 dict 插入序 | 19 只票的「共识」取决于读取顺序 |

`excluded_currency_mismatch` **104 → 20**；平局改为不聚合（逐源行仍展示）。
别名表逐条有实证并用市场后缀交叉确认（`M$`/`P$` 在 `.MX` 上是墨西哥比索，
不是林吉特）；`KWF`（疑似 KWD 笔误）刻意不映射。

### 3.4 T3 保真抽检 n=150

判据先于抽样写死在
`scratchpad/t3_audit/CRITERIA.md`；全语料随机（`Random(20260814)`），
150/150 join 命中、PDF 全部存在。10 个 agent 并行回原始 PDF 逐条核对。

| 字段 | match | mismatch | N/A | 不可核验 | 错误率 | 95% 区间 |
|---|---|---|---|---|---|---|
| ticker | 127 | 0 | 0 | 23 | 0.00% | [0.00%, 2.94%] |
| rating | 127 | 0 | 0 | 23 | 0.00% | [0.00%, 2.94%] |
| target_price | 118 | 0 | 9 | 23 | 0.00% | [0.00%, 3.15%] |
| report_date | 126 | **1** | 0 | 23 | 0.79% | [0.14%, 4.33%] |

- **整条全对 126 / 127 = 99.2%**
- **图片型 PDF（无文字层）23 / 150 = 15.3%** —— 这是覆盖缺口，不是错误
- 对照：此前唯一证据是 n=40、上界 10.7%，且抽样框取自 `no_occurrence` 桶（有偏）

## 4. 架构影响

- `normalize_currency()` 是 CRD-3 的新公开函数，`GBX`/`ZAX` 是本仓自定的子单位
  桶键（ISO 4217 无子单位代码），只在聚合内部使用，不进 schema、不进 contracts.ts。
- 导出器新增的比率剥离**改变了快照 payload 契约**：count_only 卡的
  `mean_return`/`median_return`/`expected_win_rate` 一律为 null，
  前端类型已同步为 `number | null`。
- `/audit` 前端改为下推过滤，后端 `GET /api/audit/actions` 契约未变。

## 5. 关键决策

1. **比率纪律钉在数据层而非渲染层。** 快照是冻结档案、发出去不再重算；
   payload 里没有实值，前端任何一处漏门都无从泄漏。渲染层的门同时也修了，
   但它不是最后一道。
2. **平局不选胜者。** 改成字母序只是把随机换成确定性；一个取决于字母序的
   「共识」不是共识。代价是 19 只票（0.8%）失去目标价聚合，逐源行仍在。
3. **`as_of` 用真实冻结日 2026-08-10，不用重导当天的 08-14。** 数据内容与
   08-10 那份完全相同，标 08-14 会让静态档案显得比实际新 4 天。
4. **抽检存疑一律判 match。** 估的是错误率上界，宁可低估错误也不用模糊判断
   制造假错误。
5. **`/radar` 只降级不改造。** 按 UI-1 重做还是删除是产品决策。

## 6. 验证结果

```
pytest tests/ -q                      4109 passed, 22 skipped
scripts/audit_trace_integrity.py      ✓ 4919/4919（span 128905/128905）
scripts/check_contract_drift.py       ✓ 33 mapped enums in sync
tsc --noEmit（dashboard / site）       exit 0
npm run build（dashboard / site）      通过
```

**探针**（新测试必须能在旧代码上失败，否则等于没钉）：

| 修复 | 回退后 |
|---|---|
| 币种归一 | 3 failed（含 BATS 混出 median 1717） |
| 快照比率 | 2 failed（对真实发布物） |

**浏览器/线上实测**：`/discover` 板块页百分比 0 次；`/audit?kol=汇丰` 直接命中、
`?kol=不存在的信源XYZ` 渲染「未找到对应记录」；线上 manifest 34 张 count_only
卡比率实值 0 张。

## 7. 未解决项

1. **6 条 report_date 抽取错误未修（需授权改数）。** 5 条记成 2023 年
   （抽检抓到 `bri_6e18c668835ed56866f5a38e`，回原 PDF 实为 2025-11-13，差整两年）
   + 1 条记成 2026-12-16（未来）。使摩根士丹利/花旗/巴克莱三张卡的「记录窗口」
   凭空长出两年，已随快照对外。`tests/test_site_records_snapshot.py` 的
   `_KNOWN_OUT_OF_WINDOW` 已钉住不许变多。
2. **`audit_broker_data_quality.py` 的 Q3 时间门过松**：过去界是 2020-01-01，
   而语料窗是 2025-08 起，2023 年的日期照样放行。建议收紧到语料窗。
3. **图片型 PDF 15.3% 无文字层**，四个字段均不可核验。OCR 回退决策仍未定。
4. **`/radar` 去留未定**（见决策 5）。
5. **M1 口径背离的 30 条人工核对未跑**——外置盘已挂回，可以做了。
