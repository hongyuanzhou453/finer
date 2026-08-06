# 2026 段全量处理（2026-08-06）

## 概述

把 2026 年清单里剩余的 3,639 条研报全部过完 F0→F1→F2→F3→F5。
**两个验收指标（≥3 源覆盖、中位新鲜度）一个没动**——这是处理前就说明的
结构性事实，不是失败。

## 处理量

| 阶段 | 前 | 后 |
|---|---:|---:|
| broker F0 记录 | 21,853 | **27,621** |
| F1 标准化 | 21,833 | **25,349** |
| F2 锚定 | 9,859 | **11,233** |
| canonical action | 4,577 | **4,919** |
| t9i 板块 action | 58 | **400** |
| 三向审计 | 100% | **100%**（128,905 span） |

## 验收指标：零变化，且是预期内的

```
≥3 家信源覆盖    332 (13.4%)  →  332 (13.4%)
中位最新报告日   2025-12-19   →  2025-12-19
三个月以上陈旧   70%          →  70%（同口径 <2026-03）
```

**原因是构成**：这批 3,639 条里 3,552 条是**行业研报**，产的是板块观点
（11 个 ETF 代理），不产个股观点；个股研报在处理前就已吃掉 96–98%，
标的层面没有可动空间。真实产出是语料完整性 + F7 宏观原料。

## 途中处理的三件事

### 1. 口径污染（驱动前拦住）

t9i **板块**观点与 bri **个股**评级共用 `signal_class="broker_recommendation"`。
存量 58 条时占 1.4% 可忽略，驱动 680 条后会到 ~14%——两者基准率不同，
混算等于把「选股」和「押赛道」平均掉。

按 R6 隔离先例加第三档 `broker_sector_view`：`action_composer` 按
`target_type == "sector"` 分流，存量 58 条回填，契约漂移守卫如实拦下未同步的
`contracts.ts`。记分卡 26 → 24 张（纯板块信源不再混入个股口径），
`/discover` 加口径开关，物化两个口径共 48 张卡。

### 2. F2 缺口与「按需求驱动」

t9i 第一轮 F5 **零产出**，32 条全被证据门拒（`evidence_not_grounded_in_f2` /
`evidence_empty_not_auditable`）——新 F1 信封还没过 F2。**证据门拦对了**，
它守的正是「每个数字可下钻」。

全量 F2 回填要 **32 小时**（实测中位件 18 块 / 49,478 字符、单条锚定 8.28s，
成本是 O(字符 × 注册表别名)）。但真正需要的只是 t9i intent 指向的
**472 个信封 = 51 分钟**。新增 `scripts/anchor_f2_for_intents.py`：
从 F3 intent 收集 `envelope_id` 反向驱动，而不是按存量扫。
全量回填是独立课题，不该挡住一次具体交付。

> **测量教训**：我第一次 profile 用了个 7 块的样本（0.04s），据此判断
> 「瓶颈在驱动循环」——错的。真实积压件大两个数量级，驱动器 87% CPU
> 满负荷跑，5.5 条/分钟就是它该有的速度。**样本不具代表性时，profile
> 结论比没有结论更危险。**

### 3. `.env` 未被流水线加载（运维缺口）

F1 首跑报 `No available models in registry`——`.env` 就在仓库根目录，但整条
流水线路径没有任何地方加载它（`load_dotenv` 只在几个独立脚本里）。此前能跑通
靠的是启动 shell 恰好 export 过；换 shell 或换 launchd 任务就起不来，
而报错指向「模型没配」，与真因隔着一层。

新增 `ops/env_bootstrap.py`（标准库实现，不引 `python-dotenv`——它没在
`pyproject.toml` 里声明），在 `cli.main()` 最前调用。**已存在的环境变量优先**：
文件是兜底不是权威。干净环境实测 0 → 6 个密钥；6 条测试覆盖引号 / 注释 /
`export` 前缀 / 不成对引号 / 文件缺失。

## 变更清单

| 文件 | 类型 |
|---|---|
| `src/finer/ops/env_bootstrap.py` | 新增 |
| `scripts/anchor_f2_for_intents.py` | 新增 |
| `src/finer/schemas/trade_action.py` | `SIGNAL_CLASS_LITERAL` 增 `broker_sector_view` |
| `src/finer/extraction/action_composer.py` | 按 `target_type` 分流 signal_class |
| `src/finer/extraction/sector_transmission_adapter.py` | 产出新档 |
| `src/finer/projections/materializer.py` | 物化两个口径 |
| `src/finer/cli.py` | 入口加载 `.env` |
| `src/finer_dashboard/.../discover/page.tsx` | 口径开关 |
| `contracts.ts` / `check_contract_drift.py` | 镜像 + 登记 |
| `tests/test_env_bootstrap.py` / `test_scorecard.py` | 7 条新测试 |

## 验证

`pytest tests/ -q` → **4,147 passed**；`audit_trace_integrity.py` → 4,919/4,919
三向 100%；contract drift 33 枚举同步；浏览器实测 `/discover` 两个口径切换正常，
板块口径全部 `count_only`（最大结算样本 11 条，效力门如实反映）。

## 未解决

- **全量 F2 回填**（约 14,000 条 / 32 小时）：本次只按需补了 472 个，
  其余仍缺 F2。独立课题。
- 2026 年源盘还有 2,496 份 PDF 未进清单（NAMEZY 侧分类器，不在本仓库）。
- 时效性的真正解法是**新增持续来源**，不是把存量再刨一遍。
