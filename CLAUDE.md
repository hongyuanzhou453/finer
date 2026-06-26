# Finer OS — 项目规范

@AGENTS.md

## 项目定位

AI-native 投研自动化流水线：将 KOL 社交媒体内容转化为结构化、可回测、可审计的投资事件。

## 项目上下文

- **主语言**：Python（遵循 PEP 8，类型注解必须完整）
- **前端**：TypeScript（Next.js 16 + React 19 + TailwindCSS 4）
- **后端**：Python 3.11+ (FastAPI + Pydantic V2)
- **代码比例**：Python ~170 文件，TypeScript ~40 文件

---

## 0. 跨工具共享规范

OpenADE 作为多 Agent 管理器打开 Claude Code 时，Claude Code 不会自动加载 Codex 的 skill registry。反过来，Codex 也不会自动加载 Claude Code 的 agents/commands。需要两边共同遵守的规则必须沉淀到本仓库。

本仓库的共享入口：

- `AGENTS.md`：Codex / OpenAI agent 的项目入口，包含 F0-F8 架构边界与 Agent 执行规则。
- `CLAUDE.md`：Claude Code 的项目入口，包含工程纪律、验证命令与工作流规范。
- `src/finer_dashboard/AGENTS.md` 与 `src/finer_dashboard/CLAUDE.md`：前端目录级补充规则，只能收紧或补充根目录规范，不得放宽。
- `knowledge/okf/`：OKF derived knowledge layer（跨工具可读的架构知识导航；非运行时真值，契约见 `docs/specs/2026-06-26-okf-knowledge-bundle.md`）

执行规则：

- 在本仓库内工作时，任何 Agent 都必须遵守根目录 `AGENTS.md` 和 `CLAUDE.md`。
- 私有 skill/agent 只作为工具增强，不作为项目规范真相源。
- 如果 Codex skill、Claude Code agent/command 与项目文件冲突，以项目文件为准。
- 新增跨工具长期规则时，优先更新 `AGENTS.md` / `CLAUDE.md`，不要只写入某个客户端的私有目录。
- 能力层共享使用 Claude Code skills 机制：个人技能位于 `~/.claude/skills/<skill-name>/SKILL.md`。需要把 Codex / `~/.agents` skills 同步到 Claude Code 时，运行 `scripts/sync_claude_skills_from_codex.sh`；该脚本只新增缺失 skill，不覆盖已有同名 skill。

---

## 1. 分层架构边界

**Canonical pipeline: F0-F8。** 详见 `AGENTS.md` 和 `docs/ARCHITECTURE.md`。

旧命名 L0-L8 和 V0-V6 已废弃（deprecated），仅保留于 `docs/ARCHITECTURE.md` 第16章 Legacy Mapping 供迁移参考。

```
F0 (Intake) → F1 (Standardize) → F1.5 (Topic Assembly) → F2 (Anchor) → F3 (Intent) → F4 (Policy) → F5 (Execute) → F6 (Review) → F7 (Timeline) → F8 (Backtest)
```

### 层间调用规则

| F-stage | 代码目录 | 职责 | 可调用 |
|---------|----------|------|--------|
| F0 | `ingestion/` | 多源数据接入（飞书/B站/微信） | `services/llm.py`, `services/converter.py` |
| F1 | `parsing/` | 内容标准化：结构边界、standardization quality、provenance | `services/llm.py`, `services/perception.py` |
| F1.5 | `parsing/topic_assembler.py` | 长篇复杂内容主题组装（TopicBlock）；只处理语义边界 | `schemas/content_envelope.py`, `schemas/topic_block.py` |
| F2 | `enrichment/` | 实体锚定、质量评估、时间解析 | `services/finance_skills_client.py`, `entity_registry.py` |
| F3 | `extraction/intent_extractor.py` | 投资意图提取 | `services/llm.py` |
| F4 | `policy/` | Intent→TradeAction policy 映射 | 规则引擎（无 LLM） |
| F5 | `extraction/trade_action_extractor.py` | TradeAction 生成 | `services/llm.py`, `services/finance_skills_client.py` |
| F6 | `api/routes/` | 人工审核、RLHF 反馈收集 | `services/`, `ml/` |

