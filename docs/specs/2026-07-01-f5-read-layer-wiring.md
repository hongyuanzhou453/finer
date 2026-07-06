# 任务卡：F5_executed → opinions 读层接线

> **✅ 已实现（2026-07-01，方案 A + review 加固）。** 验收全过：`_load_all_actions()` 0→58（分布 {trader_ji:52, sandbox:6}）；**索引整删后** `/timeline` 仍返回 58 条且与 `/meta` 一致；`rebuild_index` 12 文件→58 条 0 失败；`repo.load(id)` wrapper 内单取；TestClient `/timeline`/`/stats/summary` 端到端真实数据（topKols=[trader_ji×52, sandbox×6]）；pytest 全量 3003 passed 零回归。
>
> **对抗式 review（2 视角）发现并已修**：① must-fix——`/timeline` 主端点仍走 SQLite 索引轨而写路径从不建索引（我的首轮验证能过只因手动 rebuild 过），已统一到文件扫描轨 + 统一内存过滤（顺带修掉既存的 F6 单 KOL 过滤泄漏）；② extraction 写盘后现场 `index_trade_action` 保持缓存新鲜；③ `update_validation_status` 改为 单次读 + raw 原地只改两键（保未知字段、避开 to_dict 往返突变）+ tmp 文件 fsync + `os.replace` 原子替换 + 模块级写锁；④ `load()` 的 stale-index/损坏文件降级路径补 warning 日志；⑤ 修漏网调用点 `cli.py backtest-run`（原 strict + 不识别 wrapper，对 F5_executed 直接崩）。
>
> **review 提出、判为暂缓**（量级 58 条不构成问题）：文件扫描无缓存的性能（数据上千后需 TTL 缓存或回 DB 轨，openQuestions #1）；rebuild_index failed 计数不含 wrapper 内单条丢弃；TradeAction 无 extra='allow' 的 schema 演进兜底；orchestrator/kol.py 仍硬编码 L5/L6 旧目录（属 graduation plan 里 kol.py 接线卡的范围）。
>
> 实施改动文件：`schemas/trade_action.py`（from_dict lax）、`services/repository.py`（wrapper-aware/id-aware/原子写/F5 默认目录）、`api/routes/opinions.py`（三读点统一文件扫描轨）、`api/routes/extraction.py`（写后建索引）、`cli.py`（backtest-run wrapper 支持）。

> 触发：2026-07-01 P0-6 creator_id 回填后实证发现——即便 creator_id 全对，`opinions._load_all_actions()` 仍返回 0，dashboard 一条真实 F5 数据都读不出。这是所有 live 功能（可信度榜 / 市场情绪 / 时间线 / 谁对了）的真正第一道门，且**与 creator_id 无关、非回填引入**。

## piece

让 opinions/timeline 读层能真正加载 `data/F5_executed/` 里已落盘的 TradeAction。

## currentState（根因，均有 file:line + 实证）

两个叠加的既存 bug，导致 F5 数据无法被读层反序列化：

1. **反序列化撞 strict**：`TradeAction` 及全部子模型用 `ConfigDict(strict=True)`（trade_action.py:103/133/170/224/300/348/401/506/942）。落盘 JSON 把枚举/时间存成字符串（'bearish'/'close_long'/'2026-03-15T...'）。`TradeAction.from_dict`（trade_action.py:788）= `cls.model_validate(data)`（**无 strict=False**）→ 8 validation errors（`Input should be an instance of TradeDirection` 等）。实证：`model_validate(a, strict=False)` → OK（creator_id=trader_ji, dir=BULLISH）；默认 → FAIL。

2. **格式不匹配（数组包裹 vs 单条）**：`data/F5_executed/*_actions.json` 是包裹 `{source_file, extracted_at, model, actions:[...]}`（每文件多条）。但读层按"单文件单 action"设计：
   - `repo._load_from_file`（repository.py:150）= `TradeAction.from_dict(json.load(f))`，把**整个 wrapper** 当单条 → `source/target/direction Field required`（实证 flood）。
   - `_load_all_actions`（opinions.py:315-338）逐 DB record 取 `file_path`（=wrapper）→ `repo._load_from_file(wrapper)` → 必挂。
   - `_load_actions_from_dir`（opinions.py:215）+ opinions.py:599 只 glob `**/*.action.json`（单数），**不匹配** `*_actions.json`（复数）。
   - **CLAUDE.md §5 文档约定**：TradeAction 落盘应为**单条** `{ticker}_{timestamp}.action.json`。现有 `_actions.json` 数组包裹是**写侧偏离文档契约**——读层没错，写层跑偏了。

实证现状：cache DB（回填后）已有 58 行正确 creator_id（trader_ji×52/sandbox×6），但 `_load_all_actions()` 仍 = 0，因为它重建全 action 时对每个 wrapper file 反序列化失败。

## gap

读层能把 `F5_executed/` 的数组包裹 + 字符串枚举 JSON 反序列化成 `List[TradeAction]`，dedup 后交给 opinions/timeline/stats。

## 三个修法 + 权衡

