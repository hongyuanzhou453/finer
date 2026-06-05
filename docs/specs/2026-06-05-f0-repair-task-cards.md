# F0 修复 · 分阶段任务卡（断点续传真相源）

> **用途**：F0 修复轮次的任务卡 + 进度真相源。配合主控 agent `.claude/agents/f0-repair-orchestrator.md` 使用。
> **如何续传**：新会话冷启动 → 读本文件「当前进度快照」定位下一张 PENDING 卡 → 主控 agent 按卡派发 → 审阅 → commit → 回来更新本文件状态。
> **关联**：完整审计见 `docs/specs/2026-06-04-f0-runtime-audit-and-repair-plan.md`。
> **创建**：2026-06-05。

---

## 0. 当前进度快照

- **分支**：`f0-runtime-repair`
- **已完成里程碑**（提交链，已验收）：

| commit | 里程碑 | 状态 |
|---|---|---|
| `8ff2b16c` | Phase 1 运行时止血（PM 接电 asset_index 368 行 + Import Console proxy + os.walk 止血）| ✅ DONE |
| `505fb9bb` | Phase 2 GATE 冻结 5 共享契约 | ✅ DONE |
| `3f3ad4bd` | Phase 2 Batch A（BK4 本地上传 / BK2 微信 / FE2 前端入口）| ✅ DONE |
| `b32e7286` | Phase 2 Batch B（BK1 飞书+NLM / BK3 B站，收口+优雅降级）| ✅ DONE |
| `b1ce1495` | 文档收口 | ✅ DONE |

- **R-01 ~ R-33 代码层全部解决**（详见 06-04 文档 §10）。全量 `pytest tests/` = 2764 passed / 1 pre-existing F8 失败（`test_get_price_routing`，与 F0 无关）。
- **6 渠道终态**：本地上传可立即 E2E；微信视频号/公众号、飞书、NotebookLM、B站 代码已收口，E2E 待用户修环境（见 §6）。
- **下一步入口**：Phase 3（E2E 联调）/ Phase 4（IDP-01）/ Phase 6（合并）——见下，按用户选择派发。

> ⚠️ 注：本仓库 live 的 TaskCreate 任务列表（#7-18）是 BK1/BK3 subagent 的内部子任务，**已全部完成但状态显示 stale**，以本文件为准。

---

## 1. 冻结契约速查（所有实现卡必须复用，禁止改）

```python
from finer.schemas.import_receipt import ImportReceipt   # .to_import_run() 投影前端 ImportRun
from finer.ingestion.f0_index_writer import F0IndexWriter # record_imported(record, receipt) 幂等写 PM
from finer.paths import f0_raw_dir, f0_intake_dir, f0_record_path, f0_receipt_path
from finer.utils.time import now_utc
```
- `ContentRecord.source_type` frozen literal：`feishu_chat`/`nlm_note`/`manual_upload`/`wechat_article`/`wechat_channels_video`/`bilibili_video`/`unclassified` 等。
- PM 已接电：`asset_index` + `AssetIndexService`；`/api/files` 走 catalog。
- **禁止改**：`schemas/`、`ingestion/f0_index_writer.py`、`utils/time.py`、`paths.py`、migrations、live DB。

---

## 2. 断点续传协议（额度中断）

中断特征：实现 agent 返回 `subagent_tokens: 0` + "session limit"，可能已部分改文件。
1. `git status --short` + `git diff --stat HEAD` 看改到哪。
2. 优先 `SendMessage(to: <agentId>)` 继续（上下文在）：消息给"恢复，补完 X/Y/Z + 验收 + 报告"。
3. background 完成有 `<task-notification>`，再审阅。
4. SendMessage 不可用才 fresh 重派，注明"已完成 X，只需补 Y"。
5. 每里程碑完成立即 commit checkpoint，更新本文件状态。

---

## 3. Phase 3 — 渠道 E2E 验证 + 环境联调（PENDING）

> 前置：用户完成 §6 环境清单的对应项。每张卡是**只读/轻验证为主**，发现真实 bug 才改对应渠道 owned 文件。可并行（不同渠道），但每渠道串行验证。

