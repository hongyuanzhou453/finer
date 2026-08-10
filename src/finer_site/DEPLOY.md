# Finer OS 宣传站 — 部署指南（Cloudflare Worker）

> finer.t800.click 由**静态资源 Worker `finer-site`** 服务（assets-only，无服务端脚本）。
>
> ⚠️ 本文档旧版描述的 Cloudflare Pages 路线（`wrangler pages deploy out --project-name finer-site`）
> 已于 2026-08-10 实测无效：账户内不存在任何 Pages 项目。按那条路线部署只会
> 新建一个与线上域名无关的 Pages 项目，线上站点不会更新。不要再用。

---

## 标准更新流程（实测有效）

```bash
# 构建 + 部署（wrangler 读取同目录 wrangler.jsonc）
cd src/finer_site
npm run build && npx wrangler@latest deploy
```

首次使用需 `npx wrangler login`（浏览器授权一次，凭证只在本机 `~/.wrangler`，不经过 AI）。

部署完成后抽查线上路由全部 200：`/`、`/demo`、`/training`、`/kol-check`。

---

## 部署配置：wrangler.jsonc

`src/finer_site/wrangler.jsonc`（已 tracked；根 `.gitignore` 的 `*.json` 规则
**不匹配** `.jsonc`）：

- `"name": "finer-site"` —— 必须对应线上已存在、绑定 finer.t800.click 的
  Worker；错名字会部署出一个与线上无关的新 Worker。
- `"assets": { "directory": "./out" }` —— 指向 `next build` 的静态导出产物；
  assets-only，无服务端脚本。
- 域名绑定（finer.t800.click → Worker）配置在 Cloudflare 后台该 Worker 的
  **Custom Domains**，不在 wrangler.jsonc 里；`wrangler deploy` 只更新静态资源，
  不影响域名绑定。

---

## 陷阱一（已根治）：/kol-check 源码曾只在 feat/kol-check-demo 分支

2026-08-10 前 `/kol-check` 源码只在 `feat/kol-check-demo` 分支上，从 main
直接构建部署会让线上 `/kol-check` 404（新产物整体覆盖线上资源）。当时的
补救是部署前 `git checkout feat/kol-check-demo -- src/finer_site/src/{app,components,demo}/kol-check`。

该分支已于 2026-08-10 合入 main（merge commit ab5f32dc，无冲突），从 main
构建即含 `/kol-check`，checkout 步骤作废。仅当从早于该合并的旧提交构建部署时
才会复现——部署前确认 `out/kol-check/` 存在即可兜底。

---

## 陷阱二：package.json 不在 git 里

根 `.gitignore` 的 `*.json` 把 `src/finer_site/package.json`、`package-lock.json`
也忽略了——fresh clone / 新 worktree 里**没有这两个文件**，无法 `npm install`。
需从既有主仓工作区复制（连同 `node_modules` 一起 `cp -R` 实体复制，
Turbopack 拒绝 symlink）。

---

## 排查

- **构建产物缺页面**：部署前确认 `out/` 里存在 `kol-check/` 目录；缺了说明构建自
  早于 2026-08-10 合并（ab5f32dc）的旧提交。
- **线上没更新**：确认部署输出的 Worker 名是 `finer-site`（错名字会部署到别的 Worker）。
- **og 预览图不显示**：社媒抓取有缓存，用对应平台的 debug 工具刷新即可
  （图在 `/og/finer-social-preview.png`）。

---

## 安全

- 不要把 Cloudflare API Token / 全局 API Key / Zone ID 贴进任何对话或截图。
- wrangler 的登录态保存在你本机 `~/.wrangler`，AI 不接触。
