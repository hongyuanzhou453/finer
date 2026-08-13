# MiMo (Xiaomi) 接入指南 — 给 Agent 的操作手册

> 面向在本仓或外资研报仓调用 MiMo 的任何 Agent（Claude Code / Codex / OpenADE / 其他）。
> 每条结论都有实测背书，实测来源标注了日期与样本量。**没有标注实测的，就是没验证过，别当事实用。**
>
> 背景语料：2026-07-20~25 用 MiMo 对 26,069 份外资研报做了 12 类批量抽取，
> 累计 **8.89 亿 token / 103,832 条记录**。下述陷阱全部是那轮踩出来的。

---

## 0. 三十秒接入

```python
import requests

KEY = os.environ["MIMO_API_KEY"]          # 绝不硬编码、绝不打印
URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"   # 见 §1 端点分流

resp = requests.post(URL, timeout=180, headers={
    "Content-Type": "application/json",
    "api-key": KEY,                        # MiMo 用 api-key 头
    "Authorization": f"Bearer {KEY}",      # 同时带 Bearer，两个都发最稳
}, json={
    "model": "mimo-v2.5",
    "messages": [...],
    "max_completion_tokens": 6000,         # 不是 max_tokens！见 §3
    "temperature": 0,
    "thinking": {"type": "disabled"},      # 结构化任务务必关闭！见 §2，省 89-97% token
})
content = resp.json()["choices"][0]["message"]["content"]
```

本仓已封装好的路径（优先用，别重写）：`src/finer/model_config.py` 的 `VisionModelRegistry`
已处理端点分流、`api-key` 头、`max_completion_tokens` 字段名、`thinking: disabled`、失败冷却。

---

## 1. 端点分流 —— 发错端点必得 401

MiMo 的 key 绑定不同 host，**发错必 401，且报错不会告诉你是端点问题**：

| key 前缀 | 必须用的 base_url |
|---|---|
| `tp-`（Token Plan 配额包） | `https://token-plan-cn.xiaomimimo.com/v1` |
| 其它（标准开放平台） | `https://api.xiaomimimo.com/v1` |

本仓 `model_config.py:_mimo_vision_base_url()` 按 key 前缀自动选择（只读前缀，不记录 key 值），
可用 `MIMO_VISION_BASE_URL` > `MIMO_BASE_URL` 覆盖。

**相关坑（已在代码里加了 warning）**：把 `FINER_LLM_BASE_URL` 指向 MiMo 却没设
`FINER_LLM_API_KEY_ENV=MIMO_API_KEY`，会把 DeepSeek 的 key 发给 MiMo → 401。

### 模型

| 模型 | 用途 | 备注 |
|---|---|---|
| `mimo-v2.5` | 主力（抽取/摘要/OCR/vision） | 本仓 F1 vision 固定用它，不做 provider fallback |
| `mimo-v2.5-pro` | 旗舰，1M 上下文 | 贵，仅长文档需要时用 |
| ~~`mimo-v2-omni`~~ | — | **实测 400 Unsupported model，不存在** |

---

## 2. ⚠️ 最重要：`thinking: disabled` —— 不关就是白烧 90% token

**mimo-v2.5 默认开启 reasoning**，隐藏思考 token 全额计入 `usage.completion_tokens`（你付费）。
传 `"thinking": {"type": "disabled"}` 可关闭。

**实测 A/B（2026-07-25，同 prompt / temperature=0）**：

| 任务 | 默认(思考开) | `thinking:disabled` | 节省 |
|---|---|---|---|
| 简单分类（判断评级） | out=185 tok / 7.9s | out=**6** tok / **2.2s** | **-97% token, 3.6× 快** |
| 复杂结构化抽取（1,803 字真实研报 → 6 字段 JSON） | out=1,310 tok / 50.0s | out=**140** tok / **5.6s** | **-89% token, 8.9× 快** |
| **长摘要生成**（2,400 字深摘要，n=10 批量实测） | out=2,462 tok | out=**1,503** tok | **仅 -39%** |

