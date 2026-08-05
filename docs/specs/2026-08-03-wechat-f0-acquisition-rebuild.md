# F0 微信公众号获取路径重建

> 触发：安装并研读 [hxer7963/podcast-summary](https://github.com/hxer7963/podcast-summary) 后，评估其对 Finer F0 的价值，并重建已失效的公众号获取链路。

## 概述

微信于 **2026-07-29** 关闭了公众平台后台「搜索其他公众号文章」的接口，48 小时内所有基于该链路的开源工具集体失效——Finer F0 依赖的 `wechat-article-exporter` 于 07-30 宣布停止维护。本次不修旧链路，而是**把 discovery 与 fetch 拆成两个独立可替换的关注点**，并落地一条零凭证、零封号风险的 fetch 路径：给定文章 URL → 完整 F0 四件套（raw archive + ContentRecord + ImportReceipt + Project Memory 索引）。

已在本机真实数据上验证：12/12 篇公开文章抓取成功（26 req/min 无封禁），Wechat2RSS 实时 feed 端到端入库成功。全量测试 **3915 passed / 0 failed**，新增 85 条测试。

---

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/ingestion/wechat_public_article.py` | 新增 | 公开文章页抓取与解析：身份提取、页面状态分类、限速器、URL 形式判定 |
| `src/finer/ingestion/wechat_discovery.py` | 新增 | Discovery 抽象 + `AlbumDiscovery`（合集批量，免登录）+ `RssDiscovery`（任意 RSS/Atom bridge）+ `StaticUrlDiscovery` |
| `src/finer/ingestion/wechat_url_intake.py` | 新增 | F0 落盘编排：四件套产出、幂等、批量、bridge 内容降级 |
| `src/finer/services/wechat_content_record_builder.py` | 修改 | 新增 `build_public_article_record()`；补 `TYPE_CHECKING` 导入 |
| `src/finer/cli.py` | 修改 | 新增 `wechat-import` 子命令 |
| `tests/test_wechat_public_intake.py` | 新增 | 85 条测试，全离线 |

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

### 3. 决定能否抓取的是 `chksm` 签名，不是长短链

> **本节已按后续实测更正。** 初版结论是「长链一律被拦」，这不准确——真正的分界是签名。

| URL 形式 | 结果 |
|---|---|
| `/s/<token>`（分享短链） | HTTP 200，完整正文 |
| `/s?__biz=&mid=&idx=&sn=&chksm=…`（**带签名**长链） | HTTP 200，完整正文（实测 3.1 MB） |
| `/s?__biz=&mid=&idx=&sn=`（**无签名**长链） | 302 到 `wappoc_appmsgcaptcha`，17 KB 验证页 |

决定性对照：同一条 URL，带 `chksm` 返回 3.1 MB 正文，把 `chksm` 摘掉立刻变 17 KB 验证页。无签名长链在 iOS/Android MicroMessenger 与桌面 Chrome 三种 UA 下均被拦，所以那仍是 URL 属性而非限流或 IP 信誉——只是「属性」的正确定义是**有没有签名**。

这条更正很要紧，因为它决定一个 discovery 源是否自给自足：

- **`getalbum` 返回带签名长链** → 自给自足，discovery 与 fetch 都不需要凭证（见发现 11）
- **Wechat2RSS 的 feed 剥掉了签名**（实测 0 短 / 35 无签名长链）→ 其 URL 无法回源，只能用它 `content:encoded` 里的全文

代码侧对应 `is_fetchable_url()`；`is_short_link()` 保留但只回答「是不是分享短链」这个形状问题。

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

### 7. 微信读书官方 Agent Gateway 做不了公众号 discovery（已实测证伪）

这条曾是排序第一、投入产出比最高的候选：腾讯官方发个人 API Key，不需要逆向 cookie，没有会被封的账号。**用真实 Key 实测后确认不可用**，验证脚本见 `scripts/verify_weread_gateway.py`。

网关本身是真的、活的、鉴权严格（无 Authorization → `-2010 用户不存在`；伪造 `wrk-` key → `-2013 鉴权失败`）。`/_list` 返回 15 个接口，官方文档（`Tencent/WeChatReading`）也确实写明支持公众号：`/store/search` `scope=2` 搜公众号、`scope=4` 搜公众号文章，`/book/chapterinfo` 有 `chapters[].isMPChapter`，`shelf.md` 说 `books[]` 含「公众号类书籍」。

**但服务端恰好只拒绝这两个 scope。** 同一个 Key、同一个端点、同一次会话：

| scope | 含义 | 结果 |
|---|---|---|
| 10 | 电子书 | HTTP 200，20 条 |
| 0 | 全部 | HTTP 200，7 条 |
| 6 | 作者 | HTTP 200，4 条 |
| 14 | 听书 | HTTP 200，0 条（正常空结果） |
| **2** | **公众号** | **HTTP 499 / `-2041`** |
| **4** | **文章** | **HTTP 499 / `-2041`** |

排除了「Key 无效」和「接口坏了」两种解释。`-2041` 是微信读书的风控错误码（社区 2026-08 报告 cookie 版接口触发它时会出滑块），出现位置恰好是公众号——与 7-29 那轮封堵一致，但我无法证明是同一次动作，只能说吻合。

其余入口也逐一堵死：书架 126 本书里**零个**公众号（无 `MP_WXS_*`、无 `author=="公众号"`）；`mp` 字段只是「文章收藏」空壳入口（`bookId: "mpbook"`），拿它调 `/book/chapterinfo` 返回 `chapters: []`；用三个真实公众号名做综合搜索（`scope=0`），返回分组只有电子书/作者/书单/待上架，**所有响应里「公众号」三个字一次都没出现**，零 `mp.weixin` 链接，零 `MP_WXS`。

顺带一提：即使 discovery 通了，网关的 15 个接口里也**没有取文章正文的端点**——它本来就要靠本项目的公开页抓取补正文。现在 discovery 这一半先没了。

**结论：这条路关闭。** 官方文档写了但服务端不放行，不要按文档规划。价值在于它消除了整个选型里最大的不确定项，决策因此收敛。

### 8. Wechat2RSS 公开 feed 撑不起财经场景（更正前一版结论）

前一版把它排为主源，依据是「财经号可发 GitHub issue 免费申请上架，8-01 提交当日即受理」。**这个依据是错的**，逐项实测更正：

**「closed 当日」不等于上架。** issue #514 财联社、#516 腾讯研究院、#515 AI寒武纪 都在 2026-08-01 被 `state_reason: completed` 关闭——但今天（08-03）三个号**都不在公开列表里**。而且批量请求 #506（创新药/AI科技/商业航天/机器人）是被 `not_planned` 明确拒绝的。

**公开目录已冻结 19 个月。** 列表源文件 `list/all.md` 最后一次提交是 **2025-01-03**。issue 在 2026-08 持续关闭，列表却纹丝不动——所以 close 大概率只是维护者归类动作，与免费列表无关。

**目录构成本身就不面向财经。** 395 个 feed 分四类：安全 326、开发 12、其他 8、用户提交 49。**没有财经分类**。名称含财经/投资关键词的只有 7 个，其中真正做投资/经济的约 3–4 个（长赢指数投资、逻辑与现实经济、卢瑟经济学系列）。

**收录标准还主动排除财经 KOL 的主流内容。** 原文：「以下情况一般不收录：特定地区/组织的公告/通知类内容；没有足够深度的非科普向内容」——市场点评、公告解读、盘面快讯正落在这个排除项里。

**已收录的号确实活着，这一点前一版没说错。** 实测：猫笔刀最新 2026-08-02、看雪学院 08-01、逻辑与现实经济 07-31、长赢指数投资 07-30，均为全文。但冻结的列表也在烂——卢瑟经济学之安生杂谈的 feed 已 404。

**结论：只有当你的目标号恰好已在那 395 个里，这条路才成立；对财经 KOL 基本不成立。** 它可以作为补充源（那 3–4 个经济类号确实可用），但不能做主源。

### 9. 微信文章在本系统里历史上是怎么进来的

一个容易被忽略的事实：`configs/creators/` 31 个 creator 里，27 个是券商，3 个真实 KOL（9友/trader韭/猫大人），**有 wechat 配置的只有 `_template.yaml`**。公众号渠道从来没声明过目标账号。

而 `data/` 里 54 条去重后的 mp.weixin 短链，来源是**飞书聊天记录导出**（猫大人 chat history），不是任何公众号渠道。也就是说：微信文章一直是以「别人在群里转发链接」的形式进来的。

这对选型有直接影响——见「未解决项」第 1 条。

### 10. 合集（album）是唯一跑通的免登录批量路线

问题起因：能不能给一个文章链接，就把该账号发过的内容全拿下来。答案是**有条件的可以**——通过合集。

`mp/appmsgalbum?action=getalbum` **完全不需要 cookie 或 session**，能翻完整个合集，而且返回的每条 URL **自带 `chksm` 签名**（见发现 3），因此可以直接抓。这是目前唯一一条 discovery 与 fetch 两端都零凭证的路线，也就没有会被封的账号。

实测（2026-08-03，一个真实合集）：

```text
第1页 +20  continue_flag=1  最早 2026-05-19
第2页 +20  continue_flag=1  最早 2026-01-09
第3页 +20  continue_flag=1  最早 2024-12-11
第4页  +6  continue_flag=0  最早 2024-05-16
合计 66 篇，跨度 2024-05-16 → 2026-07-28
```

`base_info.article_count` 恰为 `66`，**与实际抓到的数量精确吻合**，说明翻页没有截断。66 条 URL 全部可直接抓取；端到端导入后 `acquired_via=public_url`（一手抓取，非 bridge 二手内容），raw HTML 完整归档。

**只需要 `album_id`。** 实测把 `__biz` 换成错误值、甚至留空，返回的都是同一个合集——该参数被服务端忽略。`album_id` 从合集内任意一篇文章的页面源码里取（`album_id: '…'`）。

**限制是结构性的，不是技术性的：**

- 合集是**作者手动整理的文件夹**，覆盖的是作者归入其中的文章，不等于该账号的全部发文
- 没建合集的号完全无法用这条路枚举——**本次问题里给的示例账号「方伟看十年」正是这种**（其文章页 `album_info_list = []`）
- `action=getalbumlist`（列出某账号的所有合集）**需要 session**，所以无法从账号反查合集，只能从「已知属于某合集的一篇文章」正向进入

CLI：`python -m finer.cli wechat-import --album <album_id>`

### 11. 「按账号拉全量」的完整路线评估

合集路线（发现 10）覆盖不到没建合集的号，所以把剩下的路线全部查了一遍。按「是否需要交出账号」分组：

**零凭证，但都不是按账号枚举**

| 路线 | 实测结论 |
|---|---|
| `profile_ext?action=home` | 验证页 |
| `profile_ext?action=getmsg` | `ret:-3 no session`，要 cookie |
| `mp/homepage` | 实为错误页 |
| `getalbumlist`（列某号的合集） | `ret:-3 no session` ——**所以无法从账号反查合集，只能从合集内文章正向进入** |
| 搜狗 `type=1` 公众号搜索 | 空结果（已废） |
| 搜狗 `type=2` 文章搜索 | **仍活**：翻 5 页 40 条无验证码。但是关键词匹配，结果里混着「熠数方伟」「红桥区两优一先」等无关号，不是按号枚举；链接是带签名的临时跳转，会过期 |

**要花钱，零账号风险**

- **极致了 dajiala**：`/fbmain/monitor/v3/post_history` 今日实测在线并正常鉴权（无 key 返回 `code:10002 key或附加码不正确`，不是空壳）。入参支持 ghid / 公众号名 / **任意文章链接**，0.14 元/次；注册送体验额度，可先验证再付费。**关键优势：接口文档写明 2024-12-01 起返回的文章链接均为短链接**——正好落在我们抓取层的可用形式里。
- **次幂数据 cimidata**（原二十次幂）：全部历史文章 Excel 导出，**50 元/年/账号**，入参可直接粘贴一条文章链接，字段含发布时间/标题/阅读量/在看数/文章链接。

**要交出账号**

- 微信读书 cookie 版 `/web/mp/articles`：能拿标题+短链+全文，但**覆盖深度存在直接冲突的证据**——wewe-rss 多个 issue 报告只能回溯半年到一年，而 wechat-download-api 作者称有全部历史，双方都没给号级验证。且 `-2041` 风控 2026-08-01 已有多人触发，所有活着的实现都内置了账号池轮换和 TLS 指纹伪装，这本身就是「单号会被打」的证据。
- PC 微信客户端凭据 + `profile_ext?action=getmsg`：**唯一能拿到建号至今全量**的路线（`can_msg_continue` 翻到底），但用的是主微信登录态，且现成实现基本只有 Windows。

**已死，不必再试**：公众平台 fakeid 超链接接口（2026-07-30 起 `ret=200013`）。

**对本次示例账号「方伟看十年」**：取样 4 篇文章（1 篇原始 + 3 篇经搜狗），外加同人第二个号「方伟看10年」（`MzYzNDc3NzYzNw==`）的 2 篇，`albumlist` **全部为空**，合集路线 0 覆盖。现实选择是极致了（有免费额度可先验证）或次幂数据（50 元/年）。

### 12. 限速的真实边界比预想宽

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
# 3915 passed, 69 skipped  （新增 85 条，无回归）
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

1. **Discovery 源尚未选定，且两条零风险候选均已证伪。** 官方 Gateway 服务端拒绝公众号 scope（发现 7），Wechat2RSS 公开目录冻结且无财经号（发现 8）。更根本的是：`configs/creators/` 里公众号目标数为零，历史上微信文章全部经飞书群转发进入（发现 9）——所以真正该先回答的是「要哪些号」，而不是「用哪个 bridge」。当前可用且零风险的是 `--url-file` 手工队列与飞书转发链路。
2. **`__biz` ↔ `gh_` 映射缺失。** bridge 与短链两条路线对同一文章产生不同 content_id。若两条路线并用，需要一次对账；目前建议一个账号固定一条路线。
3. **图片未本地化。** 正文保留 `mmbiz.qpic.cn` 远程 URL。微信图片有防盗链，且未来可能失效，长期归档需要下载或代理——但这属于 F0 raw archive 的增强，不阻塞主链路。
4. **无定时触发。** `wechat-import` 是手动/脚本调用，未接 launchd。接入前应先确定 discovery 源。
5. **旧 exporter 代码未清理。** `wechat_exporter_client.py`、`wechat_mp_adapter.py` 及 `/api/wechat/sync/{account_id}` 路由仍在，现已确认为死代码。清理是独立变更，需你确认后再做。

---

## Discovery 源选型（需你决策）

四条路线的实测结论。**注意一个反直觉的修正：付费 150 元/年的 Wechat2RSS 私有部署反而要你交出微信号扫码登录，而免费的公开 feed 不需要。**

| 路线 | discovery | 封号风险 | 成本 | 现状 |
|---|---|---|---|---|
| Wechat2RSS 公开 feed | ⚠️ 仅限已收录的 395 个 | **零**（你不出任何账号） | 免费 | 已收录号全文且新鲜，但**目录冻结于 2025-01-03**、无财经分类、财经号申请无效；详见「关键发现 8」 |
| Wechat2RSS 私有部署 | ✅ 全文 | **有**（须扫码登录自己的微信读书） | 150 元/年 | 协议明示「可能导致微信号被限制或封禁」 |
| we-mp-rss `weread_mp` | ✅ | 有（cookie 登录） | 免费自建 | 2026-08-03 刚合并，1 天新代码；8-01 已有 -2041 滑块风控报告 |
| ~~微信读书官方 Agent Gateway~~ | ❌ **实测不可用** | — | — | 官方文档写了 `scope=2/4`，服务端一律 `-2041` 拒绝；详见「关键发现 7」 |
| 极致了商业 API | ✅ | 零（风险外包） | 0.14 元/次 ≈ 210–420 元/月 | 7-29 后是否受影响官网无公告，需付费验证 |

**建议顺序（Gateway 证伪 + Wechat2RSS 公开 feed 证伪后，第二次更新）：**

两条零风险路线都已证伪，剩下的选择本质是「接受账号风险」「花钱」还是「改问题定义」。按推荐度：

1. **先回答「到底要哪些号」**——`configs/creators/` 里公众号目标数为零，而历史上微信文章全部来自飞书群转发。在没有目标清单前，任何 discovery 源都是空转。
2. **飞书转发链路 + 已建成的抓取层**——零风险、零成本、无需任何新 discovery 源，且与内容实际的进入方式一致：飞书消息里出现 mp.weixin 链接 → 直接喂 `import_article`。数据里已有 54 条去重短链证明这条流量真实存在。
3. **`--url-file` 手工队列**——永不失效的地板，适合少量重点号。
4. **极致了商业 API**（0.14 元/次，50 号每天 1 轮约 210 元/月）——唯一能做真 discovery 且零账号风险的路线；上线前先买最小额度对 3 个号跑 T+1 对账。
5. **Wechat2RSS 公开 feed 作为补充**——只对已收录的 3–4 个经济类号有效，不能做主源。
6. **不建议**：Wechat2RSS 私有部署（150 元/年但要交出微信读书账号，与「介意封号」冲突）；we-mp-rss weread 模式（同样交账号，且 8-01 已有 -2041 风控报告）；任何 Hook / iPad 协议 / 群控 SDK；修旧的 fakeid 链路（已死）；微信读书官方 Gateway（已实测证伪）。

架构上已经为「多源冗余 + 按 content_id 去重」准备好了。这次断供说明单一 discovery 源不是过度设计问题，多源是这个领域的最低生存配置。

---

## 合入 main 的独立复核（2026-08-04）

分支 12 commits 以 `--no-ff` 合入 main（8 个文件与 main 侧改动**零交集**）。
合并后跑全量 pytest（**4,110 passed**，+89 全绿）并做四维对抗审查
（安全 / 身份 / F0 边界 / 解析器），每条发现走独立对抗核验（默认拒真）。

### 确认并修复的 2 个缺陷

两条形状完全一样：**防御已经写好了，只是没用到全部字段上。**

| # | 位置 | 缺陷 |
|---|---|---|
| 1 | `wechat_url_intake.py:450-451` | `_render_markdown` 的五个 provenance 字段里，`title`/`account_name`/`author` 过了 `_header_safe`，而 `原文链接`/`账号标识` 是裸插值。`__biz` 来自第三方 feed 的 URL query 而 `parse_qs` 会百分号解码（`%0A` → 真换行），`ghid` 来自远程 HTML 的正则捕获（否定字符类吃换行）——两者都能在 raw archive 里伪造出第二条「原文链接」。核验方用真实 `RssDiscovery.discover()` + 敌意 RSS 复现出了伪造行。 |
| 2 | `wechat_discovery.py:156,170` | `safe_feed_url` 的整个存在理由是剥掉 feed 凭据，却用 `netloc` 重建——**`netloc` 含 userinfo**。`https://svc:token@host/…` 的凭据原样穿过「安全形式」，流进错误 envelope（`_SENSITIVE_KEYS` 按键名脱敏，`feed_url` 不在表内）、日志、以及每条 ContentRecord 的 `discovery_source`。 |

修复：① 五个字段一律过 `_header_safe`；② 新增 `_safe_host()` 用 `hostname`(+port)
重建，畸形 URL 返回 `invalid-host` 而**不回退成原串**。3 条回归测试钉住
（`tests/test_wechat_public_intake.py`，88 passed）。

写测试时自己也踩了一次：第一版断言「行内不得含 evil.test」是错的——
`_header_safe` 把 `>` 换成全角 `＞` 并压平换行后，载荷作为**字面量**留在合法
行内是正确行为。真正的安全属性是「它无法成为一条 provenance 行」，断言据此改写。

### 未完成的核验

另有 14 条发现（解析器 HTML5 边界、身份分裂、provenance 诚实性等）因会话额度
中断未走完对抗核验，**既未确认也未排除**。它们不阻塞合并（全量测试绿、
两条确认项已修），但下轮碰微信链路时应先跑完这批核验。

### 14 条待核验发现的补跑（2026-08-05）

前一轮因会话额度中断的 14 条全部走完对抗核验（7 组分头核验 + 裁决）。
**13 条机制为真，其中 3 条实测判为 severity `none`**（机制存在但不可达或无害：
未闭合内联标签、13 位毫秒时间戳截断、协议相对图片 URL），1 条被否
（legacy exporter builder 缺 `acquired_via`——该路径已不可产出记录）。

**已修 8 条**，按形状归为三类：

**A. 解析器正文边界（#9/#10/#11）——一次性换成标签栈**

`_content_depth` 计数器换成标签名栈。#9 是前一会话修 void 标签那个 bug 的
**另一半**：`HTMLParser` 不是 HTML5-aware，void 标签与可选结束标签是同一个
盲区的两种表现，上次只补了一半。实测 7 个边界案例修前 4 个泄漏、修后零泄漏。

> **核验方的重要校准**：它把解析器跑过仓库里 25 份**真实微信样本页**——零泄漏、
> 标签全平衡，且 bridge 路径结构上免疫（`parse_bridge_article` 的 wrapper
> 后面没有内容）。因此 #9 从 high 降为 **medium：这是对页面结构漂移的潜在
> 防御缺口，不是当前正在发生的缺陷**。修仍值得（页面结构会变），但不该按
> 「线上正在丢数据」计。

**B. 「不变量写明了但某处没守」（#13/#6/#0/#2）**

| 缺陷 | 仓库自己写明的不变量 | 没守的地方 |
|---|---|---|
| `poc_token` 误判 | `_is_structural_block` docstring：这些标记「不可能出现在散文里」 | 裸 `poc_token` 是普通标识符 |
| 身份坍缩 | `_PAGE_VARS` 取 mid/idx 要求纯数字 | `identity_from_url` 从 URL 取时不校验 |
| `raw_path` 绝对 | schema 字段：「Relative path…under data/raw/」 | builder 存绝对路径 |
| 伪造发布时间 | schema `Optional`「may be unknown」+ 测试名 `test_missing_publish_time_is_none_not_now` | builder 填 `now()` |

伪造发布时间那条核验方**上调**了严重度：F5 的执行时钟正是从 `published_at`
推出来的，填 `now()` 等于让导入时刻冒充发布时刻——与本轮早先做过的全语料
时钟修复是同一类错。改为留 `None`，让下游 `timing_builder` 显式报错：
**响亮地失败好过静默用错基准**。

**C. 错误信封（#3）** — 归档写失败（磁盘满/只读挂载）以裸 `OSError` 逃出，
绕开 Line F。F0 其余写点都用 `F0_IO_001`，补齐。

### 仍未修（2 条，均为设计决策而非补丁）

- **#7 短链 token 做身份不唯一**：同一篇文章经不同短链会得到两个
  `article_id`。修法要改 Project Memory 的 `stable_key` 口径（改用
  `(account_id, title, published_at)` 或正文哈希），属身份设计变更。
- **#8 带签名长链缺 mid/idx 被跳过**：可从 URL 回填身份（`parse_bridge_article`
  已经这么信任 URL 了），但会把「跳过」变「导入」，属召回口径变更。

验证：`pytest tests/test_wechat_public_intake.py` **107 passed**（+19），全量见提交。
