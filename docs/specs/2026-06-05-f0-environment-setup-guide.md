# F0 环境配置指南（解锁 Phase 3 渠道 E2E）

> **用途**：把任务卡 `2026-06-05-f0-repair-task-cards.md` §8 的环境清单变成可执行步骤。每项含：当前状态 → 命令 → 验证 → 解锁哪张 P3 卡。
> **前提**：F0 代码已收口（merge 到 main），各渠道依赖缺失会优雅降级（不崩）。本指南是为了让 5 个 🔴/🟡 渠道**真正端到端跑通**。
> **安全**：密钥只进 `.env`（已 gitignore），不进代码/commit/日志。
> **创建**：2026-06-05。

---

## 0. 当前环境快照（已实测）

| 工具/服务 | 状态 | 还需 |
|---|---|---|
| `lark-cli` | ✅ 已装 `/opt/homebrew/bin/lark-cli` | 🔁 user token 过期，需重登 |
| `nlm` | ✅ 已装 `~/.local/bin/nlm` | 🔁 确认登录态 |
| `BBDown` | ✅ 已装 `~/.dotnet/tools/BBDown` | ❌ 缺 .NET 8 运行时（本机仅 .NET 10） |
| `wx_video_download` | ✅ vendored binary 存在 | 🟡 可直接用（或配 env 更干净） |
| `.NET` | ⚠️ 仅 `Microsoft.NETCore.App 10` | ❌ 需补装 **.NET 8** |
| DashScope key | ❌ `.env` 无 `DASHSCOPE_API_KEY` | ❌ 需补（仅 B站转录用） |
| exporter service | ❌ 未运行（localhost:3001） | ❌ 需 clone + 启动 |

**优先级建议**：先做①②（一条命令，立即解锁 2 渠道）→ 再③（wx 现成可用）→ 然后按需 ④⑤⑥。

---

## ① 飞书 token 重登 — 解锁 `P3-FEISHU`（最易，1 条命令）

```bash
# 系统终端执行（不要粘进 Claude 会话）
lark-cli auth login
```
- 浏览器/扫码完成 user 身份授权（读群消息 scope 需 user 身份）。

**验证**：
```bash
lark-cli auth status        # tokenStatus 应为 valid，且 expiresAt 在未来
```
✅ 通过后可派 P3-FEISHU 实测 `/api/integrations/feishu/fetch`。

---

## ② NotebookLM 登录 — 解锁 `P3-NLM`（最易）

```bash
nlm login                   # 若已登录可跳过；按提示完成 Google 授权
# 切换账号：nlm login switch <profile>
```

**验证**：
```bash
nlm source list 2>&1 | head    # 能列出 source（非鉴权错误）即可
```
✅ 通过后可派 P3-NLM 实测 `/api/integrations/nlm/fetch`。

---

## ③ 微信视频号 binary — 解锁 `P3-WECHAT-CH`（现成可用）

vendored binary 已存在，F0 的查找顺序是 `shutil.which` → env `WX_CHANNELS_DOWNLOAD_BIN` → config → vendored 回退，所以**现在就能用**。要更干净/可移植：