⚠️ **节省幅度取决于「真实输出有多长」，不是任务复杂度。** 上表第三行是关键反例：
深摘要的输出本身就是 1,500 token 的真实内容，思考只占小头，所以只省 39%。
**输出越短，省得越多**（抽取类输出几十 token → 思考占 90%+）。
估算新作业成本时按这条规律推，别照抄 89-97%。

**质量对照（复杂任务）**：`ticker` / `rating_current` / `target_price`（850000 KRW）三项**完全一致**；
`rating_action` 关思考后反而**更准**（`maintain` vs 开思考的 `unknown`）；`key_thesis` 关思考版更详实
（多提到了 SOTP 估值方法）。

**结论与纪律**：
- 结构化抽取、分类、OCR、摘要 → **默认关闭 thinking**。上述 8.89 亿 token 的烧录**全程没关**，
  抽取类任务（T3/T6/T7/T9，输出短）的浪费尤其大；摘要类（T5/T8，输出长）浪费约 39%。
- **质量实测**：深摘要关闭 thinking 后 10/10 结构完整（八小节齐全）、数据翔实，
  字数中位 2,843 → 2,374（-16%，仍在 1500-2500 目标区间）。结构化抽取见上表，关键字段一致。
- 需要多步推理的任务（复杂因果链、数学）→ 保留 thinking，但**必须先用自己的 gold set 做 A/B**
  再决定，别照搬本表（本表 n=2，只证明"结构化任务关掉不掉质量"，不证明"所有任务都能关"）。
- 关闭 thinking 后 `max_completion_tokens` 可以从 6000+ 降到 1000-2000（§3 的陷阱随之消失）。

---

## 3. `max_completion_tokens` 陷阱（thinking 开启时）

两个独立的坑：

1. **字段名**：MiMo 用 `max_completion_tokens`，**不是** `max_tokens`。传错会被忽略 → 用默认值。
2. **数值**（仅当 thinking 未关闭）：思考 token 计入该预算。给小了 → 思考吃光额度 →
   **`content` 返回空串，HTTP 200，不报错**。症状：解析失败率飙升 + `tokens_out` 精确钉在你设的上限值。

**实测分级（thinking 开启时的安全值）**：

| 任务类型 | 最小安全值 | 实测依据 |
|---|---|---|
| 结构化抽取（T3 评级/目标价） | **6000** | 1600 时 content 全空；有效输出仅 800-1600，思考占大头 |
| 深度抽取（T6 estimates 多字段） | **10000** | 6000 时实测截断（校准 id=4392） |
| 长摘要（T8 1500-2500 字） | **12000** | 输出长 + 思考重 |

**关掉 thinking 后这一节基本作废**——直接按实际输出长度给 1.5 倍即可。

---

## 4. 429 有三种含义，判据不同 —— 这是最容易误判的地方

| 现象 | 真实含义 | 正确处置 |
|---|---|---|
| 高并发下零散 429，退避后恢复 | **RPM 突发限流** | 指数退避重试（2/4/8/16/30s），别停 |
| 连续 429，但每轮仍有新记录产出 | 同上，只是打得比较狠 | 降并发继续 |
| **单请求**（并发=1、间隔 10s）仍 429，body 含 `"type":"limitation"` | **当期配额窗口耗尽** | **等下一个窗口，不要放弃** |
| 401 / 402 | 真的 key 失效/欠费 | 停手 |

**关键实测（2026-07-24）**：MiMo Token Plan 是**滚动窗口配额，约 70 分钟一个周期**。
00:28 四条车道 44 秒内同步熔断（当时误判为"key 死亡"），**01:38 探针即恢复 200**，
key 又持续正常工作了 12+ 小时。

**判据纪律**：只有**单请求跨越 >100 分钟（超过一个完整窗口周期）持续非 200**，才能判定真死。
在此之前的所有 429 都应该"等下一个窗口"而非收工。

推荐的存活探针（低成本，不污染批量作业）：