**禁止**：
- 跨 F-stage 直接调用（如 F5 直接调 F1）
- 在 API route 中写业务逻辑（route 只做参数解析和响应格式化，逻辑放 `services/`）
- F3 生成 TradeAction（F3 职责止于 Intent）
- F5 不经过 F3/F4 直接从原始文本生成 TradeAction
- F1.5 解析 F1 原始格式细节（markdown heading、HTML wrapper、OCR bbox、ASR timestamp）
- 新 F1 代码输出 legacy `SegmentRecord` 作为 canonical 结果

**公共模块**（任何 F-stage 可调用）：
- `services/llm.py` — LLM 统一调用
- `services/finance_skills_client.py` — 金融数据（带 TTL 缓存）
- `schemas/` — 数据契约
- `config.py`, `paths.py`, `manifests.py` — 配置与路径

---

## 错误反馈系统 (Line F)

新建或改动的 API 错误必须使用 canonical error envelope（见 `src/finer/errors/`）。每个错误必须携带 `request_id`、`stage`、`operation`、`retryable`、`fix_hint`；F0 导入错误还必须携带 `source_channel`。

旧路由中尚未迁移的错误响应由 verification agent 报告并逐步收敛，不允许为了“一次性清零”做无边界全量迁移。

详见 `docs/specs/2026-05-parallel-agent-execution.md` Line F 章节。

---

## 2. Schema 即真相源

**唯一真相源**：`src/finer/schemas/` 下的 Pydantic 模型。

### 规则

- 数据结构变更**只改 Pydantic 模型**，不改 JSON Schema
- `/schemas/` 目录下的 JSON Schema 保留为文档参考，标注 `<!-- AUTO-GENERATED, DO NOT EDIT -->`
- 新增字段必须有 `Field(description=...)` 说明
- 前端 `contracts.ts` 必须与 Pydantic 模型字段名、类型一致

### 核心 Schema 依赖关系（F0-F8 Canonical）

```
ContentRecord (F0)
  └→ ContentEnvelope (F1)
       └→ ContentBlock + BlockQuality + BlockProvenance (F1)
            └→ TopicBlock / TopicAssemblyResult (F1.5)
                 └→ QualityCard + TemporalAnchor + EntityAnchor + EvidenceSpan (F2)
                      └→ NormalizedInvestmentIntent (F3)
                           └→ PolicyMappingResult (F4)
                                └→ TradeAction + ExecutionTiming (F5)
                                     └→ ViewpointState (F7) → BacktestResult (F8)
```

> 旧 L0/L3/L5 命名仅在 `pipeline/orchestrator.py`（legacy orchestrator）和 `data/` 目录结构中保留。Schema 定义、API 契约、文档均以 F-stage 为准。
> F1 标准化契约以 `docs/specs/f1-standardization-contract.md` 为准。旧 V0 block type、legacy `SegmentRecord`、L3 perception 只能作为迁移输入，不是新代码的 canonical output。
> F1.5 是 F1/F2 之间的 mandatory sub-stage，用于把长聊天、长文档等 multi-topic 内容组装为 `TopicBlock`，但不改变 F0-F8 顶层命名。规则版 TopicAssembler 只作为 baseline/fallback，主方向是 constrained LLM proposal + deterministic validator。

### 前后端契约同步

修改 Pydantic schema 后，**必须同步修改**：
1. `src/finer_dashboard/src/lib/contracts.ts` — TypeScript 类型定义
2. 相关 API route 的请求/响应模型
3. 前端组件中使用该类型的代码

---

## 3. API 路由规范

### 结构

- 路由文件放 `src/finer/api/routes/`
- 单文件不超过 **500 行**（当前 `files.py` 已超，需拆分）
- 每个路由模块导出 `router = APIRouter(prefix=..., tags=[...])`
- 在 `server.py` 中统一注册

### 响应格式

```python
# 成功
{"ok": true, "data": {...}}

# 错误
{"ok": false, "error": {"code": "NOT_FOUND", "message": "..."}}
```

