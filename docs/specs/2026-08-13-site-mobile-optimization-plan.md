# 宣传站移动端优化方案（小红书导流准备度）

> 产出方式：14-agent 并行审计 + 对抗验证（8 条高危逐条证伪，2 条被推翻）。
> 原始编排 run: `wf_d7cc4974-399`。

---

# Finer 宣传站移动端优化方案（小红书导流准备度排序）

## 结论先行

**导流前必须清的只有 4 项，都是 S/M 量级，1 个工作日内可完成。** 站点最大的风险不是"页面太长"或"手机上没导航"——这两条我复核后判定不成立（hero 第 0.6 屏就有 `看记录与共识` 锚点，第 3.9 屏有指向 `/records` 的红色主 CTA，页脚 8 条链接在移动端全部可见，结尾 CTA 是"启动在线演示"不是招聘）。**真正卡住导流的是两类伤：**

1. **数字自伤（P0-1/P0-2）**——一个把"测量纪律"当卖点的产品，其 `/demo` 上印着 `72.0% · n=2`（算术上不可能），`/kol-check` 上把 `28%` 当 hero 大数裸渲染（8/29 的 95% 区间是 15%–46%）。小红书用户里只要有一个人按计算器，整站可信度归零。这是唯一会造成**不可逆声誉损失**的一类。
2. **移动端把关键叙事藏进横滑容器（P0-4）**——标题写"一条内容，走完 F0 → F8"，375px 下只看得见 F0/F1/F2 三个，且无任何横滑提示（`.finer-scrollbar` 只设了 `width: 5px`，未设 `height`，移动端 overlay 滚动条不滑就完全不可见）。这是首屏之后的第 2 屏，用户决定去留的位置。

**图片、字号、SEO 那些全部是 P1**——它们让体验更好，但不会让人怀疑你在编数字。

---

## 优先级总表

| 级别 | 项 | 卡在哪 | 量 | 风险 |
|---|---|---|---|---|
| **P0-1** | `/demo` 比率与样本量自相矛盾 | 可信度自伤，CTA 落点 | S | 无 |
| **P0-2** | `/kol-check` 裸点估计 28%，无 sufficiency 无区间 | 公开违反落地页自己的承诺 | M | 无 |
| **P0-3** | `/kol-check` 「晨星/战绩/体检」评级框架 | 标题层面对撞定位红线 | S | 改 `<title>`，见决策项 |
| **P0-4** | pipeline strip 移动端 9 阶段只露 3 个 | 第 2 屏叙事断裂 | S | 无 |
| P1-1 | 首屏 hero 545KB + 6 张 2880px PNG | 4G 首屏体感 | M | 需加 devDependency |
| P1-2 | 76 处 10–11px 中文 | 可读性下限 | S | 未复核 |
| P1-3 | 页脚触摸目标 20px | 误触 | S | 未复核 |
| P1-4 | `/kol-check` 无 signal_class 口径徽标 | 跨口径横比（红线 §2） | S | 无 |
| P1-5 | `/records` 首屏被 z/t 统计量挡住 | 第一张卡只露 131px | S | 未复核 |
| P1-6 | canonical 全指首页 / og height / favicon 是 114KB JPEG | 索引与冷启动 | S | 无 |
| P1-7 | `/records` manifest 请求排在 hydration 之后 | 弱网白屏 | S | 未复核 |
| P2-1 | `kol-radar.ts` 四处排序键（含一个"可执行推荐榜"） | 未上线的红线代码债 | M | 无 |
| P2-2 | "平均每笔跟单"措辞 | 把记录写成可执行策略 | S | 无 |
| P2-3 | RLHFFeedback 卡片 `w-44` 截断 62% | 第 12 屏，影响小 | S | 未复核 |
| P2-4 | CJK 衬线字体族 Android 取不到 | 视觉身份设备依赖 | M | 见"没有好解法" |

标注"未复核"= 来自审计实测，我本轮未独立复现像素测量，代码位置我已确认存在。

---

## P0 — 导流前必做

### P0-1 `/demo` 工作台在 n=2/n=3 上渲染比率