```python
r = requests.post(URL, json={"model":"mimo-v2.5",
    "messages":[{"role":"user","content":"ok"}],
    "max_completion_tokens":2000, "thinking":{"type":"disabled"}},
    headers=H, timeout=60)
alive = (r.status_code == 200)
```

---

## 5. 并发与吞吐实测

| 场景 | 安全并发 | 实测吞吐 |
|---|---|---|
| 纯文本抽取（单进程） | **16–32**（64 也测过零 429） | 单车道 15–18M token/h |
| 多进程并行（5 车道，总线程 ~110） | 靠 429 退避自动调度到服务端上限 | **24M token/h**（1.6× 单车道） |
| 图片 OCR（vision） | **2–3** | ~10–20s/图 |

**vision 并发必须压到 2-3**：实测 concurrency=4 在批量 OCR 时触发限流，导致 **71 张图静默降级**
成 fallback 占位块（仍标记 `ok`/`canonical=True`，37% 污染率）。见 §7 质量门控。

**短调用比长调用更容易触发限流**：请求率而非 token 量是 RPM 的分母。
T7（每份 2 次 ~20s 短调用）的限流频率是 T6（60s 长调用）的 3-4 倍。

---

## 6. 批量作业工程骨架（现成可复用，别重写）

**位置**：`/Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/tools/`
（`t_burn_runner.py` = 通用并发骨架；`t5`–`t9` 系列 = 各类抽取任务的实现范例）

必备的六件套，缺一个都会在长时作业中出事：

1. **断点续传（幂等）** — 输出 JSONL 里 `validation.json_ok=true` 的 id 跳过，false 的重做。
   重跑同一条命令即续接。半截行（进程被杀）解析失败即忽略 → 该条自动重做。
2. **QuotaGuard 熔断** — 401/402/429 连续 N 次（重并发下设 30，单车道设 15）→ 优雅退出 `exit 3`
   并打印续跑命令。**注意**：熔断只是"本轮停"，不等于 key 死（见 §4）。
3. **预算硬顶** — `--budget` 限制 LLM 调用次数，超顶抛 `BudgetExceeded` 停止。
4. **单写者 JSONL + flush** — 并发 worker 写同一文件必须过锁，逐行 append + flush，
   保证被 kill 时最多损失一行。
5. **单份失败不杀全局** — worker 捕获所有异常返回状态码，绝不向上抛。
6. **三层 JSON 解析** — ①剥 markdown 围栏 ②直接 `json.loads` ③取首 `{` 到末 `}` 子串；
   全失败则用"严令重试"再要一次（`parse_json_object()` 已实现）。

**并行多任务时**：不同任务写**不同输出文件**即可零冲突；同一文件的家族依赖（如五票依赖三票完整）
用车道内串行解决。池子分片（按年份/按 id 段）是安全的并行切法。

---

## 7. 质量门控 —— MiMo 有三类静默失败

**这三类都返回 HTTP 200 且下游校验会通过，不加门控就是数据污染**：

1. **空 content**（thinking 吃光 max_tokens，§3）— 判据：`content` 为空 + `tokens_out` 等于上限值。
2. **内容审核 refusal** — 模型返回"我不能处理这个请求"之类的文本，被当成 OCR 结果存下来。
   实测**偶发**（同一张图重试即成功），不是稳定误杀。
3. **幻觉占位符** — 图表类内容会编造 `via.placeholder.com` 之类的假 URL。

本仓已有单一真相源：`src/finer/parsing/ocr_quality.py` 的 `gate_vision_output()`
（adapter 源头 + audit/runner 复用）。**vision 新代码必须过这个门**，别自己写。

**第四类坑（调用方自己造成的）**：脚本漏 `load_dotenv()` → 没有 key → 走 fallback 占位块，
但仍标记 `canonical=True` **伪成功**。任何 MiMo 调用路径都要有 `None` 守卫。

**OCR 准确率参照（gold set 实测，7 张投研截图 / 219 个数字）**：
recall **97.3%**，5 张财务表格 **100%**（含会计括号负数 `(1,177,201)`），**零幻觉数字**。
已知弱项：图表轴刻度、边角文字。结论：文本/表格数字可用，图表数据提取不可信。