### 路由拆分原则

- 按资源实体拆分（files、review、rlhf、extraction...）
- 同一资源的操作超过 8 个端点时，按操作类型拆子路由
- CRUD + 列表 = 一个文件；复杂业务流程（如 RLHF）独立文件

---

## 4. LLM 调用规范

### 模型选择

| 场景 | 主模型 | 降级模型 |
|---|---|---|
| 文本富化/分类 | GLM-5.1 (SVIPS) | Qwen-Plus (DashScope) |
| 图像 OCR/图表分析 | MiMo-V2.5 | — |
| 结构化提取 (Instructor) | Qwen-Max | — |

模型注册表在 `model_config.py`。F1 vision/OCR 当前固定为 `mimo-v2.5`，不启用视觉模型 fallback。

### Prompt 管理

- Prompt 模板写在**调用方模块内**，不单独抽文件
- 使用 Jinja2 模板（`jinja2` 已是依赖）或 f-string
- 复杂 prompt（如 DPO 训练模板）放 `ml/` 目录
- **禁止**在 prompt 中硬编码 API key 或敏感信息

### Instructor 使用

结构化输出必须用 `instructor` + Pydantic response model：

```python
from instructor import patch
client = patch(OpenAI(...))
result = client.chat.completions.create(
    model="qwen-max",
    response_model=MyPydanticModel,
    messages=[...]
)
```

---

## 5. 数据目录契约

### F0-F8 层目录

```
data/F0_intake/        ← ingestion/ 写入
data/F1_standardized/  ← parsing/ 写入（标准化后内容）
data/F2_anchored/      ← enrichment/ 写入
data/F3_intents/       ← extraction/ 写入（Intent）
data/F4_policy_mapped/ ← policy/ 写入
data/F5_executed/      ← extraction/ 写入（TradeAction）
data/F6_reviewed/      ← review 流程写入
data/F7_timeline/      ← timeline/ 写入
data/F8_metrics/       ← backtest 写入
```

> 当前磁盘目录仍为 L0-L8 命名，迁移映射详见 `docs/ARCHITECTURE.md` 第16章。

### 辅助目录

```
data/raw/              ← 原始文件，按 creator 组织
data/processed/        ← manifests, documents, transcripts
data/rlhf/             ← RLHF 反馈数据
data/cache/            ← 应用缓存，可安全清理
```

### 文件命名

- Content manifest: `{content_id}.manifest.json`
- Segment: `{content_id}_{segment_idx}.json`
- Event: `{content_id}_{event_idx}.event.json`
- TradeAction: `{ticker}_{timestamp}.action.json`

### Manifest 管理

- 每个内容必须有 `ContentManifest`
- manifests 索引懒加载，API 层用 TTL 缓存
- 修改 manifest 后必须更新索引

---

## 6. 测试规范

### 测试策略：关键路径强制

**必须有测试的模块**：
- `extraction/` — 事件提取核心逻辑
- `enrichment/` — 市场数据融合、情绪融合
- `parsing/` — 文本解析、slang 映射
- `schemas/` — Pydantic 模型序列化/反序列化
- `api/routes/` — API 端点基本可用性

**不要求测试的模块**：
- `ingestion/` — 依赖外部服务（飞书/B站），用 smoke test 覆盖
- `ml/` — 训练流程，手动验证
- `services/` — 外部 API 客户端，mock 测试可选

### 测试约定

- 测试文件放 `tests/`，命名 `test_{module}.py`
- 测试数据放 `tests/fixtures/`
- 使用 `pytest`，运行命令：`pytest tests/ -v`
- Mock 外部服务（LLM API、finance-skills），不 mock 内部逻辑
- Schema 测试覆盖：序列化、反序列化、字段校验、默认值

### 验证命令

```bash
# 后端
pytest tests/ -v

# 前端
cd src/finer_dashboard && npm run build

# 类型检查（如有配置）
cd src/finer_dashboard && npx tsc --noEmit
```

---

## 7. 配置管理

### 配置分层