**已确认代码**（`src/components/demo/demo-workbench.tsx:484-489`）：

```tsx
{ k: "胜率（历史记录）", v: `${(m.win_rate * 100).toFixed(1)}% · n=${m.signal_count}` },
```

`src/demo/data.ts` 五个 KOL 的 metrics 实测为 `(0.667/3)`、`(0.72/2)`、`(0.51/2)`、`(0.6/2)`、`(0.58/2)`。n=2 只能产出 0%/50%/100%，后四条算术上不可能。同一行还在 n=2 上渲染夏普 1.05、年化、最大回撤。

修正一点审计原文：静态产物 `out/demo.html` 首屏只含默认 KOL 的 `66.7% · n=3`（自洽），不可能的数字要点一次 KOL 名录才出现。但**默认态本身就在 n=3 上渲染比率+夏普+年化**，同样违背落地页 `page.tsx:62` 的"样本不足只报计数"。

**改法**（`demo-workbench.tsx:482` 前）：

```tsx
const thin = m.signal_count < 10;
const cells = thin
  ? [
      { k: "已结算样本", v: `${m.signal_count} 笔` },
      { k: "其中正收益", v: `${m.wins} 笔` },
      { k: "样本充分性", v: "不足 · 只报计数" },
    ]
  : [ /* 现有六格 */ ];
```

同步改 `src/demo/data.ts`：删掉 `win_rate` 字段，改存 `wins` 整数（`signal_count: 2` 配 `wins: 1`），从源头杜绝比率与 n 对不上。术语统一为 `/records` 已用的"结算命中率（历史）"。

顺带：`demo-header.tsx:36` 的"演示数据 · Sample data only"徽章 className 是 `hidden ... lg:inline`，手机上完全不显示——把 `hidden`/`lg:inline` 去掉，改为始终可见。这一条审计报告漏了，但对小红书流量（几乎全移动端）恰恰是最关键的那块缓解。

**验证**：
```bash
cd src/finer_site && npm run build
grep -oE '[0-9]+\.[0-9]% · n=[0-9]+' out/demo.html   # 应为空
```
再手工点一遍五个 KOL，确认无任何比率/夏普/年化。

### P0-2 `/kol-check` 结算命中率 28% 无 sufficiency

**已确认代码**：`KolCheckReport.tsx:122-124`（verdict banner）、`:137-141`（MetricTile "结算命中率"）、`kol-l2.ts:27-31`（narrative），三处独立渲染 `Math.round(hitRate*100)%`，全页无 `display_policy` 分支、无 count_only 门、无 Wilson 区间。实测 8/29 → 27.6%，95% Wilson 区间 14.7%–45.7%（宽 31 个百分点，跨过 50% 两侧的全部解释空间）。

**同页自相矛盾**：`:243` 页脚自称"所有比率均并排样本量，样本偏少时明确标注"，页头 `:91-95` 已承认"KOL 层级样本不足、未检验"，中间却渲染裸点估计。落地页 `page.tsx:62` 更是把"命中率并排 95% 区间；样本不足只报计数"当作对外承诺——`/kol-check` 是这条承诺的公开反例。

**改法**：不要在前端硬编阈值，复用 `/records` 已有契约。

1. `src/demo/kol-check/data.json` 的 `radar` 上补一个与 `src/demo/records/types.ts:31-48` 的 `Sufficiency` **完全同构**的对象。注意审计给的 JSON 缺三个必填字段，照抄会 tsc 报错，完整字段是：`settled_n / total_n / successes / point_estimate / wilson_low / wilson_high / ci_width / confidence / coverage_ratio / coverage_penalised / tier / display_policy / predictive_claim / notes`。取值：`settled_n:29, total_n:37, successes:8, point_estimate:0.2759, wilson_low:0.147, wilson_high:0.457, ci_width:0.310, tier:"provisional", display_policy:"show_with_warning", predictive_claim:null, notes:["KOL 口径未做跨期持续性检验，该比率不可外推"]`。
2. `KolCheckReport.tsx:136-142` 换成与 `RecordCardWall` 的 `CardRatioBlock` 同一套分支：`show`/`show_with_warning` 输出「28%　95% 区间 15%–46%　已结算 29 笔」+ 金色告警注；`count_only` 只输出「已结算 29 / 总数 37（样本不足，只报计数）」。
3. `kol-l2.ts:27-31` narrative 同步带上区间。
4. **区间不要贴死字面量**——写一个 Wilson 工具函数从 `settled.length` / `wins` 实时算，快照一换才不会静默失真。