---

## 8. 运维教训（血泪，别重蹈）

1. **长时作业的产物和唯一副本工具，绝不能只存在 `/tmp`。**
   实测事故：macOS `/tmp` 清理 + 磁盘 95% 满，删掉了工作镜像里 4GB 的 `reports.db` 和
   多个 `rag_system/` 模块，烧录静默中断 6.5 小时。产物侥幸幸存，抢救到了外置盘。
2. **监视器必须区分 `rc=1`（进程崩溃）和 `rc=3`（限流/配额）。**
   同一事故中，`rc=1` 被当成正常轮次不断重试，空转刷屏到兜底时间才退出。
   `rc=1` 应当**立即停止并报错**，因为重试不会自愈。
3. **`.env` 里含特殊字符的值必须加引号。**
   实测：`BBDOWN_COOKIE=` 值含 `;` `(` `|` 未加引号 → `source .env` 在该行 syntax error 中断，
   **其后所有变量都不加载**（包括 launchd wrapper 依赖的 key）。
4. **key 只从 600 权限的 env 文件读**，不写进命令行（会出现在 `ps` 里）、不写日志、不进 commit。
5. **bash 3.2（macOS 默认）不支持 `declare -A`**，配 `set -u` 会启动即死。
   用 `eval "V_$k=..."` / `eval "echo \${V_$k:-0}"` 替代。

---

## 9. 成本参照表（thinking 开启状态下的实测中位数）

用于估算新批量作业的规模。**关闭 thinking 后 out 部分可按 §2 打 1-2 折**。

| 任务 | 单份 in | 单份 out | 单份合计 | 延迟 |
|---|---|---|---|---|
| T3 结构化抽取（4k 字符切片） | ~2.5k | ~1.4k | **3.9k** | 24s |
| T5 短摘要（900 字，10k+2k 切片） | 4.0k | 1.0k | **5.3k** | 14s |
| T6 深度抽取（10k+4k 切片，多字段） | 5.0k | 4.2k | **11.5k** | 64s |
| T7 共识复核（2 次调用/份） | 5.4k | 1.4k | **7.2k** | 20s |
| T8 深摘要（2500 字，16k+4k 切片） | 5.0k | 2.4k | **8.7k** | 30s |
| T9 行业深抽（10k 切片） | 3.4k | 3.1k | **6.8k** | 35s |
| T2 图片 OCR（vision） | — | — | **~72k** | 10-20s |

---

## 10. 已有资产与真相源

| 内容 | 位置 |
|---|---|
| 本仓 MiMo 模型注册表（端点分流/头/字段名/冷却） | `src/finer/model_config.py` |
| vision OCR 质量门控（单一真相源） | `src/finer/parsing/ocr_quality.py` |
| OCR 429 退避重试实现 | `src/finer/parsing/image_ocr_standardizer.py` |
| 批量烧录骨架 + 6 类抽取任务实现 | `/Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/tools/` |
| 8.89 亿 token 的抽取产物（103,832 条） | 同上 `../products/`（含 README） |
| 烧录全程编排脚本与日志 | 同上 `../chain_logs/` |
| 烧录轮次完整记录与事故复盘 | `docs/specs/2026-07-21-mimo-token-burn-finale.md` |

---

## 附：新建 MiMo 批量作业检查清单

- [ ] key 从环境变量读，端点按前缀选对（§1）
- [ ] `max_completion_tokens`（字段名对）+ `thinking:{"type":"disabled"}`（§2）
- [ ] 先跑 20-30 份校准，人工核对 2-3 条输出，再放量（本轮每个任务都这么做，抓出过 max_tokens 截断）
- [ ] 断点续传 + QuotaGuard + 预算硬顶 + 单写者写入（§6）
- [ ] 输出**不要**落在 `/tmp`（§8.1）
- [ ] 429 判据写对：别把限流当 key 死（§4）
- [ ] vision 任务过 `gate_vision_output()`，并发压到 2-3（§5、§7）