| 文件 | 内容 | 是否 gitignore |
|---|---|---|
| `.env` | API 密钥（MIMO_API_KEY, GLM_API_KEY, DASHSCOPE_API_KEY） | 是 |
| `configs/*.yaml` | 服务配置（飞书、creator profiles） | 否（敏感字段用占位符） |
| `configs/*.yaml.example` | 配置模板 | 否 |
| `src/finer/config.py` | 配置加载器 | 否 |

### 规则

- 新增配置项先加到 `config.py` 的 dataclass，再写 YAML
- 敏感值（key、token、secret）只放 `.env`，代码中通过 `os.environ` 读取
- `configs/` 下的 YAML 可提交，但不含真实密钥

---

## 8. 工程纪律

### 代码风格

- Python: 遵循 PEP 8，类型注解必须完整
- TypeScript: 使用 ESLint（`npm run lint`）
- 命名：Python 用 snake_case，TypeScript 用 camelCase，Schema 字段用 snake_case

### Git 约定

- Commit message: `type(scope): description`
  - type: feat / fix / refactor / docs / test / chore
  - scope: ingestion / enrichment / extraction / api / dashboard / schemas / ml
- 不提交 `data/` 目录、`.env`、`__pycache__`、`.venv`

### 新增模块检查清单

1. 在对应层目录下创建模块
2. 定义 Pydantic schema（如涉及新数据结构）
3. 写 API route（如需前端访问）
4. 同步 `contracts.ts`（如涉及前端）
5. 补测试（如在关键路径上）
6. 更新 `config.py`（如有新配置项）

### 禁止事项

- 不注释掉报错代码来消除警告
- 不在代码中硬编码密钥、token
- 不在 API route 中写业务逻辑
- 不跳过分层直接跨层调用
- 不修改 JSON Schema（只改 Pydantic 模型）

---

## 9. 启动命令参考

```bash
# 安装（含行情数据可选依赖）
pip install -e '.[dev,market-data]'

# 后端 API
uvicorn finer.api.server:app --reload --port 8000

# 前端 Dashboard
cd src/finer_dashboard && npm run dev

# CLI
python -m finer.cli init-storage
python -m finer.cli feishu-sync

# 测试
pytest tests/ -v
```

---

## 10. 工作流规范

### 并行 Agent 执行规范

涉及多条任务线、多 Agent、或跨 3+ 模块的开发，必须先阅读并遵守：

```text
docs/specs/2026-05-parallel-agent-execution.md
```

每轮实现型并行任务启动前，必须先运行或读取 Line V 只读门控规范：

```text
docs/specs/2026-05-verification-snapshot-gate.md
```

Line V 的输出是当前仓库 baseline report；后续实现型 Agent 必须基于该报告声明 ownership、冲突文件和验证命令。

并行任务启动前必须声明：

1. parallel line（如 F0 Intake Repair、F3-F4-F5 Canonical Path、F8 Backtest）
2. 所属 F-stage
3. 输入 schema 与输出 schema
4. 允许修改文件
5. 禁止修改文件
6. 验收命令

强制规则：