**验证**：`npm run build` 后 `grep -c '95% 区间' out/kol-check.html` ≥ 2；把 data.json 的 `display_policy` 临时改成 `count_only` 重新构建，确认页面零比率。

### P0-3 `/kol-check` 的"晨星 / 战绩 / 体检"评级框架

**已确认**：`src/app/kol-check/page.tsx:6` title = `"KOL 晨星 · 真实战绩体检"`（经 layout 模板拼成 `… · Finer OS`），`KolCheckReport.tsx:101` 眉标"KOL 晨星 · 体检报告"、`:122` "体检结论："、`:227` "真实战绩时间线"、`:4` 文件注释"晨星式体检报告"。晨星在中文投资语境的第一联想是基金星级评级——"谁更值得买"，正是定位红线要拆掉的东西。页面在 `sitemap.ts` 以 priority 0.8 收录、robots 全站 allow，公开可索引。

严重度我判 **medium-high 而非 high**：正文其实已经合规（不排名、02 章节明写"按已结算笔数的稳定输出序，不是排名"、三处独立的"不构成对未来的预测"）。出问题的是**外壳**——`<title>` 是被索引强度最高的单一字符串，而它跟自己页头的"样本不足、未检验"正面打架。

**改法**（四处替换）：

| 位置 | 现在 | 改成 |
|---|---|---|
| `page.tsx:6` | KOL 晨星 · 真实战绩体检 | 单个 KOL 的公开记录核查 |
| `KolCheckReport.tsx:101` | KOL 晨星 · 体检报告 | 单信源记录 · KOL 口径 |
| `:122` | 体检结论： | 记录摘要： |
| `:227` | 真实战绩时间线 | 观点记录时间线（en 保留 `EVIDENCE · AUDIT TRAIL`） |
| `:4` 注释 | 晨星式体检报告 | 单信源公开记录核查页 |

`:122` 那段横幅**只换措辞前缀，保留现有派生表达式**（`settled.length` / `wins` / `hl.hitRate` / `earn.avgReturn`、`TRADING_STYLE.observed.left_side_count`），不要把数字写死。description 已在 1906d136 收敛过（现文是"公开记录做可审计核查"），只需按新 title 微调。

CSS 变量 `--morningstar-red` 是设计 token（晨星是本站刻意的设计血统），保留，不改。

**验证**：`grep -rn "晨星\|战绩\|体检" src/app/kol-check/ src/components/kol-check/` 只应剩 CSS 变量名。

### P0-4 pipeline strip 移动端只露 3/9 阶段

**已确认**：`pipeline-strip.tsx:31-32` = `overflow-x-auto finer-scrollbar` + `<ol className="flex min-w-[820px]">`，STAGES 共 9 项（F0–F8）。375px 下 clientWidth 327 / scrollWidth 843，61% 在屏外。`globals.css:109-111` 的 `.finer-scrollbar::-webkit-scrollbar` 只设 `width: 5px`（纵向），**移动端 overlay 滚动条不滑完全不可见**（桌面 WebKit 会回落 UA 默认 height，仍绘制，所以这条只在移动端成立——而这正是本项的作用域）。全站 grep 确认无 mask、无 snap、无横滑文案提示、无 `@media` 覆盖。

**改法：移动端不要横滑，改 3×3 网格。**

```tsx
// pipeline-strip.tsx:32
<ol className="grid grid-cols-3 gap-px md:flex md:min-w-[820px] md:items-stretch">
// li:
<li className="flex md:flex-1 md:items-stretch">
// :56 的 ChevronRight 分隔符（网格里箭头方向是错的）：
{i < STAGES.length - 1 && (
  <div className="hidden items-center px-0.5 text-foreground/25 md:flex">
)}
```

