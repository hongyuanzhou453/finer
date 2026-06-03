# Finer OS 宣传站 — 部署指南（Cloudflare Pages）

> 目标：把静态产物 `out/` 部署到 Cloudflare Pages，绑定 **finer.t800.click**。
> 你的域名已在 Cloudflare 同一账户，绑定会**自动**配好 DNS + HTTPS，无需手填记录。
> 全程不需要把任何 API Token / Zone ID 交给 AI。

---

## 第 0 步：生成最新产物

```bash
cd src/finer_site
npm run build          # 产物输出到 src/finer_site/out/
```

`out/` 是纯静态站（HTML/CSS/JS + 图片），无后端，demo 全部前端 mock。

---

## 方式 A1：后台拖拽上传（推荐，零 CLI）

1. 登录 Cloudflare Dashboard → 左侧 **Workers & Pages** → **Create** → 选 **Pages** → **Upload assets**
2. 项目名填 `finer-site`（或自定义）
3. 把 `src/finer_site/out/` 文件夹**里的内容**拖进上传区
   - 提示：拖的是 `out/` 内部的文件，不是 `out` 这个文件夹本身
   - 嫌麻烦可先打包：`cd out && zip -r ../finer-site.zip .`，上传 zip
4. 点 **Deploy site**，几秒后得到一个 `finer-site-xxx.pages.dev` 临时地址 → 先打开确认页面正常、demo 能点
5. 进项目 → **Custom domains** → **Set up a custom domain** → 输入 `finer.t800.click`
   - 域名已在你的 Cloudflare，会**自动添加 CNAME**，无需手填 DNS
6. 等 1–5 分钟 SSL 证书签发（状态变 **Active**）→ 访问 https://finer.t800.click

---

## 方式 A2：wrangler CLI（可复用，每次一条命令）

需要先登录（浏览器授权一次，凭证只在你本机，不经过 AI）：

```bash
cd src/finer_site
npx wrangler login                                          # 浏览器授权
npx wrangler pages deploy out --project-name finer-site     # 首次会提示创建项目
```

之后每次更新只需：

```bash
npm run build && npx wrangler pages deploy out --project-name finer-site
```

绑定自定义域名同 A1 的第 5–6 步（或在 Pages 后台 Custom domains 里操作）。

---

## 更新站点

改完代码后重新构建并重新部署：

```bash
npm run build
# A1：把新的 out/ 再拖一次到 Pages 项目（会生成新 deployment）
# A2：npx wrangler pages deploy out --project-name finer-site
```

---

## 排查

- **页面 404 / 样式丢失**：确认上传的是 `out/` 内部内容，不是整个 `src/finer_site/`。
- **自定义域名一直 Pending**：等几分钟；若超过 15 分钟，去 DNS 面板确认 `finer.t800.click` 的 CNAME 指向 `finer-site.pages.dev`。
- **og 预览图不显示**：社媒抓取有缓存，用对应平台的 debug 工具刷新即可（图在 `/og/finer-social-preview.png`）。

---

## 安全

- 不要把 Cloudflare API Token / 全局 API Key / Zone ID 贴进任何对话或截图。
- wrangler 的登录态保存在你本机 `~/.wrangler`，AI 不接触。