### 卡 P3-LOCAL — 本地上传 E2E（无外部依赖，可立即）
- F-stage F0 / 实现+验证 / 状态 PENDING / 依赖：无
- 目标：起 `uvicorn` + `npm run dev`，实测上传 → 确认产 ContentRecord+receipt+PM 行、Import Console/文件列表出现该文件、sourceRecordId 非空、路径穿越文件名被拦。
- allowed：`api/routes/files.py`、`files_utils.py`（仅修实测暴露的 bug）；forbidden：其它渠道、frozen。
- 验收：TestClient 或真实 HTTP 上传一次 → 贴 response + asset_index 行数 +1；`pytest tests/test_files_upload_f0.py -q`。

### 卡 P3-WECHAT-CH — 微信视频号 E2E
- F-stage F0 / 状态 PENDING / 依赖：`wx_video_download` binary 在 PATH 或 `WX_CHANNELS_DOWNLOAD_BIN`/config 配置
- 目标：实测 `/api/wechat/channels/import`，确认 external-install 查找生效、binary 缺失走 `F0_EXT_001`(retryable)、成功产 record+receipt+PM。
- allowed：`ingestion/wechat_adapter.py`、`api/routes/wechat.py`（仅 bug）；forbidden：frozen、其它渠道、前端。
- 验收：binary 存在/不存在两路径；`pytest tests/test_wechat_channels_f0.py -q`。

### 卡 P3-WECHAT-MP — 微信公众号 E2E
- F-stage F0 / 状态 PENDING / 依赖：exporter service 已启动（端口 3001，单一真相源 `configs/wechat.yaml`）
- 目标：实测 `/api/wechat/login`(扫码) + `/api/wechat/sync/{account_id}`，确认产 markdown raw + ContentRecord + receipt + PM；exporter 离线走 `WX_EXT_001` 不崩。
- allowed：`ingestion/wechat_exporter_client.py`、`wechat_adapter.py`、`api/routes/wechat.py`（仅 bug）；forbidden：frozen、其它渠道。
- 验收：exporter 在/不在两路径；`pytest tests/test_wechat_api_routes.py tests/test_wechat_f0_contract.py -q`。

### 卡 P3-FEISHU — 飞书 E2E
- F-stage F0 / 状态 PENDING / 依赖：`lark-cli auth login`（user token 已过期，必须先登录）
- 目标：实测 `/api/integrations/feishu/fetch` 或 `/api/sources/refresh`，确认飞书 F0 产 ContentRecord+receipt+PM、Vision/Summary/NLM 已解耦（不在 F0 路径内联跑）、token 失败走 `FEISHU_AUTH_001`+fix_hint 且 stderr 不外泄。
- allowed：`ingestion/feishu_poller.py`、`feishu_f0_importer.py`、`orchestrator.py`、`api/routes/sources.py`、`integrations.py`（仅 bug）；forbidden：frozen、其它渠道、`bilibili*`/`wechat*`。
- 验收：token 有效/过期两路径；`pytest tests/test_feishu_f0_contract.py tests/test_bk1_feishu_nlm_f0.py -q`。

### 卡 P3-NLM — NotebookLM E2E
- F-stage F0 / 状态 PENDING / 依赖：nlm CLI 已登录（`nlm login`）
- 目标：实测 `/api/integrations/nlm/fetch`，确认产 `nlm_note` ContentRecord+receipt+dedupe+PM、`resolve_nlm_cli` 解析到真实 `~/.local/bin/nlm`、重复 fetch 走 skipped。
- allowed：`ingestion/nlm_sync.py`、`api/routes/integrations.py`（仅 bug，注意 integrations.py 飞书+NLM 同文件，与 P3-FEISHU 串行或拆 ownership）；forbidden：frozen、其它渠道。
- 验收：`pytest tests/test_bk1_feishu_nlm_f0.py -q`。

