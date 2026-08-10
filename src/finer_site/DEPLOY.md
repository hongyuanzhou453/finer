# Finer OS 宣传站 — 部署指南（Cloudflare Worker）

> finer.t800.click 由**静态资源 Worker `finer-site`** 服务（assets-only，无服务端脚本）。
>
> ⚠️ 本文档旧版描述的 Cloudflare Pages 路线（`wrangler pages deploy out --project-name finer-site`）
> 已于 2026-08-10 实测无效：账户内不存在任何 Pages 项目。按那条路线部署只会
> 新建一个与线上域名无关的 Pages 项目，线上站点不会更新。不要再用。

---

## 标准更新流程（实测有效）

```bash
# ① 仓库根目录：取回 /kol-check 页面源码（只在 feat/kol-check-demo 分支，见下方陷阱一）
git checkout feat/kol-check-demo -- \
  src/finer_site/src/app/kol-check \
  src/finer_site/src/components/kol-check \
  src/finer_site/src/demo/kol-check

# ② 构建 + 部署（wrangler 读取同目录 wrangler.jsonc）
cd src/finer_site
npm run build && npx wrangler@latest deploy
```

首次使用需 `npx wrangler login`（浏览器授权一次，凭证只在本机 `~/.wrangler`，不经过 AI）。

部署完成后抽查线上路由全部 200：`/`、`/demo`、`/training`、`/kol-check`。

---

## 部署配置：wrangler.jsonc

`src/finer_site/wrangler.jsonc`。`name` 必须是 `finer-site`——对应线上已存在、
绑定了 finer.t800.click 的 Worker；`assets.directory` 指向 `next build` 的静态导出产物：

```jsonc
{
  // finer.t800.click 实际由静态资源 Worker（finer-site）服务，非 Pages 项目
  "name": "finer-site",
  "compatibility_date": "2026-08-01",
  "assets": {
    "directory": "./out"
  }
}
```

- 根 `.gitignore` 的 `*.json` 规则**不匹配** `.jsonc`，该文件可正常入 git。
  目前 tracked 版本在 `feat/kol-check-demo` 分支上（随该分支合入 main 收编）；
  若工作区里找不到，按上面内容原样重建即可。
- 域名绑定（finer.t800.click → Worker）配置在 Cloudflare 后台该 Worker 的
  **Custom Domains**，不在 wrangler.jsonc 里；`wrangler deploy` 只更新静态资源，
  不影响域名绑定。

---

## 陷阱一：/kol-check 源码只在 feat/kol-check-demo 分支

- main 上**没有** `/kol-check` 页面源码。从 main 直接 `npm run build` 再部署，
  新产物会整体覆盖线上资源 → **线上 /kol-check 变 404**。
- 所以从 main 部署前必须先执行标准流程第 ① 步的 `git checkout feat/kol-check-demo -- …`。
- 该 checkout 会把文件同时写入工作区和暂存区。部署后如需还原：

```bash
git reset -- src/finer_site/src/app/kol-check src/finer_site/src/components/kol-check src/finer_site/src/demo/kol-check
rm -rf src/finer_site/src/app/kol-check src/finer_site/src/components/kol-check src/finer_site/src/demo/kol-check
```

- **根治方案 = 把 feat/kol-check-demo 合入 main。** 2026-08-10 实测
  `git merge-tree --write-tree main feat/kol-check-demo` 无冲突（该分支只领先
  一个提交 5687a4dd）。合并顺带解决三件事：kol-check 源码进 main、
  `wrangler.jsonc` 进 tracked、`data.json` 的 .gitignore 定向 negation 进 main。
  注意：合并前先移走主仓工作区里**未提交**的 `wrangler.jsonc` 副本（与分支版
  内容不同，git 会拒绝用 tracked 文件覆盖 untracked 文件）。合并后本节的
  checkout / 还原步骤全部作废。

---

## 陷阱二：package.json 不在 git 里

根 `.gitignore` 的 `*.json` 把 `src/finer_site/package.json`、`package-lock.json`
也忽略了——fresh clone / 新 worktree 里**没有这两个文件**，无法 `npm install`。
需从既有主仓工作区复制（连同 `node_modules` 一起 `cp -R` 实体复制，
Turbopack 拒绝 symlink）。

---

## 排查

- **构建产物缺页面**：部署前确认 `out/` 里存在 `kol-check/` 目录；缺了说明第 ① 步没执行。
- **线上没更新**：确认部署输出的 Worker 名是 `finer-site`（错名字会部署到别的 Worker）。
- **og 预览图不显示**：社媒抓取有缓存，用对应平台的 debug 工具刷新即可
  （图在 `/og/finer-social-preview.png`）。

---

## 安全

- 不要把 Cloudflare API Token / 全局 API Key / Zone ID 贴进任何对话或截图。
- wrangler 的登录态保存在你本机 `~/.wrangler`，AI 不接触。