375px 下每格约 105px，够放 `F0` / `规则` / `Intake` / `多源接入` 四行，9 个全部可见，桌面端行为完全不变。

同一处理 roadmap 轴：`page.tsx:760-761` 的 `overflow-x-auto` + `flex min-w-[640px]`（实测 325/688，53% 隐藏）。

**若坚持保横滑**（不推荐，交互成本 > 0），最低限度补三样：容器右缘 `[mask-image:linear-gradient(to_right,#000_85%,transparent)]` 渐隐、`snap-x snap-mandatory` + 子项 `snap-start`、标题下加一行「← 横滑看完 9 个阶段」。另外顺手给 `globals.css:109` 补 `height: 5px`，让横向滚动条在桌面也有一致外观。

**验证**：`npm run dev` 后 375px 视口下数 9 个 `<li>` 是否全部 `fullyVisible`；桌面 1280px 下确认仍是一条横排带箭头。

---

## P1 — 上线后首周

### P1-1 图片
`demo-hero.png` 实测 545,823 B / 2880×1800，`page.tsx:237` 标 `priority`，构建产物里 9 张图它是唯一没有 `loading="lazy"` 的，还带 `<link rel="preload" as="image">`。`public/landing/` 共 3.6MB。

**修正审计的一个数**："图片占传输量 99%"是缓存命中下的假象，实测冷加载约 533KB 图 / 759KB 总量 ≈ **70%**，JS 是 197KB gzip / 10 个 chunk。所以别按"图片是唯一瓶颈"排优先级。

**另一个修正**：移动端该图起点 y≈645、只露顶部，**移动端 LCP 是 h1 文字不是图片**。它的危害是挤占带宽延迟其余资源，不是直接拉长 LCP。因此这条降为 medium。

改法：加 sharp 构建脚本产出 `-m.webp`（650×406，约 40–60KB），`<picture>` 按 `media="(max-width:640px)"` 切换，桌面保留原图；移动端去掉 hero 的 `priority`。`next.config.ts` 的 `images.unoptimized:true` 是 `output:"export"` 强制的，`product-frame.tsx:50` 的 `sizes` 属性形同虚设——必须自己出变体，见"没有好解法"。

### P1-2 / P1-3 / P1-5 / P1-7 快改
- **字号**：`text-[10px]` → `text-[11px] sm:text-[10px]`；说明类 `text-[11px]` → `text-[12px] sm:text-[11px]`。地板：正文 ≥14px、说明 ≥12px、徽标 ≥11px。
- **触摸目标**：`site-chrome.tsx` 页脚 8 条链接加 `py-2 -my-2`（命中区 20→36px，视觉行距不变）；header CTA `py-2` → `py-3`。
- **`/records` banner**：`RecordsExplorer.tsx:119-135` 调换层级——白话句（"未观测到该指标的跨期持续性…不构成对未来的预测"）提为 banner 正文，`6 个切分点 / |z|=0.32 / |t|=1.20` 收进默认折叠的 `<details>`。红线要求的是"必带 sufficiency、必声明不预测"，不是要求把统计量放在散户第一屏。改的是呈现层级，`usePersistenceStatement` 的数据不动。
- **manifest 预加载**：`RecordsExplorer.tsx:53` 的 `useEffect` fetch 排在整个 JS 下载+hydration 之后。更彻底的做法是构建期内联——manifest brotli 后仅 5.9KB，由服务端组件 `fs.readFileSync` 注入为 `initialManifest` prop，首屏零请求，"正在加载冻结快照…"这个状态可以整个删掉；`creator-N.json` 的懒加载保持不变。

### P1-4 `/kol-check` 口径徽标
`src/demo/records/types.ts:10` 的 `SignalClass` 联合类型**只有两个值**，站点侧根本没有 `kol_statement`——说明该页从未接入口径隔离契约。补：types 扩为三值、`primitives.tsx:16` 的 `SIGNAL_CLASS_LABEL` 补 `kol_statement: "KOL 表述"`、hero 元信息行加一枚"口径：KOL 表述（kol_statement）"徽标、页头持续性横幅末尾追加"本页数字属 KOL 表述口径，与 /records 的两种口径基准率不同，不可跨口径比较"。两页共用 header/footer 且同在 sitemap，读者必然会横比。

