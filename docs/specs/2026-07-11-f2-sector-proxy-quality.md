# F2 实体锚定质量：sector→ETF 代理映射 + 伪 ticker 守卫（2026-07-11）

## 概述（Overview）

Roadmap P1 #5（`docs/specs/2026-07-11-architecture-priorities.md`）落地：F5 对 sector intent 的处理从「一律拒绝（`sector_target_not_tradable`）」升级为「经 `configs/sector_proxies.yaml` 可配置映射到 ETF 代理执行」，同时补上伪 ticker 硬门。曾被拒的两条储能观点（多空各一）回放后均落在 159566.SZ（储能电池ETF易方达）上，携带完整代理溯源，全量测试 3215 条通过。

## 变更清单（Changes）

| 文件 | 类型 | 内容 |
|---|---|---|
| `configs/sector_proxies.yaml` | 新增 | 16 个板块 → CN 场内 ETF 代理映射（文件真值，含核验层级注释） |
| `src/finer/enrichment/sector_proxy.py` | 新增 | `SectorProxyRegistry`（TTL 60s 缓存，模式同 `services/kol_registry.py`）+ `resolve_sector_proxy()`；加载时拒绝非可交易格式的 instrument；`SectorProxyResolution.audit_metadata()` 输出溯源块 |
| `src/finer/entity_registry.py` | 修改 | ① 14 个板块别名新增（半导体/芯片/光伏/锂电池/锂电/券商/创新药/军工/黄金/恒生科技/机器人/人工智能/白酒/算力），curated 批次，与 proxies 键一致；② `is_plausible_tradable_symbol()`：registry 非 sector 符号集 ∪ 严格 ticker 格式（`\d{4,6}\.(HK\|SH\|SZ)` / `[A-Z]{1,5}`，与 `llm_entity_proposal` 的正则对齐） |
| `src/finer/pipeline/canonical_runner.py` | 修改 | programmatic 与 llm_guided 两路径同步改造（见下） |
| `tests/test_sector_proxy.py` | 新增 | 14 条：registry 单测 / repo 一致性钉子 / 符号校验 / runner 门集成 |
| `tests/test_backfill_f2_anchor.py` | 修改 | gap 候选种子文本剔除现已注册的板块词；新增 `test_registered_sector_terms_anchor_instead_of_gap` 钉住新行为 |

### canonical_runner 两路径的门改造

1. **sector 门**：`target_type == "sector"` → `resolve_sector_proxy(target_symbol, market=intent.market)`；命中 → 继续，TradeAction 落在代理 ETF 上（`TargetInfo.ticker=代理码, instrument_type="etf", company_name=基金简称`），`metadata.sector_proxy` 记录 `{sector_symbol, sector_name, proxy_symbol, proxy_name, rule, config_version}`；未命中 → 拒绝 `reason="sector_proxy_not_configured"`（取代旧 `sector_target_not_tradable`，语义更可操作：修法=加一条 YAML）。
2. **伪 ticker 门**（新增）：非 sector intent 的 `target_symbol` 若既不是 registry 已知非 sector 符号、又不符合严格 ticker 格式 → 拒绝 `reason="pseudo_ticker_symbol"`。中文公司名、占位符、LLM 自造符号不再能进 `TargetInfo.ticker`；格式合法但 registry 未收录的真 ticker（如 ORCL）不受影响。
3. **F2 grounding 顺序**：grounding 仍用**原始 sector 占位符号**查 F2 证据索引（F2 锚的是 储能→ENERGY_STORAGE），先 ground 再改写 target——代理动作的证据链指向 KOL 原话。
4. **交易日历**：`build_execution_timing(market=...)` 对代理动作使用代理 ETF 的市场（执行工具决定日历）。
5. **LLM 路径附带修复**：composed ticker 改用 `matched_intent.target_symbol`（归一符号），不再回显 LLM 输出的 ticker 字符串（回显可能是公司名——本身就是一类伪 ticker 来源）。

## 架构影响（Architecture Impact）