### 卡 P3-BILI — B站 E2E
- F-stage F0 / 状态 PENDING / 依赖：装 .NET 8 runtime（BBDown 需要；+ DashScope key 仅转录）
- 目标：实测 `/api/bilibili/import/{bvid}`，确认产 raw artifact set + ContentRecord + receipt + PM、不依赖 transcript、BBDown 缺.NET 走 `F0_EXT_001`+fix_hint；transcribe 是 F1-adjacent 不阻塞 F0。
- allowed：`ingestion/bilibili_adapter.py`、`bbdown_client.py`、`api/routes/bilibili.py`、`bbdown.py`（仅 bug）；forbidden：frozen、`parsing/mimo_asr_client.py`、其它渠道。
- 验收：.NET 在/不在两路径；`pytest tests/test_bilibili.py tests/test_bilibili_f0_contract.py tests/test_bbdown_cli_adapter.py -q`。

---

## 4. Phase 4 — PM 增量写入深化 + IDP-01（PENDING）

### 卡 P4-IDP01 — artifacts 表确定性去重键
- F-stage F0 / 状态 PENDING / 依赖：无（独立）/ ⚠️ 触碰 PM 写入路径
- 背景：`F0IndexWriter` 当前**不写 artifacts/storage_objects**（backfill 用随机 `art_<uuid>` 非幂等，重复 backfill 会累积 `is_canonical=0` 历史行 371→742）。
- 目标：给 artifact 写入设计**确定性去重键**（如 `sha256(content_id+role+raw_sha256)`），使 `F0IndexWriter.record_imported` 能幂等注册 artifacts；可选清理 backfill 已产生的重复历史行（清理=批量删除，**红线，需用户确认**）。
- allowed：`ingestion/f0_index_writer.py`、`scripts/project_memory_backfill.py`、相关测试；forbidden：migrations 表结构变更（除非用户确认）。
- 验收：重复调用 record_imported / backfill → artifacts 行数稳定；`pytest tests/test_f0_index_writer.py tests/test_project_memory_backfill.py -q`。
- 🔴 红线：清理历史行属批量删除，需用户确认。

### 卡 P4-COVERAGE — 各渠道 record_imported 接线覆盖确认
- F-stage F0 / 状态 PENDING / 依赖：Phase 3 之后
- 目标：只读核查 6 渠道导入成功路径**是否都真的调了** `F0IndexWriter().record_imported`（BK2/BK3/BK4/BK1 报告称已接，需端到端确认每条 happy path 都落 PM 行，无遗漏/无静默 best-effort 吞错）。补缺失接线。
- allowed：对应渠道 route/adapter（按渠道单 agent）；forbidden：frozen。
- 验收：每渠道导入一次 → asset_index 行数 +1；汇总成一张"渠道→PM 写入确认表"。

---

## 5. Phase 5 — F1 接手解耦能力（PENDING，F1 scope）

### 卡 P5-F1HANDOFF — Vision/Summary/ASR 落到 F1
- F-stage **F1**（非 F0）/ 状态 PENDING / 依赖：F1 owner
- 背景：F0 收口已把 Vision/Summary（飞书）、ASR（B站）从 F0 路径解耦，留了 seam：`orchestrator.F1_HANDOFF_SEAM`、`sync_chat` 返回的 `f1_handoff_seam`、B站 transcribe 标 F1-adjacent。能力模块仍在（`vision_utils.py`/`summary_generator.py`/`mimo_asr_client.py`）。
- 目标：F1 owner 在 F1 阶段消费 `data/raw/...` raw + ContentRecord 跑 Vision/OCR/Summary/ASR，产 F1 canonical 输出（`ContentEnvelope`/`ContentBlock`）。**不得在 F0 路径重新挂回这些调用。**
- allowed：`parsing/`（F1 owning area）；forbidden：F0 ingestion 路径回挂、frozen。
- 验收：F1 standardization 测试；F0 路径仍不内联跑这些阶段（grep orchestrator 无 Vision/Summary import）。
- 注：本卡属 F1 修复轮次，列此仅为交接连续性。

---