### P1-6 SEO 三件套（各 5 分钟）
- `layout.tsx:30` 的 `alternates: { canonical: SITE_URL }` 定义在 root layout，6 个页面全部指向首页，与 sitemap 自相矛盾。删掉全局 `alternates`，各页自己声明相对 canonical（`metadataBase` 已设）。验证：`for h in index records demo training kol-check case; do grep -o '<link rel="canonical"[^>]*>' out/$h.html; done` 应输出 6 个不同 URL。
- `layout.tsx:42` `height: 670` → `640`（实测文件是 1280×640）。
- `src/app/icon.png` 实测是 **JPEG**（`file` 输出 `JPEG image data … 1024x1024`）却叫 `.png` 且按 `image/png` 下发，114,440 B，每页冷访问都拉一次。重采样到 192×192 真 PNG（约 10KB），iOS 主屏图标另出 `apple-icon.png` 180×180。

---

## P2 — 后续

**P2-1 `kol-radar.ts` 排行榜代码债（趁没上线先改）。** 我复核时发现比审计报告更严重的一处：除了 `:280-281`（按 `credibility` 降序）和 `:506`（按 `cumReturn` 降序），还有 **`:345` `calls.sort((a,b) => b.score - a.score)`**——按 `credibility × confidence × freshness` 排的"当前可执行推荐榜"，这是最直接的"谁更准 + 该买什么"排行榜本体。目前 `data.json` 只有 1 个 KOL，`KolCheckReport.tsx:60/64` 只取 `[0]`，三个 board 全是休眠代码，线上看不到。但 `:453` 的注释已把"live 路径同一函数零改动复用"写成契约——一接多 KOL 就是三个违规榜单同时上线。

改法：默认序统一改为已结算样本量（`b.settledCount - a.settledCount || a.name.localeCompare(b.name)`），`credibility` / `cumReturn` / `score` 保留为列不作排序键；`credibility` 改名 `shrunkHitRate`、`deriveCredibilityBoard` 改名 `deriveSourceRecordBoard`、`topCall` 改名 `latestActionable`（"top"在多 KOL 场景会被复用成"最佳推荐"）；函数上方注释写明「默认序 = 已结算样本量（CLAUDE.md 定位前提 §3）」。

**P2-2 措辞**：`KolCheckReport.tsx:144` "平均每笔跟单" → "每笔结算均值（历史）"，`:200` 表头 → "均值结算收益（历史）"，`ViewpointTimeline.tsx:178` 去掉"跟单"。"跟单"是动作动词，读者会理解成"跟着这个人做能拿到什么"——正是要拆掉的暗示。`/records` 侧同一个量已经中性命名为"均值收益（历史）"。

**P2-3** RLHF 卡片 `flex flex-col gap-0.5 sm:flex-row`、`dt` 改 `w-auto sm:w-44`、`dd` 改 `break-words sm:truncate`。位于第 12 屏，优先级低。

---

## 需要你拍板的（我不自行决定）

1. **`/kol-check` 改 `<title>`**（P0-3）。该 URL 已公开上线并被索引，标题变更会影响既有搜索结果。我倾向改——现标题跟定位红线冲突，越晚改沉没成本越大——但这是产品决策。
2. **主 CTA 指向。** 现在 5 处按钮指向 `/demo`（明确标注"不连接真实后端"的演示数据），而站里有 4,919 条真实 action。是否把最显眼的常驻位置换成 `/records` 或 `/kol-check`？这是"展示能力"vs"展示证据"的取舍，不是技术问题。
3. **是否新建小红书专用落地页。** 现落地页 14,204px 是给工程师/投资人看的完整叙事，做一个短页（hero + 一个可查的真实数字 + 一个 CTA）成本约 0.5 天。但会多一个需要同步维护的页面，且分散 SEO 权重。我的判断：**先不做**——把 P0 清干净，直接把小红书导流指向 `/kol-check`（单页、有真人真事、能查证据链），比新建落地页 ROI 高。
4. **邮箱订阅 / 二维码留存。** 全站零留存机制，唯一联系方式是个人 Gmail，内容又是冻结快照（无回访理由）。收邮箱涉及个人数据收集与存储方案，属于需要你先定的合规决策，我不会直接实现。二维码回流成本更低、无合规负担，可以先做这个。
5. **加 `sharp` 为 devDependency + 图片构建脚本**（P1-1）。项目现在无 sharp（`package.json` 已确认），`scripts/` 下只有 `freeze_kol_check_snapshot.py` 和 `screenshot-demo.cjs`。这是新增项目依赖，按纪律先问你。
6. **部署。** 所有改动完成后的 Worker 部署属于公开发布，我不会自行执行。