- **分层**：sector→可交易工具的解析归 F2（实体锚定的延伸），实现于 `enrichment/sector_proxy.py`；`pipeline/canonical_runner.py`（cross-stage 编排层）在 F5 构造点只读查询。F4 policy 不感知代理（对 policy 而言 sector intent 与之前无异）。
- **数据契约**：`TradeAction.metadata` 新增可选 `sector_proxy` 溯源块（自由 metadata 字段，无 schema 变更）；`RejectedIntent.reason` 是自由字符串（runner 内 dataclass），新增 `sector_proxy_not_configured` / `pseudo_ticker_symbol` 两个值。前端 `contracts.ts` 与审计路由不枚举 reason 值，无需同步（已核）。
- **下游自动受益**：P0 增量驱动器 `pipeline/driver.py` 的 `_default_f5_executor` 走 canonical runner，新语料的 sector 观点自动代理映射；F8 结算用 `yahoo_prices.yahoo_symbol`（`.SH→.SS`、`.SZ` 直通），代理 ETF 码可直接取价回测。
- **F2 gap 流行为变化**：新增的板块别名使含板块泛称的 block 直接产出 sector `EntityAnchor`，不再流入 registry-gap 候选（`test_registered_sector_terms_anchor_instead_of_gap` 钉住）。`entity_stoplist.CN_SECTOR_THEME_TERMS` 保持不变，仍负责挡 LLM 提议路径的板块泛称——registry 精确别名优先于 stoplist 泛称拒绝，两层不冲突。

## 关键决策（Key Decisions）

1. **映射放 F5 构造点而非改写 F3 intent**：intent 保留 sector 真相（`target_symbol=ENERGY_STORAGE`），只有 TradeAction 落在代理上。时间线/画像仍能按板块聚合，代理只是执行层语义。
2. **ETF 码必须 web 核实，不凭记忆**：跑了 research+双对抗 verify 工作流（16 板块、48 agents）。4 个板块（储能/绿电/光模块/半导体）完成完整双重对抗核验；其余 12 个 research agent 均在 eastmoney 基金档案页核验过代码↔名称配对（confidence 0.85–0.98），对抗复核因 subagent 会话额度中断（非被驳回；光伏组唯一完成的复核为通过）。核验层级已注记在 YAML 注释中。
3. **无纯板块 ETF 时用市场公认代理**：光模块/算力 → 515880 通信ETF（光模块+服务器仓位 >78%）；白酒 → 512690 酒ETF（白酒权重 ~85-90%，161725 为 LOF 不取）。`COMPUTE_POWER` 另配 159819 人工智能ETF 为 priority 2。
4. **同日反向对不在 F5 归零**：两条储能反向观点来自不同 envelope、不同日期、证据 span 独立，是真实的观点分歧；F5 忠实产出对立 action（opinion tier），冲突处理归 F3 共识（反向对归零已有）与未来持仓簿语义，不在执行构造层擅自裁决。
5. **别名扩充守 curated 红线**：14 条人工圈选，未做批量 LLM 写入；刻意排除超泛词（科技/消费/金融/医药/银行/证券），「黄金」保留但列为观察项（黄金坑/黄金周 等子串误锚风险）。
6. **配置加载失败隔离**：坏 YAML → 空 registry（sector 全部退回拒绝路径，不炸 F5）；占位符混进 instruments 在加载时被拒。

## 验证结果（Verification）

```bash
pytest tests/ -q
# 3215 passed, 15 skipped （改动前基线：3213 passed, 1 failed*）
# * test_gap_candidates_filter_generic_terms_and_keep_entity_phrase 因板块词
#   可锚定而失效，种子已更新并新增行为钉子测试

pytest tests/test_sector_proxy.py -q          # 14 passed
pytest tests/test_backfill_f2_anchor.py -q    # 14 passed
```

离线回放（真实数据只读，`run_canonical_from_artifacts` programmatic + 现场 F4 `PolicyMapper`）：

```
储能 bearish (cb75ed27, env_7d0a98e37690) F4 hint=avoid_or_watch_risk
  → ACTION 159566.SZ 储能电池ETF易方达 bearish etf, 3 条 F2 证据 span, tier=opinion
储能 bullish (cb050d72, env_04530c84bf10) F4 hint=watch_or_no_trade
  → ACTION 159566.SZ 储能电池ETF易方达 bullish etf, 6 条 F2 证据 span, tier=opinion
  两条均携带 metadata.sector_proxy 溯源（rule=configs/sector_proxies.yaml#ENERGY_STORAGE/159566.SZ）
```

改动前该两条 intent 均被拒（`sector_target_not_tradable`），是 56→42 漏斗中唯二的 sector 损耗。

F2 命中率（`python scripts/backfill_f2_anchor.py --scope all-local --dry-run`，只读）：

