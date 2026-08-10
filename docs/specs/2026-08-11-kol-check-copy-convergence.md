# /kol-check 旧口径文案收敛（2026-08-11）

## 概述

完成定位转向（docs/specs/2026-08-02-positioning-pivot-proposal.md §6）遗留的最后一块
对外文案收敛：/kol-check 快照页移除「评分即推荐」与「按收益排序的榜」语义，
补齐 KOL 层级持续性声明。页面本体（匿名真实快照、言行不一核查、逐条证据链）
与新定位一致，保留结构只收敛口径。

## 变更清单

| 文件 | 变更 |
|---|---|
| `src/finer_site/src/app/kol-check/page.tsx` | metadata description 去「信誉分」，改为可审计核查表述 |
| `src/finer_site/src/components/kol-check/KolCheckReport.tsx` | hero「信誉分 N/99」→「已结算 N 笔 · 命中 X 笔（%）」；建议语义两分支合并为记录语义单句；页头加持续性边界横幅；「标的兑现榜」→「标的结算记录」；footer 信誉分公式句删除 |
| `src/finer_site/src/demo/kol-check/kol-snapshot.ts` | 标的表排序主键改**已结算笔数降序**（均值收益仅作同笔数 tie-breaker） |
| `src/finer_site/src/demo/kol-check/kol-l2.ts` | 「最佳兑现」→「单笔最高兑现」（禁词扫尾） |
| `src/finer_site/src/demo/kol-check/kol-radar.ts` | 注释口径同步；credibility 字段数据兼容保留、不再作评价口径渲染 |

## 关键决策

1. 信誉分**整体移除**而非改名——CRD-1 判定「分数隐含可据此选人」，改名救不了语义。
2. 持续性声明措辞严格守 spec §1.1 边界：券商层级=检验为否定；KOL 层级=样本不足、
   **未检验**——否定结论不越界引用到 KOL。
3. 「完全跟单回测/跟单收益」作为回测记账口径的机械术语保留；「言行不一」板块原样保留
   （CRD-4 旗舰，正是新定位形态）。
4. 记录语义句不因收益正负切换话术（原版负收益时劝退、正收益时鼓励，都是建议语义）。

## 验证结果

- 实现 + 独立复核双 agent：复核零违规通过（含排序代码级核验：settledCount 降序实测
  [5,4,3,3,2,2,2,1…]；边界越界检查无发现）
- `npx tsc --noEmit` 0 错；`npm run build` 11 路由全过；playwright 冒烟 13 断言过
- 禁词 grep（信誉分/兑现榜/建议/更准/最佳/Top）仅剩否定句式与 CSS 属性字面撞词
- 终检截图目检：页头声明/新 hero/结算记录表/言行不一全部正常

## 未解决项

- 发布（push + Worker deploy）待用户确认。
- data.json 中 KOL 原话引用内含「不是投资建议」为语料原文，按规则不动。