```bash
# 方式 A：显式指定（推荐，避免依赖 vendored 目录）
export WX_CHANNELS_DOWNLOAD_BIN="$PWD/scripts/wx_channels_download/wx_video_download"
# 方式 B：放进 PATH
# 方式 C：在 configs/wechat.yaml 配 channels_downloader_bin: <path>
```
> ⚠️ vendored 目录含 GPLv3 + MITM 私钥，是发布风险（P6-WXVENDOR）。**自用没问题**；若要分发，按上游 [ltaoo/wx_channels_download](https://github.com/ltaoo/wx_channels_download) 自行 clone+build 后用方式 A 指向，再删 vendored 目录（需你确认）。

**验证**：
```bash
ls -l "${WX_CHANNELS_DOWNLOAD_BIN:-scripts/wx_channels_download/wx_video_download}"   # 存在且可执行
```
✅ 通过后可派 P3-WECHAT-CH 实测 `/api/wechat/channels/import`。视频号 profile 抓取还需本地 :2022 服务（见该 binary 文档）。

---

## ④ 安装 .NET 8 — 解锁 `P3-BILI` 下载链路

BBDown 需要 **.NET 8 运行时**（本机只有 10，major 版本不兼容，光设 `DOTNET_ROOT` 救不了）。

```bash
# macOS — 二选一
brew install dotnet@8
# 或官方安装包：https://dotnet.microsoft.com/download/dotnet/8.0  （选 Runtime，arm64）
```

**验证**：
```bash
dotnet --list-runtimes | grep 'Microsoft.NETCore.App 8'    # 出现 8.x 即可
BBDown --help | head -3                                     # 不再报 "You must install or update .NET"
```
✅ 通过后可派 P3-BILI 实测 `/api/bilibili/import/{bvid}`（raw 下载，不需 DashScope）。

> 注：B站 **F0 导入（raw 下载）只需 .NET 8**；转录是 F1-adjacent，才需要下面的 DashScope key。

---

## ⑤ DashScope key — B站转录（F1-adjacent，非 F0 必需）🔴 改 .env

```bash
# 你自己编辑 .env（红线，agent 不碰），追加一行：
# DASHSCOPE_API_KEY=sk-xxxxxxxx
# key 从阿里云 DashScope 控制台获取：https://dashscope.console.aliyun.com/
```

**验证**：
```bash
grep -q '^DASHSCOPE_API_KEY=' .env && echo "✅ 已配置（值不显示）" || echo "❌ 未配置"
```
✅ 通过后 `/api/bilibili/transcribe/{bvid}`（F1-adjacent）可用。**不影响 B站 F0 导入**。

---

## ⑥ 启动 exporter 服务 — 解锁 `P3-WECHAT-MP`（最费事）

公众号链路依赖外部 Nuxt.js 服务 `wechat-article-exporter`，需跑在 **localhost:3001**（与 `configs/wechat.yaml` 的 `exporter_url` 对齐）。

```bash
# 在 Finer 仓库之外另找目录
git clone https://github.com/kelipovanatalja453-bot/wechat-article-exporter
cd wechat-article-exporter
npm install
# 启动到 3001（Nuxt 默认 3000，需指定端口对齐 Finer 配置）
PORT=3001 npm run dev      # 或 build 后 PORT=3001 node .output/server/index.mjs
```
首次需在该应用里扫码登录微信公众号后台。

**验证**（Finer 后端起着时）：
```bash
curl -s localhost:8000/api/wechat/exporter/health    # available 应为 true
```
✅ 通过后可派 P3-WECHAT-MP 实测 `/api/wechat/login` + `/api/wechat/sync/{account_id}`。

> 若不想跑端口 3001，改 `configs/wechat.yaml` 的 `exporter_url` 对齐你的实际端口（单一真相源，BK2 已统一）。

---

## 验证全链（环境就绪后）

每搞定一项环境，对应渠道就能派 Phase 3 的 P3 卡做 E2E。最省事的验证路径：

```bash
# 1. 起后端
uvicorn finer.api.server:app --reload --port 8000
# 2. 起前端（另开终端）
cd src/finer_dashboard && npm run dev
# 3. 浏览器开 Import Console，逐个渠道点导入，看是否产 ContentRecord + 出现在文件列表 + asset_index +1
```

| 环境项 | 解锁渠道 | E2E 卡 |
|---|---|---|
| ① lark-cli 登录 | 飞书 | P3-FEISHU |
| ② nlm 登录 | NotebookLM | P3-NLM |
| ③ wx binary（现成） | 微信视频号 | P3-WECHAT-CH |
| ④ .NET 8 | B站 | P3-BILI |
| ⑤ DashScope（可选） | B站转录(F1-adjacent) | — |
| ⑥ exporter 服务 | 微信公众号 | P3-WECHAT-MP |

> 本地上传（P3-LOCAL）无需任何环境，现在就能验。
