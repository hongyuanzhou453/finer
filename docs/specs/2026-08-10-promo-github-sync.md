# 宣传站 + GitHub README 同步定位转向（2026-08-10）

## 概述

把 2026-08-02 拍板的定位转向（「不告诉你谁更准，让你查得清谁说过什么」）与消费面三页
（/discover /ticker /audit）同步到两个对外展示面：宣传站 `src/finer_site`（finer.t800.click）
与双语 landing README。这是定位提案 §6 预留的「UI 轮次逐条收敛」轮：审计出宣传站 19 处、
README 36 处旧口径文案（含 7 处硬违规），全部收敛；新增「记录与共识」章节，
使用真实语料截图与带出处的数字。**本轮只改文案与静态资产，未动任何产品代码；
未 push、未部署（等确认）。**

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `README.md` / `README.en.md` | 修改 | 标题改记录身份；hero 换已批准定位句 + 三支柱；「为什么是 Finer」改三问题式 + 持续性检验否定结果公开段；新增「记录与共识」章节（三截图 + 数字条 + 五个只读 API）；F8 改「回测与结算记录」；F6 逐条强制门表述改三向审计硬门；roadmap 回填第一轮 DPO 真实数字；阶段表 F1.5 → wired；F5 关键文件 → `action_composer.py`；免责声明补无持续性句；中英严格镜像 |
| `src/finer_site/src/app/page.tsx` | 修改 | hero 三行新定位；新 `#records` 章节（三视图 + 28,565/4,919/128,905 数字条 + 诚实的统计块）；#proof 改「收益曲线是历史记录，不是承诺」；能力卡 F8/来源清单改写；human-loop 硬门表述；DPO 状态 4 处回填 |
| `src/finer_site/src/app/layout.tsx` | 修改 | TITLE=「谁说过什么，后来发生了什么」；description/og/keywords 同步 |
| `src/finer_site/src/components/landing/site-chrome.tsx` | 修改 | 导航加「记录与共识」；#proof label 改「结算记录」；footer blurb 换定位句 |
| `src/finer_site/src/components/landing/pipeline-strip.tsx` | 修改 | F8 desc「回测评分」→「回测结算」 |
| `src/finer_site/src/components/demo/demo-workbench.tsx` | 修改 | hero 指标改已结算样本（演示）；roster 红字评分改 n=样本数；胜率并排 n；图例「跟单模拟（演示）」 |
| `src/finer_site/src/demo/data.ts` | 修改 | F8 走查文案删「回算 KOL 评分」 |
| `src/finer_site/src/app/training/page.tsx` | 修改 | 4 处「待实跑」状态更新为第一轮完成（/case 数字，小样本限定） |
| `src/finer_site/src/app/sitemap.ts` | 修改 | 加 /case；lastModified=2026-08-10 |
| `src/finer_site/public/landing/record-{discover,ticker,audit}.png` | 新增 | 真实产品截图（1440×900 @2x，2026-08-10，主仓 main 运行实拍） |
| `docs/assets/record-{discover,ticker,audit}.png` | 新增 | 同上，README 用 |

## 架构影响

无产品代码、schema、API 契约变更。只读 API 端点在 README 中首次对外列出
（`/api/creator/records`、`/api/creator/{id}/record`、`/api/ticker/{symbol}/consensus`、
`/api/audit/actions`、`/api/audit/actions/{id}/trace`），与 `api/server.py` 注册一致。

## 关键决策

1. **对外口径以定位提案 §4 原文为准**，两处展示面均原文引用；营销文案自身也
   受产品红线约束（不引用任何具体胜率数字——各版记分卡文档均声明绝对值不可对外直读）。
2. **数字冲突取最新权威**：action 总量用 4,919 / span 128,905（2026-08-06），
   不用 4,577/124,988（08-02）；持续性检验样本用 2,983（其检验口径）。
3. **诚实叙事作为卖点**：否定结果、陈旧度分布（中位 2025-12-19 / 70% 三个月无更新 /
   69% 单一信源）、AZN.L 拒绝聚合，全部正面呈现，不藏脚注。
4. **截图用真实语料实拍**，与 demo 的「演示数据」标注严格区分；截图注明日期
   （as_of_days 每天在变）。
5. **repo URL 维持 `kelipovanatalja453-bot/finer`**：与 `hongyuanzhou453/finer`
   为同一仓库（GitHub 改名重定向），保持现状一致即可。
6. **demo 工作台只做标签级收敛**（评分退位、样本量上位），不重排布局；
   `/kol-check`（feat/kol-check-demo 分支 + 独立 Worker 部署）的口径收敛留待后续轮。

## 验证结果

- `cd src/finer_site && npm run build` → ✓ 9 静态页全部生成（含 TS 检查通过）
- 禁词扫描（更准/最佳信源/Top 券商/回测评分/KOL 评分/验证跟随）→ 仅存于否定句式
- 数字核对：28,565 / 4,919 / 128,905 / 2,983 / 87.1 / 2025-12-19 双语与站点一致；
  旧数字（4,577/124,988/待实跑）0 残留
- playwright 全页截图目检：hero / #records / #proof / roadmap 渲染正常，
  record-*.png 全部 200
- README 中英 `##` 章节数一致，锚点与 GitHub auto-anchor 规则核对通过

## 未解决项

- **部署与 push 均未执行**（用户红线，等确认）：站点需
  `npx wrangler pages deploy out --project-name finer-site`（见 `src/finer_site/DEPLOY.md`）；
  部署后确认 `/kol-check`（独立 Worker 路由）仍可达。
- `/kol-check` 快照页旧口径文案在 `feat/kol-check-demo` 分支，本轮未动。
- 宣传站旧 mock 截图（demo-hero.png 等）仍为转向前工作台形态，已用文字标注；
  如需彻底一致可在后续轮重摄。
- worktree 的 `src/finer_site` 缺 `package.json`（根 .gitignore 的 `*.json` 规则所致），
  构建时从主仓拷贝；该 gitignore 规则值得单独修。