| 方案 | 做法 | 红线 | 评价 |
|---|---|---|---|
| **A 读层加固（推荐）** | (a) `from_dict` 改 `strict=False`；(b) 新增 wrapper-aware `load_actions_from_file(path)->List`；(c) `_load_all_actions`/`_load_actions_from_dir` 改为直接扫 `F5_executed/` 两种 pattern、flatten、dedup | **无**（纯读侧，不改 schema/DB/数据） | ✅ 立即可用、可逆、最小面。**首选** |
| B DB 直读 | opinions 不重建全 action，直接用 DB 列拼 TimelineOpinion | 🔴 需扩 SQLite 表列（company_name/backtest/evidence/action_chain/rlhf 均不在现有列） | ❌ 触发 DB schema 变更红线，且信息不全 |
| C 写层归一 + 迁移 | F5 writer 改写单条 `.action.json` + 迁移现有数组 | 🔴 批量重建 | 长期卫生（对齐文档契约），但不作即时修；且不改 strict 仍读不了 |

**推荐 A 先做（解锁 dashboard），C 作为后续写层卫生**（把 F5 落盘对齐 CLAUDE.md §5 单条约定），届时读层的 wrapper 分支可退役。

## filesToTouch（方案 A）

- `src/finer/schemas/trade_action.py:788`（`from_dict` → `model_validate(data, strict=False)`）
- `src/finer/services/repository.py:150`（`_load_from_file` 增 wrapper 分支 / 或新增 `load_actions_from_file`）
- `src/finer/api/routes/opinions.py:315-338`（`_load_all_actions` 改直接扫文件 + flatten + dedup）
- `src/finer/api/routes/opinions.py:215, 599`（glob 增 `*_actions.json`）

## changes（方案 A）

1. `from_dict` 单行：`return cls.model_validate(data, strict=False)`。修所有持久化 JSON 的反序列化（含 F6 单条）。风险低——`from_dict` 语义就是"从落盘 dict 恢复"，宽松是对的；构造期仍 strict。
2. 新增 `load_actions_from_file(path) -> List[TradeAction]`：读 JSON，若含 `actions`(list) 则逐条 `from_dict`；否则当单条 `from_dict`；逐条 try/except 不整文件挂。
3. `_load_all_actions`：从"逐 DB record → `_load_from_file`(单条)"改为"glob `F5_executed/**/*_actions.json` + `**/*.action.json` → `load_actions_from_file` flatten → 按 trade_action_id dedup"。DB 仍作过滤/索引用（creator_id/ticker 查询），但全量重建走文件扫描。
4. `_load_actions_from_dir`（F6）：glob 增 `*_actions.json`，改用 `load_actions_from_file`。
5. （可选）`repo._load_from_file` 若仍被 `repo.load(id)` 用于按 id 取单条：wrapper 分支里按 id 在 array 中查找返回。

## contractImpact

- **不改 Pydantic schema、不改 API 响应结构、不改前端 contracts.ts**——纯读层修复，对外契约不变。
- 修好后 `/api/opinions/timeline`、`/stats/summary` 首次返回真实数据（trader_ji×52/sandbox×6）；前端 `creatorId` 分组即 handle（trader_ji），与 fixtures 同构，dashboard 直接点亮。
- 注意：`_load_all_actions` 全量文件扫描的性能（当前 58 条无虑；上千条时应回退到 DB 列查询 + 惰性加载，见 open questions）。

## risks

- `from_dict` 改 strict=False 后，历史脏数据（字段缺失/类型错）会被更宽容地接收——需保留逐条 try/except + 日志，避免坏数据静默混入。
- wrapper 与单条并存期，dedup 必须可靠（按 trade_action_id），否则同一 action 若既在数组又被单独落盘会重复计数。
- 若后续做 C（写层归一），读层双 pattern 分支要同步退役，避免长期两套格式。
- `_load_from_file` 若被其它调用方依赖"返回单条"语义，改动需回归（grep 调用点）。

## dependencies

- **无前置**——这是最底层的门，其它 live 卡（creator_id 已回填完成、opinions 五向、信誉分、异动）都在它之上。creator_id 回填已完成，此卡修好即可验证按 KOL 分组在真实数据上成立。

## effort

**S–M**（读层局部修 + 一个 helper + 4 处调用点；无 schema/DB/数据迁移）。

## acceptance

1. `python -c "import sys;sys.path.insert(0,'src');import finer.api.routes.opinions as o;print(len(o._load_all_actions()))"` → 58（非 0）。
2. `_load_all_actions()` 的 creator_id 分布 = {trader_ji:52, sandbox:6}。
3. 起后端，`GET /api/opinions/timeline` 返回非空，opinion.author/creatorId = 真实 handle。
4. dashboard `/demo/kol-radar`（切 live 数据源后）可信度榜出现 trader_ji 行、非单一 unknown 桶。
5. 回归：现有 opinions 相关测试 + `pytest tests/ -k opinion` 通过；F6 单条 `.action.json` 仍可加载。

## openQuestions

1. 全量文件扫描 vs DB 列查询：`_load_all_actions` 全扫在数据量大时不可持续。是否此卡就引入"DB 存全 action JSON blob 一列"或"惰性按需 load"，还是先 58 条能用、扩展性留给后续？
2. `sandbox` 6 条是否算真实 KOL（P1 规范化时可能剔除/合并），影响验收里是否期望它出现在榜上。
3. 是否同步排期 C（写层归一到单条 `.action.json`，对齐 CLAUDE.md §5），让读层 wrapper 分支有明确退役时点。
