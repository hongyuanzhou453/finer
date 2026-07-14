# /radar live 面：全时段窗口 + 事件循环解阻塞（roadmap ⑦-3a/3b）（2026-07-14）

## 概述（Overview）

让 live `/radar` 面在浏览器里真正显示现有真实数据。两处修复：**⑦-3a** 给收益榜加"全时段"窗口选项（live 面默认用它，历史结算不再被 7/30d 滚动窗口过滤掉）；**⑦-3b** 把 API 热路径里"同步阻塞调用直接跑在 async handler"的反模式改为 `run_in_threadpool` 卸载（消除事件循环饿死）。结果：`/radar` 端到端渲染真实数据（LIVE · 42 条观点 · 2 KOL · 收益榜全时段 sandbox +6.92%/trader韭 −122.24%），全套件 3216 passed 0 回归。过程中审计发现这是**系统性问题**：全 API 有 46 个阻塞 handler，本次只修热路径 4 个，其余立 follow-up。

## 变更清单（Changes）

| 文件 | 变更 | 方向 | 说明 |
|------|------|------|------|
| `lib/fixtures/kol-radar.ts` | 修改 | ⑦-3a | `deriveEarningsBoard` 加 `EarningsWindow = 7\|30\|"all"`，`"all"` 跳过时间窗口（只要已结算就纳入） |
| `components/kol-radar/EarningsRace.tsx` | 修改 | ⑦-3a | 加"全时段"tab + `defaultWindow` prop（默认 7，保留 /demo） |
| `components/kol-radar/KOLRadar.tsx` | 修改 | ⑦-3a | 透传 `earningsWindow` prop |
| `app/radar/page.tsx` | 修改 | ⑦-3a | live 面传 `earningsWindow="all"` |
| `components/layout/sidebar.tsx` | 修改 | ⑦ nav | 首页操作台 Analysis 区加"观点雷达 Radar · LIVE"链接 |
| `components/layout/header.tsx` | 修改 | ⑦ nav | AppShell 页导航加"雷达" |
| `api/routes/stats.py` | 修改 | ⑦-3b | `get_stats` 的 3× `build_workflow_assets` → `asyncio.gather(run_in_threadpool(...))` |
| `api/routes/files.py` | 修改 | ⑦-3b | `get_files` 降级 fallback 的 `build_workflow_assets` → `run_in_threadpool` |
| `api/routes/system.py` | 修改 | ⑦-3b | `warmup_cache` 的 manifest 扫描 + `build_workflow_assets` → `run_in_threadpool` |
| `api/routes/opinions.py` | 修改 | ⑦-3b | `get_changes` 重体（快照构建+落盘+diff）抽 `_compute_changes` helper → `run_in_threadpool` |

## 架构影响（Architecture Impact）

- **⑦-3a（前端窗口）**：收益榜口径不变（按 settle time 分桶、等权 Σ returnPct），只是"全时段"跳过时间边界。`/demo`（fixture 为 7d 窗设计）默认仍 7d，行为不变；`/radar`（live，历史 settle）默认"全时段"。
- **⑦-3b（后端并发）**：根因是 `async def` handler 直接调**同步阻塞函数**——`build_workflow_assets` 内部 `generate_semantic_title → LLMClient.chat()` 是同步 httpx POST（本地 LLM 不可达 → 60s 超时/次，×3 passes），把单线程 uvicorn 事件循环冻死，`/radar` 的快请求全部饿死。改为线程池卸载后，阻塞发生在 worker 线程，事件循环保持响应。**纯并发行为修复，端点返回值/契约不变**（TestClient 走 async handler，354 相关测试全过）。
- 不改 F0-F8 数据契约、schema、pipeline。

## 关键决策（Key Decisions）

1. **只修热路径 4 个，不一次扫全 46 个**。用户目标是"/radar 显示真实数据"——热路径是首页(`/api/stats`+`/api/files`) + `/radar`(`/api/opinions/*`)。修完即达成（已浏览器验证）。其余 42 个阻塞 handler（多为 action/POST：转写/导入/回测/抽取）是系统性问题，需逐端点小心卸载 + 测试，立 follow-up task，不在本次盲扫。
2. **`get_changes` 抽 helper 再卸载**，而非把 `run_in_threadpool` 塞进 handler 每一步——一次卸载整个同步体，干净。
3. **`get_stats` 三路并发**（`asyncio.gather` + 3× threadpool），而非串行——冷缓存下更快。
4. **`generate_semantic_title` 的同步 LLM 调用留在原处**（只卸载到线程池）——GET 端点里发 LLM 生成标题本身是可疑设计（应缓存/后台化），但那是更大的重构，本次只解阻塞不改设计。

## 验证结果（Verification）

```
# 并发解阻塞证明（3b 核心）：冷缓存 heavy /api/stats 与快 /api/opinions/timeline 并发
cache invalidated (cold)
while stats STILL RUNNING (120s, LLM-timeout churning in threadpool):
    timeline = OK 0.03s (42 opinions)     ← 事件循环未被阻塞
VERDICT: PASS

# 浏览器端到端（3a + 3b）：直接加载 /radar
LIVE · 真实数据源 /api/opinions · 42 条观点 · 2 个 KOL
观点雷达 · sentiment 分歧 · 看多10/看空11/中性3 · 观点流向潮汐 chart
收益榜【全时段】active: 01 sandbox +6.92% (n=3) / 02 trader韭 −122.24% (n=29)
  （近一周/近一月下为空——历史 settle 被窗口过滤；全时段显示真实结算 P&L）

# 回归
pytest -k 'opinion or stats or files or system or kol or contract' → 354 passed
pytest tests/ → 3216 passed, 22 skipped, 0 回归
tsc --noEmit（前端）→ 0 error
```

## 未解决项（Open Issues）

- **系统性阻塞（42 个未修 handler）**：审计（`docs` 无落盘，见 workflow 结果）发现全 API **46 个** async handler 有同步阻塞调用，本次修 4 个热路径。**剩余 critical**：`kol.py` list_kols_enriched(O(N×N) 重扫)、`enrichment.py` extract/rebuild(每文件 LLM)、`bilibili.py` transcribe(下载+ffmpeg+ASR)、`integrations.py` feishu/nlm(subprocess 循环)、`wechat.py` import(subprocess)、`backtest.py` run/compare(pandas 逐日循环)。**high/medium** 多为读端点的 O(N) 文件扫描（现役数据小、暂快，随量增会退化）。已 spawn follow-up task 做系统性 sweep（逐端点 `run_in_threadpool` + 测试）。
- **`build_workflow_assets` 在 GET 里发 LLM 生成语义标题**：应缓存/后台化，属设计改进（本次只解阻塞）。
- **trader韭 −122.24%**：真实计算结果（29 条已结算，23 failed/9 verified，等权 Σ 方向调整收益）——数据真实，非 bug；口径是否合理（等权累计对做空/多标的的呈现）可另议。
- 变更未提交（前端 ⑦ + 后端 3b 在 `feat/pipeline-autodrive` 分支）。