---

## 静态导出下没有好解法的问题（诚实说明）

1. **`next/image` 的响应式能力彻底失效。** `output: "export"` 强制 `images.unoptimized: true`，不生成 srcset，`product-frame.tsx:50` 的 `sizes` 属性是死的。**只能手工产出变体**——加构建脚本 + `<picture>`，多一层需要维护的资产管线。没有"改个配置就好"的路。
2. **截图在手机上的可读性无解，压缩解决不了。** 2880×1800 渲染到 325px 是 1/8.9 缩放，截图内的表格与数字在手机上物理不可读——换成 650px 窄版只是省流量，字还是看不清。**唯一真解是把关键三张截图换成 HTML 复刻的数字块**（NVDA 205/284/350、AZN.L 拒绝聚合、瑞银 46.2% + 95% 区间）：手机可读、可点、体积近乎为零，还顺带解决"截图不可点"。但这是重做而非优化，属于新工作量，不在本轮 P0/P1 里。
3. **邮箱收集必须靠站外能力**（Cloudflare Worker POST 端点或第三方表单），站点本身没有后端。
4. **`cache-control: public, max-age=0, must-revalidate` 是 Worker 层的响应头**，不是 Next 能改的，需要动部署配置——我本轮没有读 Worker 配置，这条标注为未核实。
5. **CJK 字体跨端一致无廉价解。** `globals.css:14` 的 `--font-display-serif` 里 Songti SC / STSong 只在 macOS·iOS 预装，Android/Windows 全部落到 generic `serif`（在多数 Android 上映射的还不是衬线），`--font-ui-sans` 里的 Inter 也从未被加载。全量思源宋体 5–15MB，引进来会直接毁掉移动端。要么承认现状（把 fallback 写显式、在设计说明里注明"衬线标题为 macOS·iOS 增强"），要么做标题字形子集化（约 288 个不重复汉字，需挂进构建以防文案改动后缺字）。**我建议选前者**——这是设备差异不是 bug，为它引入构建复杂度不划算。
6. **`/records` 的 `creator-N.json` 必然是运行时请求。** manifest 可以构建期内联（5.9KB），但 455KB 的 creator 数据只能按需拉——这是对的设计，不要"优化"掉。

---

## 执行顺序建议

```
Day 1 上午：P0-1 + P0-4（纯前端，无依赖，可并行）
Day 1 下午：P0-2 + P0-3（同一文件 KolCheckReport.tsx，串行改，避免冲突）
          → npm run build + 375px 手工过一遍全站
          → 交你确认后再部署
Week 1：  P1-6（5 分钟三件套）→ P1-4 → P1-2/P1-3 → P1-5 → P1-1（等依赖决策）
Later：   P2-1 必须在接入多 KOL 数据之前完成，否则三个违规榜单直接上线
```

关键文件绝对路径：
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/components/demo/demo-workbench.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/demo/data.ts`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/components/kol-check/KolCheckReport.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/demo/kol-check/data.json`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/demo/kol-check/kol-radar.ts`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/app/kol-check/page.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/components/landing/pipeline-strip.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/app/page.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/app/layout.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/app/globals.css`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/components/records/RecordsExplorer.tsx`
- `/Users/zhouhongyuan/Desktop/finer/src/finer_site/src/demo/records/types.ts`

按 CLAUDE.md §12，本轮改动完成后需产出 `docs/specs/2026-08-13-site-mobile-readiness.md`。