- 一个实现型 Agent 只能拥有一个 F-stage、一个明确 frontend surface，或一个只读 verification 任务。
- Line V Verification Snapshot 是实现型并行任务的前置门控；它只能读文件、运行测试/build/rg/git diff，并输出 baseline report，不得修改任何文件。
- 共享 contract 先冻结，再允许下游并行；渠道 Agent 不得私自扩展 `ContentRecord`。
- 第一轮并行优先级：并行规范 -> ERR-0/ERR-1 错误反馈基础 -> A0 F0-Core -> A1 Project Memory contract -> A2 分渠道导入 -> A3 Import Console -> KOL Backtest MVP。
- F0 只输出 `ContentRecord`、raw archive、import receipt/status、F0 local index；不得做 OCR、topic assembly、entity/time anchor、intent、TradeAction、backtest。
- F0 Project Memory 以 raw 文件和 `ContentRecord`/manifest 为可重建依据，SQLite 只能作为热索引；Finer OS 启动默认不得递归扫描 raw 目录。
- 新增或修改 SQLite 表结构、旧数据迁移、批量重建、批量删除，必须先获得用户确认。
- F0 渠道导入按来源拆分为飞书、本地上传、NotebookLM、微信、B站；共享文件如 `integrations.py`、`contracts.ts` 必须单 agent 串行修改或先拆分 ownership。
- 新建或改动的错误响应必须使用 Line F canonical envelope；必须包含 `request_id`、`stage`、`operation`、`retryable`、`fix_hint`，F0 还必须包含 `source_channel`。
- 错误 details 禁止出现 token、secret、password、cookie、authorization、api_key。
- 新主链路不得依赖 legacy `TradeActionExtractor.extract_from_text()`；F5 canonical `TradeAction` 必须包含 `intent_id`、`policy_id`、`evidence_span_ids`、`execution_timing`。
- F0 Import Console 只能展示导入状态和项目内存健康状态，不得把“导入成功”显示为“解析成功”。
- F0 Import Console 必须展示错误码、request_id、retryable、fix_hint；不得展示原始 traceback、token、cookie 或 auth header。
- 多 Agent 并行写代码时优先使用独立 git worktree 或独立分支；不得让两个实现型 Agent 在同一工作目录修改重叠文件。
- Verification Agent 默认只读，只能读文件、运行命令、报告发现；不得顺手改业务代码。

### 多 Agent 并行调试

涉及 **3+ 问题** 的复杂调试场景，使用并行 Agent 模式：

1. 每个 Agent 独立调查一个问题
2. 所有 Agent 完成后汇总发现
3. 统一应用修复，避免冲突
4. 并行数量控制在 3-4 个，避免超时

示例场景：
- 同时诊断 B站/微信/Trade Action/F-stage 边界/摘要生成等多个问题
- 跨 10+ 文件的重构验证

### 会话启动检查

开始多文件操作前，确认工作目录正确：

```bash
# 确认在项目根目录
pwd  # 应为 /Users/zhouhongyuan/Desktop/finer
```

如果遇到目录问题，重启会话到正确位置。

### CLI 命令执行

CLI 命令（如 `claude mcp add`、`claude --version`）在**系统终端**执行，不要粘贴到 Claude 会话中。

---

## 11. 任务追踪

复杂多步骤工作使用 TaskCreate/TaskUpdate 追踪进度：

- 每个子任务独立创建
- 开始时标记 `in_progress`
- 完成后立即标记 `completed`
- 依赖关系用 `blockedBy` 声明

---

## 12. 大规模任务文档化

**触发条件**：单次任务耗时超过 10 分钟（累计处理、分析、修改时间），完成后必须产出结构化审阅文档。

### 文档命名与位置

```
docs/specs/{YYYY-MM-DD}-{任务简述-kebab-case}.md
```

任务简述例：`f-stage-migration`、`intent-extractor-rewrite`、`image-preview-fix`

### 文档结构要求

每个文档必须包含以下核心段：

1. **概述**（Overview）：一句话说清任务目标与结果
2. **变更清单**（Changes）：文件路径 + 变更类型（新增/修改/删除），用列表或表
3. **架构影响**（Architecture Impact）：说明对分层边界、数据流、API 契约的影响，引用受影响的 schema / route / contract
4. **关键决策**（Key Decisions）：本次做了什么选择、为什么（不一定要多，但要捕捉非显而易见的决策）
5. **验证结果**（Verification）：跑了什么命令、输出是什么、是否全部通过
6. **未解决项**（Open Issues）：本次未覆盖的已知缺口（如没有则写「无」）

### 引用规范

- 文件路径使用从项目根开始的相对路径：`src/finer/extraction/intent_extractor.py:142`
- Schema 引用：`schemas/contract.py:AssetFile`
- API 端点引用：`GET /api/files?tier=F1`
- 外部系统：用完整 URL（如 Grafana dashboard、Linear ticket）

### 反例（禁止）

- 只在聊天里口述结论性摘要，不落地为文件
- 写一个 README 式的浏览文档，不包含具体变更路径和验证输出
- 把聊天内容直接复制粘贴当文档
