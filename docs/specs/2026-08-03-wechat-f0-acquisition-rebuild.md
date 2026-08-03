# F0 微信公众号获取路径重建

> 触发：安装并研读 [hxer7963/podcast-summary](https://github.com/hxer7963/podcast-summary) 后，评估其对 Finer F0 的价值，并重建已失效的公众号获取链路。

## 概述

微信于 **2026-07-29** 关闭了公众平台后台「搜索其他公众号文章」的接口，48 小时内所有基于该链路的开源工具集体失效——Finer F0 依赖的 `wechat-article-exporter` 于 07-30 宣布停止维护。本次不修旧链路，而是**把 discovery 与 fetch 拆成两个独立可替换的关注点**，并落地一条零凭证、零封号风险的 fetch 路径：给定文章 URL → 完整 F0 四件套（raw archive + ContentRecord + ImportReceipt + Project Memory 索引）。

已在本机真实数据上验证：12/12 篇公开文章抓取成功（26 req/min 无封禁），Wechat2RSS 实时 feed 端到端入库成功。全量测试 **3908 passed / 0 failed**，新增 78 条测试。

---

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/ingestion/wechat_public_article.py` | 新增 | 公开文章页抓取与解析：身份提取、页面状态分类、限速器、URL 形式判定 |
| `src/finer/ingestion/wechat_discovery.py` | 新增 | Discovery 抽象 + `RssDiscovery`（任意 RSS/Atom bridge）+ `StaticUrlDiscovery` |
| `src/finer/ingestion/wechat_url_intake.py` | 新增 | F0 落盘编排：四件套产出、幂等、批量、bridge 内容降级 |
| `src/finer/services/wechat_content_record_builder.py` | 修改 | 新增 `build_public_article_record()`；补 `TYPE_CHECKING` 导入 |
| `src/finer/cli.py` | 修改 | 新增 `wechat-import` 子命令 |
| `tests/test_wechat_public_intake.py` | 新增 | 78 条测试，全离线 |

未改动：`ContentRecord` schema（`wechat_article` 已在闭集内）、`contracts.ts`、数据库结构、既有 exporter 代码。

---

## 关键发现（一手实测，2026-08-03）

### 1. 断供是行业级的，不是配置问题

三个互相独立的项目在同一 48 小时内因同一上游接口失效：

- `wechat-article-exporter`（12.6k star）issue #200，2026-07-30，维护者原文：「项目所依赖的上游核心接口已被微信关闭（大概率也不会再开放了）」
- `we-mp-rss` issue #439：「昨天微信把这个可以搜其他公众号的口子给堵上了，现在无法搜索其他公众号的内容，只能搜自己发布的」
- `wechat-download-api` issue #23（07-31）以该断供为前提讨论替代方案

**结论：不要修旧链路。** 它不是坏了，是被关了。

### 2. Finer 的公众号路径实际上「从未生效」，而非「中途失效」

审计发现三层叠加断点：

1. **部署层**：exporter 服务从未托管（无 launchd，3001 端口无监听），E2E 门 `P3-WECHAT-MP` 自 2026-06-05 起一直 PENDING
2. **契约层**：`wechat_exporter_client.py:717` 调 `POST /api/web/mp/export`，但本机 exporter v2.3.16 根本没有这个端点（只有 `appmsgpublish`/`searchbiz`/`info`/`logout`/`profile_ext_getmsg`/`searchbyurl`）。即使服务跑起来并登录成功，每篇文章导出必 404
3. **凭证层**：`data/cache/wechat/` 为空，从未持久化过任何登录账号

磁盘证据：`data/F0_intake/` 下**没有 wechat 子目录**，0 条真实 ContentRecord；`data/raw/wechat/` 40 个文件全在 `test_account/` 夹具目录下。

### 3. 只有短链接可抓，长链接形式被无条件挑战

这是本次最有架构后果的发现：

| URL 形式 | 结果 |
|---|---|
| `/s/<token>`（分享短链） | HTTP 200，完整正文，稳定 |
| `/s?__biz=&mid=&idx=&sn=`（规范长链） | 一律 302 到 `wappoc_appmsgcaptcha` 验证页 |

验证方法：对**同一篇文章**，短链抓取成功后立即用长链请求 → 被拦截；换 iOS MicroMessenger、Android MicroMessenger、桌面 Chrome 三种 UA → 全部被拦截。**这是 URL 形式的属性，不是限流、不是 IP 信誉，改 header 绕不过去。**

直接后果：**Wechat2RSS 的 feed 只发长链（实测 0 短 / 35 长），其 URL 无法回源抓取**，可用的是它 `content:encoded` 里自带的全文。

### 4. 验证页有 JS 渲染变体（已修复的真缺陷）

初版分类器按可见文案（「环境异常」「访问过于频繁」）判定拦截。但验证页存在一个 ~17KB 的 JS 外壳变体，服务端 HTML 里**不含任何这些字样**，只有 `PAGE_MID='mmbizwap:secitptpage/verify.html'`。

后果是危险的：外壳被解析为「空文章」，而 EMPTY 是终态跳过——**一篇只是被限流的文章会被静默判死、永不重试**。现按外壳标记 + 重定向后 URL 双重检测，归类为 BLOCKED。

### 5. 路径穿越（自查发现并已修，commit `f5b44f1a`）

初版把 `account_id` / `article_id` 直接当路径组件用，但这两个值全都来自不可信输入：`__biz` 是第三方 RSS bridge 提供的 URL query 参数，`user_name`/`mid`/`idx` 是从远程页面里正则抠出来的。**没有任何净化。**

实测复现：一个携带 `__biz=../../../../tmp/pwned` 的 feed 条目，把 `9_1.md`、`9_1.sidecar.json`、`sync_state.json` 写到了 data 根目录之外，而导入结果报告的是 `status=imported`。

良性输入也会踩到：`__biz` 是 base64，字母表含 `/`，会把一个账号无声地拆散到嵌套目录里。

修法是双层的——在身份层净化（保证路径组件与落盘 metadata 一致），并在写盘前加围栏（未来若净化逻辑回退，会响亮报错而不是落到磁盘上）。穿越段做替换而非剥离，且全由点构成的标识符退回占位符，因此没有任何编码路径能产出 `.` 或 `..`。对合法标识符净化是恒等变换：真实文章的 `content_id` 未变（已对真实数据验证），且磁盘上 0 条 wechat ContentRecord，无迁移问题。

### 6. 四路对抗性审查发现的其余缺陷（已修，commit `acdeccd5`）

对新代码做了正确性/安全/契约/测试覆盖四个视角的对抗性审查，提出 24 条、独立复核后 20 条成立。归并后的根因：

**正文边界失守（最严重）。** Python 的 `HTMLParser` 不懂 HTML5：裸 `<img>` / `<br>` 只报 start tag 没有对应 end tag，深度计数器永不回平，`#js_content` 真正的 `</div>` 因此从未被识别，**页脚（二维码、赞赏、阅读原文、广告）被当作正文归档**。更糟的是它同时击穿了长度守卫——正文只有「加载中」的页面因为拼上了泄漏的页脚而被判为 OK。这正是本模块存在的意义所要防的那件事。现在 void 标签在正文和元数据捕获两处都对称地排除出计数。

**身份坍缩（数据丢失）。** `article_id` 在缺 `mid`/`idx` 时回退到 URL 路径尾巴，而长链的路径就是光秃秃的 `/s`——于是所有这类文章都拿到 `article_id="s"`，塌到同一个 `content_id`，**第二篇被当成 duplicate 静默丢弃**。现在退化的身份就等于没有身份，没有身份的页面直接跳过，绝不编造。

**正文与页面状态混淆。** 那些状态标记本身就是普通中文句子。一篇讨论审查、正文里引用了「该内容已被发布者删除」的真文章，会被判定为已删除而丢掉——而这恰恰是这条流水线最想抓的内容。现在只有在找不到正文时才参考可见标记；验证页外壳标记和重定向 URL 是机器痕迹，不会出现在文章里，因此始终可信。

其余：撕裂的导入不再被永久判为 duplicate（原子写 + 重复探测改到最后落盘的收据上）；限速器默认值不再意外关闭限速；bridge 标题无法伪造 provenance 行；bridge 时间戳归一到 UTC；feed URL 在日志与错误信封中脱敏（它常带 token）；二次复杂度的空白清理换成线性；未知 charset 不再以裸 `LookupError` 逃出 Line F 信封。

### 7. 限速的真实边界比预想宽

本机住宅 IP + 普通 Android UA，12 篇不同文章背靠背请求，26 req/min，全部 200，无验证页。失败的 2 篇是真实内容状态（`该内容已被发布者删除` / `此内容因违规无法查看`），不是反爬。

对照：调研 agent 从数据中心 IP 请求同样的 URL 拿到验证页。**决定因素是 IP 信誉，不是 UA。** 生产默认取 6s 间隔（10 req/min），留足余量。

---

## 架构影响

### F0 边界

完全在 F0 内：只产 ContentRecord、raw archive、ImportReceipt、F0 index。不做 OCR、不做 topic assembly、不做实体/时间锚定、不做 intent。

### 契约

- `source_type="wechat_article"` 已在 `schemas/content.py:27` 闭集内 → **无 schema 变更，无 contracts.ts 同步，无 drift 风险**
- 错误全部走 Line F canonical envelope（`stage="F0"`、`source_channel="wechat"`、`retryable`、`operation`）
- 落盘位置：`data/raw/wechat/{account_id}/`、`data/F0_intake/wechat/{content_id}.json{,.receipt.json}`

### 身份设计

公开文章页自带完整身份，无需登录即可构造稳定 `content_id`：

| 页面变量 | 用途 |
|---|---|
| `user_name` = `gh_1652e0dbaabd` | `creator_id`（微信账号规范标识） |
| `__biz` = `MzA3NTg4MDUzNQ==` | 账号在 URL 空间的标识 |
| `mid` + `idx` | `article_id`，账号内唯一 |
| `ct` | `published_at`（unix 秒） |

`article_id = f"{mid}_{idx}"`，**不用 `/s/<token>`**——同一篇文章可能有多个 token。已测：同一文章走两个不同 token，落到同一 `content_id`（第二次返回 `duplicate`）。

**已知身份缺口**：bridge 路径（长链）只能拿到 `__biz`，拿不到 `gh_`，因此同一篇文章经 bridge 导入与经短链导入会产生**两个不同的 content_id**。两个标识都写进 metadata 供日后对账，但实践上**一个账号应固定走一条获取路线**。

### Provenance 诚实性

receipt 的 artifact role 直接编码来源：

- `public_html` / `public_markdown` —— 微信实际服务的页面（一手证据）
- `bridge_markdown` —— 第三方 feed 提供的正文（二手）

record metadata 带 `acquired_via`（`public_url` / `bridge_content`）与 `discovery_source`。`--first-hand-only` 可强制只要一手证据。**审计时若分不清这两者，就无法判断记录的证据强度。**

---

## 关键决策

**为什么把 discovery 和 fetch 拆开。** 这次断供证明单一 discovery 源的期望寿命以「月」计：搜狗微信索引空了、公众平台接口被关、feeddd 2023 就停了、微信读书 cookie 接口正在被 -2041 风控。而「抓一篇公开文章页」多年稳定且不需要凭证。所以 discovery 是一个只需产出 URL 的可插拔输入，fetch 及其下游全部与之解耦——换 bridge 就是换一个 `--feed` 参数，不动任何 F0 代码。

**为什么保留 bridge 正文降级而不是只认一手抓取。** 排第一的零风险 discovery 源（Wechat2RSS 公开 feed）只发长链，若不接受其自带正文，这个源直接不可用。降级是必要的，但必须诚实标注来源，并可通过 `--first-hand-only` 关掉。

**为什么复用而非重写 F0 落盘层。** `WeChatArtifactStore`、receipt 构造、`F0IndexWriter` 与获取方式完全无关，本来就是好的。死掉的只有获取层——旧 sync 循环里只有两处触碰 exporter（`get_articles` 和 `export_article`）。

**为什么 DELETED/VIOLATION 返回而非抛异常。** 它们是关于文章的**真实事实**，值得记录；BLOCKED 是关于**我们自己**的状态，是唯一值得退避重试的。混为一谈会导致要么丢数据要么无限重试。

**podcast-summary 的借鉴与不借鉴。** 借鉴了其 HTML→Markdown 状态机（`wechat_fetch.py`，MIT，已在模块 docstring 注明）、成本分层路由思想、幂等阈值检查、「新渠道 = 一个脚本 + 路由表一行」的扩展协议。**没有**采用其 `README.md`-as-metadata + `✓ Episode complete:` stdout-grep 契约——与 Finer 的 Pydantic ContentRecord + JSON receipt 真相源冲突。其反爬检测过于薄（无限速、无验证页 JS 变体识别、无长/短链区分），生产化时全部重写。

---

## 验证结果

```bash
pytest tests/ -q --ignore=tests/test_wechat_live.py
# 3908 passed, 69 skipped  （新增 78 条，无回归）
```

真实数据端到端：

```bash
# 短链直抓
python -m finer.cli wechat-import --url-file urls.txt --interval 3
# → counts {"imported": 2}，两个不同账号，四件套齐全

# Wechat2RSS 实时 feed（长链 → bridge 正文降级）
python -m finer.cli wechat-import --feed 'https://wechat2rss.xlab.app/feed/<id>.xml' --limit 2
# → counts {"imported": 2}，acquired_via=bridge_content，receipt raw_paths=[bridge_markdown]
# → creator_name 从 channel/title 正确取到「看雪学苑」

# 重跑
# → status: duplicate（幂等）
```

抓取实测：12/12 篇公开文章，26 req/min，0 封禁；2 篇失败为真实内容状态（已删除/违规）。

---

## 未解决项

1. **Discovery 源尚未选定。** 代码已就绪，但选哪个源涉及花钱与账号风险，需你决定（见下节）。当前可用的是 `--url-file` 手工队列和任意 RSS bridge。
2. **`__biz` ↔ `gh_` 映射缺失。** bridge 与短链两条路线对同一文章产生不同 content_id。若两条路线并用，需要一次对账；目前建议一个账号固定一条路线。
3. **图片未本地化。** 正文保留 `mmbiz.qpic.cn` 远程 URL。微信图片有防盗链，且未来可能失效，长期归档需要下载或代理——但这属于 F0 raw archive 的增强，不阻塞主链路。
4. **无定时触发。** `wechat-import` 是手动/脚本调用，未接 launchd。接入前应先确定 discovery 源。
5. **旧 exporter 代码未清理。** `wechat_exporter_client.py`、`wechat_mp_adapter.py` 及 `/api/wechat/sync/{account_id}` 路由仍在，现已确认为死代码。清理是独立变更，需你确认后再做。

---

## Discovery 源选型（需你决策）

四条路线的实测结论。**注意一个反直觉的修正：付费 150 元/年的 Wechat2RSS 私有部署反而要你交出微信号扫码登录，而免费的公开 feed 不需要。**

| 路线 | discovery | 封号风险 | 成本 | 现状 |
|---|---|---|---|---|
| **Wechat2RSS 公开 feed** | ✅ 全文 | **零**（你不出任何账号） | 免费 | 实测新鲜（8-01 有新条目）；财经号可 GitHub issue 免费申请上架 |
| Wechat2RSS 私有部署 | ✅ 全文 | **有**（须扫码登录自己的微信读书） | 150 元/年 | 协议明示「可能导致微信号被限制或封禁」 |
| we-mp-rss `weread_mp` | ✅ | 有（cookie 登录） | 免费自建 | 2026-08-03 刚合并，1 天新代码；8-01 已有 -2041 滑块风控报告 |
| 微信读书官方 Agent Gateway | ❓ 未验证 | **最低**（官方发 Key） | 免费 | 文档写明 `/store/search` 支持 `scope=2 公众号`，但**零公开实测**；且无正文接口 |
| 极致了商业 API | ✅ | 零（风险外包） | 0.14 元/次 ≈ 210–420 元/月 | 7-29 后是否受影响官网无公告，需付费验证 |

**建议顺序：**

1. **先跑 30 分钟验证官方 Gateway**——这是投入产出比最高的一步。若 `scope=2` 真能返回 `MP_WXS_*`，你就拿到唯一一条腾讯官方授权的 discovery 通道，配合本次的公开页抓取正好补上它缺正文的短板，整条链路零逆向、零 cookie。
2. **主源用 Wechat2RSS 公开 feed**——零账号风险，把目标财经号通过 GitHub issue 申请上架（实测 8-01 提交当日即受理）。注意其授权条款限个人研究使用，产出结论不可对外分发原文。
3. **兜底用 `--url-file` 手工队列**——永不失效，适合重点号。
4. **不建议**：任何 Hook / iPad 协议 / 群控 SDK（唯一会真封微信号的路线）；修旧的 fakeid 链路（已死）。

架构上已经为「多源冗余 + 按 content_id 去重」准备好了。这次断供说明单一 discovery 源不是过度设计问题，多源是这个领域的最低生存配置。
