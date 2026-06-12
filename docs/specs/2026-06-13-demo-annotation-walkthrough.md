# /demo 标注全流程交互视图

> 日期: 2026-06-13
> F-stage: 无（纯前端宣传站 finer_site，零后端、零 F0-F8 业务代码）
> 关联: docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md（RLHF×RLVR 概念源）、2026-06-11-finer-site-training-page.md（training 叙事页）

## 1. 概述（Overview）

在 `finer.t800.click/demo` 新增「标注全流程」交互视图，与现有「研究·回测」工作台通过顶部 segmented 切换并列，把 training 页"讲"的三类人工标注 + RLHF×RLVR 协同变成访客可亲手操作的 demo（Gold 标注 / DPO 偏好对 accept-edit-reject / F6 字段修正），右栏挂确定性 RLVR verifier 实时打分。全演示数据、虚构 persona、不落库。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer_site/src/components/demo/demo-shell.tsx` | 新增 | 视图外壳，持 `view` state，条件渲染两个 workbench |
| `src/finer_site/src/components/demo/demo-header.tsx` | 新增 | 共享顶栏 + segmented 视图切换（`DemoView` 类型源） |
| `src/finer_site/src/components/demo/annotation-workbench.tsx` | 新增 | 标注全流程主组件（三任务工作台 + 右栏 verifier + 数据流脉络） |
| `src/finer_site/src/components/demo/reward-meter.tsx` | 新增 | RLVR verifier 打分可视化（结构门 + grounding/calibration/abstention 条形 + total + margin） |
| `src/finer_site/src/demo/annotation-data.ts` | 新增 | fixture（Gold 2 / 偏好对 3 / F6 2）+ 确定性 `scoreExtraction` / `committalRate` |
| `src/finer_site/src/demo/types.ts` | 修改 | 追加 `ExtractionDraft`/`RewardBreakdown`/`GoldTask`/`PreferencePair`/`F6Case`/`AnnotationTaskId` |
| `src/finer_site/src/components/demo/demo-workbench.tsx` | 修改 | 抽离内联 header→`<DemoHeader>`；导出 `Stars`/`HighlightedSource`/`DIRECTION_META`；签名加 `view`/`onViewChange` props。三栏 body 逻辑零改动 |
| `src/finer_site/src/app/demo/page.tsx` | 修改 | 渲染 `<DemoShell/>`；metadata.description 补标注全流程 |

## 3. 架构影响（Architecture Impact）

- **零后端、零 schema 改动**：纯静态导出站（`output: "export"`），不碰 `src/finer/**`、F0-F8、Pydantic schema、API。
- **概念对齐而非代码耦合**：demo `RewardBreakdown` 字段（total/structure/grounding/calibration/abstention）刻意对齐任务卡 `rewards.py` 接口，但是独立的 demo 实现，不 import 后端。
- **路由不变**：仍 7 条静态路由，`/demo` 单页内 client-side 视图切换。
- **复用**：`demo-workbench.tsx` 的 `Stars`/`HighlightedSource`/`DIRECTION_META` 改为导出供标注视图复用；标注素材复用现有虚构 persona（trader_ji/value_laozhang/trend_hunter_k/hk_veteran），天然无真人。

## 4. 关键决策（Key Decisions）

1. **承载=视图切换（非独立路由/非重建）**：用户确认。回测工作台仅抽 header、逻辑零改，不动已上线体验；一处入口呈现 AI抽取→人工标注→RLVR/DPO 闭环。
2. **确定性 demo scorer**：`scoreExtraction` 是透明规则函数（structure 硬门→fail 即 total=0；grounding 0.5 / calibration 0.4 / abstention 0.1 加权），让 verifier 分数随 edit 实时变化，呼应"可验证奖励：确定性·免费·可复现"，而非假装有模型。
3. **Gold 任务 verifier 不介入**：任务一右栏显式说明「人工验证集(RLHF)是评测真相，RLVR verifier 只对训练候选(任务二/三)打分」——用 UI 表达两类信号的分工，强化 RLHF×RLVR 概念。
4. **诚实基调延续**：全程「演示数据」徽章、`reviewer_id=you_demo`、JSON 标注「未落库」、gold 零泄漏提示；reference_gold 作"提交后揭示的参考"而非预先标准答案。

## 5. 验证结果（Verification）

```
npm run lint   # 通过（无输出）
npm run build  # 通过，7 路由全静态，/demo 静态导出
```

preview（dev server 端口 4311）走查：
- 视图切换：`/demo` 默认研究·回测 → 切「标注全流程」正常。
- 任务一 Gold：右栏正确显示「验证集·verifier 不介入」说明卡。
- 任务二偏好对：verifier 实时打分 **chosen 0.94**（grounding 1.00 / calibration 1.00）vs **rejected 0.45**（grounding 0.60 / calibration 0.28，编造价位被罚），**margin 0.49「偏好信号充分」**，committal rate 100%——与确定性规则手算一致。
- edit 模式：chosen 侧渲染 DraftEditor（direction/ticker/action/conviction 控件）。
- console 无 error；mobile(375) 三栏正确堆叠为单列。

> 注：`npm run build` 与 turbopack dev server 共用 `.next` 会写坏 dev 缓存（工具链限制，非代码问题）；验证时先 `rm -rf .next` 再重启 dev（`out/` 不受影响）。

## 6. 未解决项（Open Issues）

- **未部署**：demo + training 改动均未上线 `finer.t800.click`。wrangler 无登录态、所连 Cloudflare MCP 无 Pages 部署能力 → 部署最后一步需用户终端 `wrangler login` 或后台拖拽 `out/`。
- **未提交 git**：本次 demo 改动 + 上轮 training `page.tsx` 改动均未 commit；push 到 PR #3 需用户确认（红线）。
- **mobile 左栏较长**：窄屏下左栏（三任务卡+累积+数据流）在工作台之上，需滚动较多才到中栏——与现有回测 demo 同模式，未单独优化。