```
blocks: 3051, hit blocks: 676 (22.2%)
# 基线 ~18.6%（2026-06-26，见 docs/specs/2026-06-26-f2-llm-entity-proposal-impl.md）→ +3.6pp
# 初版含裸词别名（机器人/黄金/金价）时为 24.5%，多出的 2.3pp 经审查判定
# 主要是假命中（"1 个机器人" bot 语义、"金价4500" 矿业股上下文），别名收紧后回落
```

## 审查结论与修复（多视角审查工作流，14 agents，9 条确认）

| 级别 | 发现 | 处置 |
|---|---|---|
| high | 裸词板块别名（机器人/黄金）× CJK 子串匹配 × 代理放行 = 从非投资文本捏造可执行 action（旧 sector gate 是最后防线，本次同时降精度+拆防线） | **已修**：只收 KOL 指称板块的实际用语（人形机器人/机器人板块/机器人概念、黄金板块/黄金股/现货黄金）；「金价」因矿业股上下文噪声一并移除（test_select_candidates 实证撞上） |
| medium | sector_proxy 配置加载隔离不完整：`version: v2`/`priority: high`/proxies 为 list 均会炸穿 `_rebuild()` 直至 F5 中止（复现确认） | **已修**：version/priority 容错降级 + proxies 类型守卫 + per-entry try/except；两条回归测试钉住 |
| medium | OPTICAL_MODULE 与 COMPUTE_POWER 共用 515880 → F7 按 (KOL, ticker) 键立场槽，两个板块观点坍缩为一条立场线 | **已修**：COMPUTE_POWER 改 159819 为 priority 1。残余：COMPUTE_POWER↔AI_COMPUTING 共享 159819（持久解法：F7 立场键优先读 `metadata.sector_proxy.sector_symbol`，见未解决项） |
| medium | LLM 路径 instrument_type 硬编码 "stock"，crypto/index 被错标（programmatic 路径经 `_target_type_to_instrument` 正确） | **已修**：非代理分支改用 `_target_type_to_instrument(matched_intent.target_type)` |
| medium | LLM 路径改写最大但零测试覆盖 | **已修**：新增 4 条 llm_guided 测试（mock LLMClient：代理命中/market 回显/伪 ticker/未配置板块） |
| medium | `test_sector_opinion_still_rejected` 因本次改动变为空转且 docstring 语义反转 | **已修**：改写为 `test_sector_opinion_trades_through_proxy`，钉住新行为 |
| low | LLM 路径 final_market 仍信 LLM 回显（ticker 已改用 intent 归一值），可产出 ticker=300750.SZ + market=US 的自相矛盾记录 | **已修**：market 一并取自 intent |
| low | `_TRADABLE_SYMBOL_RE` 在 entity_registry / sector_proxy 重复 | **已修**：收敛到 `entity_registry.matches_tradable_format()` 单真相（llm_entity_proposal 的正则语义不同，保留） |

修复后全量测试 3221 passed（含 6 条新回归测试），储能回放结果不变。

## 未解决项（Open Issues）

1. **ETF 码核验（2026-07-12 更新，已基本闭环）**：全部 17 instrument 已过真实 Yahoo 价格层（各 62 交易日可取价）；10/16 板块双对抗复核通过；剩 6 个（DEFENSE_MILITARY 1/2、GOLD/HSTECH/ROBOTICS/AI_COMPUTING/LIQUOR）复核 agent 因会话额度中断但已过研究核验+价格层。错码的失败模式是 F8 取价失败→action 停 pending（fail-open），而价格层已实证全部可取价，故风险已消除；剩余 6 个的第二道复核为 belt-and-suspenders，额度恢复后补齐即可。
2. **F7 立场键的代理坍缩（结构性）**：多个板块共用一只代理 ETF 时，`stance_snapshot` 的 (KOL, ticker) 键会合并独立观点。本次已把三组两两冲突降为一组（COMPUTE_POWER↔AI_COMPUTING 共享 159819）；持久解法是 F7 立场键优先读 `metadata.sector_proxy.sector_symbol`（溯源字段已就位），归 F7 排期。
3. **per-creator 代理开关未做**：当前映射全局生效。trader_ji 明确要 ETF 代理（creator YAML notes），未来若有 KOL 需关闭代理，可在 `CreatorProfile` 加开关后于 runner 处传入。
4. **板块别名精度需持续观察**：审查后已收紧为「指称板块的实际用语」策略；「人工智能」保留为观察项（4 字、金融语境特异性尚可）。新增别名的纪律：先过 curated 评审 + 与 `test_select_candidates` 等下游分类器对拍。
