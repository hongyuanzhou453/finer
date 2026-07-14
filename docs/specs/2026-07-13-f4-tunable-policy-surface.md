# F4 分层调参可调面（roadmap ⑧）（2026-07-13）

## 概述（Overview）

执行 `docs/specs/2026-07-13-next-optimization-directions.md` 方向⑧：把 F4 止损/止盈/最长持有等阈值从 `global_base.py` 硬编码升级为 `configs/skills/f3f4-policy.yaml` 外置可调面，并可**按 KOL 声明的 `entry_style` 分层覆盖**。纯确定性、零 LLM、零数据依赖。**默认值镜像旧硬编码、`by_style` 空 → 行为零变化**（全套件 3207 passed 佐证），机制就绪后填一条 style tuning 即生效。这是 P2#8「止损/止盈按 KOL 风格分层」的地基。

## 变更清单（Changes）

| 文件 | 变更 | 说明 |
|------|------|------|
| `src/finer/policy/policy_config.py` | 新增 | `PolicyTuning`/`ExitRuleHints` + `load_policy_tuning()`：读 f3f4-policy.yaml，默认==旧硬编码，非法/缺省/坏 YAML 落回 base，缓存+`reset_cache()` |
| `src/finer/policy/global_base.py` | 修改 | `GlobalBasePolicy` 加 `tuning` 字段；`compute_risk_constraints` 的 exit 字面量(-0.10/0.20/30)与 0.3/0.4 阈值改读 `self.tuning`（值不变，保持 Layer0 风格无关，只用 `base_exit`） |
| `src/finer/policy/policy_mapper.py` | 修改 | 加 `_apply_style_exit_overlay`：仅当 `tuning.by_style` 非空且 intent 为持仓型才解析 `creator_id→entry_style`（KOL registry 懒调用/可注入）覆盖 exit hints，记入 `policy_layers_applied`+`layer_traces`(StyleExitOverlay) |
| `configs/skills/f3f4-policy.yaml` | 修改 | 加 `f4_policy.exit_rules`(base 镜像旧值 + `by_style: {}` 空 + 注释示例)；`risk_flags`/`exit_rules` 标「已 wire」 |
| `tests/test_policy_config.py` | 新增 | 7 测：默认==硬编码/shipped 回归/base 覆盖/risk_flags/by_style 部分覆盖回落/非法值降级/坏 YAML 降级 |
| `tests/test_policy_style_overlay.py` | 新增 | 6 测：空 by_style 不解析(registry 零调用)/匹配 style 生效/未 tune style 回落/非持仓 intent 跳过/resolver 异常回落/空 creator 回落 |

## 架构影响（Architecture Impact）

- **Layer 边界守住**：`GlobalBasePolicy` 是 F4 Layer 0、明确风格无关（docstring line 13），仍只消费 `tuning.base_exit`。按 KOL/风格的覆盖作为独立 overlay 在 `PolicyMapper` 层应用（StyleArchetype-lite），不污染 Layer 0。
- **F4 输出契约不变**：`PolicyRiskConstraints` 的 exit-hint 字段与符号约束(stop_loss<0/take_profit>0/max_holding>0)不变；overlay 用 `model_copy(update=)`，值由 loader 校验保证合法。overlay 生效时新增 `policy_layers_applied=['GlobalBase','StyleExitOverlay']` + 一条 layer_trace + 一条 risk_note，可审计。
- **跨模块调用合规**：`kol_registry` 是公共模块（任何 F-stage 可查询），overlay 经 `get_registry().declared_style(creator_id).entry_style` 解析，best-effort（异常/不可用 → base），且**仅在 by_style 非空时才调用**——shipped 默认空 → registry 永不被调、热路径零开销。
- **迁移纪律**：遵守 `configs/skills/README.md`「迁一个验证一个、默认值不变、补 config==旧值回归测试」。本轮迁 exit_rules + risk_flags（同在 compute_risk_constraints，一处内聚）；`position_sizing_bands`/`f3_intent`/`f5_action` 仍为 scaffold，留后续迁移。

## 关键决策（Key Decisions）

1. **GlobalBase 只吃 base，style overlay 上移到 mapper**。而非给 Layer 0 加 style 参数——保住「Layer 0 风格无关」的设计契约，符合 docstring「per-horizon tuning belongs to higher policy layers」。
2. **默认 `by_style: {}` 空 + 值镜像旧硬编码 → 零行为变化**。机制就绪、可测，但不动 shipped 行为（3207 passed 无回归）；填一条 style tuning 才改变该 style 输出。这是安全「地基」的核心。
3. **overlay 仅当 by_style 非空才解析 style**。空时短路，registry 永不被调，避免热路径/测试对 registry 可用性的依赖，也让现有 test_policy_mapper 零影响。
4. **`entry_style` 作为分层 key**（left_side/right_side/mixed/unknown，低基数 Literal），而非自由文本 style_label——契合 exit-rule 风格差异（右侧追突破 vs 左侧抄底）且稳定。
5. **坏 config 降级不崩**：非法值(符号错)/缺字段/坏 YAML → 落回 base + warning，F4 永不因配置错误而 crash。

## 验证结果（Verification）

命令与输出（`.venv/bin/python`，2026-07-13）：

```
# F4 定向 + 回归
$ pytest tests/test_policy_config.py tests/test_policy_style_overlay.py \
         tests/test_policy_mapper.py tests/test_policy_schema.py \
         tests/test_execution_timing_policy.py -q
157 passed

# 用到 PolicyMapper 的下游
$ pytest tests/test_canonical_runner_mapping.py tests/test_canonical_action_builder.py \
         tests/test_action_composer.py -q
59 passed

# 全套件（零回归）
$ pytest tests/ -q
3207 passed, 22 skipped in 70s

# 端到端冒烟（真实 KOL registry）
[default shipped]        trader_ji → stop=-0.10 tp=0.20 hold=30  layers=['GlobalBase']         # 行为不变
[real registry override] trader_ji → tp=0.30 hold=20            layers=['GlobalBase','StyleExitOverlay']
                         note: "Exit rules tuned for declared style 'right_side'"              # 真实 registry 解析 trader_ji→right_side 生效
[unknown creator]        nobody   → tp=0.20                     layers=['GlobalBase']          # 回落 base
```

- **回归**：默认 shipped 配置下 exit hints == 旧硬编码值，全套件零回归 → 行为零变化。
- **分层生效**：真实 KOL registry 把 trader_ji 解析成 right_side 并应用 by_style override，端到端打通「按 KOL/风格分层」。
- **健壮性**：非法值/坏 YAML/resolver 异常/空 creator 均安全回落 base。

## 未解决项（Open Issues）

- **shipped `by_style` 为空**：机制就绪但未启用任何真实 style tuning——这是刻意的（地基先行、零行为变化）。真正给右侧/左侧配差异化止损止盈，是下一步产品决策（需要回测数据支撑参数选择，依赖③/④出活水）。
- **其余 scaffold 阈值未迁**：`f3_intent`(conviction/confidence)、`f5_action`、`f4_policy.position_sizing_bands` 仍硬编码，按「迁一个验证一个」后续逐个迁。
- **calibration 评估未接**：yaml `evaluation` 段（用 F6 RLHF 做 conviction calibration）属 M3，依赖 F6 反馈数据（当前为空，见 P2#8）。
- 变更在 `feat/pipeline-autodrive` 分支，未提交。