## 6. Phase 6 — 收尾（PENDING，多为红线，需用户确认）

### 卡 P6-MERGE — 分支合并
- 状态 PENDING / 🔴 红线
- 目标：`f0-runtime-repair` → main（5 个 commit）。合并前确认全量验收、解决与 main 的潜在冲突。
- 必须用户确认（merge/push 是红线）。

### 卡 P6-WXVENDOR — wx_channels_download external-install 收尾
- 状态 PENDING / 🔴 红线（删目录）
- 背景：BK2 已把 binary 路径改 external-install（`shutil.which`→env→config→vendored 回退）。`scripts/wx_channels_download/`（含 GPLv3 fork + Commons Clause + MITM root CA + RSA 私钥）仍是 untracked 发布风险（见 `2026-05-wx-channels-dependency-policy.md`）。
- 目标：补外部安装文档（clone+build+配置 `WX_CHANNELS_DOWNLOAD_BIN`/config）；用户确认后删除 vendored 目录；更新 CLAUDE.md 启动命令引用。
- 必须用户确认（删目录是红线）。

### 卡 P6-L0MIGRATE — data/L0_ingest 迁移
- 状态 PENDING / 🔴 红线（数据迁移）
- 背景：`data/L0_ingest`(650MB) 是 legacy F0 输出，已从 `/api/files` fallback scan 移除（不再被扫）。
- 目标：把其中仍有价值的内容迁移/backfill 到 `F0_intake` + PM，或归档清理。
- 必须用户确认（数据迁移 + 可能批量删除是红线）。

---

## 7. 验证债 / 待确认残留（下一轮先 Line V 核实）

派 Phase 3 前，建议先一个只读 agent 核实这几项是否真闭合（06-04 报告声明已解决，但值得端到端确认）：
- **R-33**：`WeChatSyncResult.l0_triggered` legacy 命名（前端 contract）是否已改为 `f0_*`；前端是否消费该字段。
- **wechat_adapter.py** 未物理拆分（1667 行，公众号 1-1246 / 视频号 1248-end）——是否需要拆（可选，非阻塞）。
- **search_videos()** B站 stub——已标注 placeholder，是否要接真实 API。
- **classifier.py** 硬编码 `/opt/homebrew/bin/gemini`（R 报告 P3 项）——是否迁到项目 LLM 注册表。
- 各渠道 `_register_f0_index` best-effort 吞错是否会掩盖 PM 写失败（P4-COVERAGE 一并查）。

---

## 8. 环境清单（用户侧执行，agent 不碰 .env/系统/外部服务）

| 项 | 动作 | 解锁渠道 E2E |
|---|---|---|
| 飞书 token 过期 | `lark-cli auth login`（系统终端） | P3-FEISHU |
| 缺 .NET 8 | 安装 .NET 8 runtime | P3-BILI |
| 缺 DashScope key | `.env` 加 `DASHSCOPE_API_KEY`（🔴 红线，用户改） | P3-BILI 转录 |
| 微信 exporter 未托管 | 启动 exporter service（端口对齐 3001） | P3-WECHAT-MP |
| nlm 未登录 | `nlm login` | P3-NLM |
| wx 视频号 binary | 配置 `WX_CHANNELS_DOWNLOAD_BIN` 或放 PATH | P3-WECHAT-CH |

---

## 9. 派发顺序建议（主控 agent 参考）

1. **先 Line V 核实** §7 验证债（1 个只读 agent，不改文件）。
2. **Phase 3 可立即的**：P3-LOCAL（无依赖）先验。其余 P3 卡随用户完成对应环境项后逐个派（可 2-3 个并行，注意 integrations.py 飞书/NLM 串行）。
3. **Phase 4**：P4-IDP01（独立，触 PM 写入，红线先问）+ P4-COVERAGE（Phase 3 后）。
4. **Phase 6**：全是红线，逐项问用户后做。
5. **Phase 5**：F1 轮次，单独起。

每完成一卡/一批 → commit checkpoint → 回来把本文件对应卡状态改 ✅ DONE + 记 commit。
