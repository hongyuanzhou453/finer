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

### 10. 限速的真实边界比预想宽

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
