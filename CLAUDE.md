# Finer OS — 项目规范

## 项目定位

AI-native 投研自动化流水线：将 KOL 社交媒体内容转化为结构化、可回测、可审计的投资事件。

## 项目上下文

- **主语言**：Python（遵循 PEP 8，类型注解必须完整）
- **前端**：TypeScript（Next.js 16 + React 19 + TailwindCSS 4）
- **后端**：Python 3.11+ (FastAPI + Pydantic V2)
- **代码比例**：Python ~170 文件，TypeScript ~40 文件

---

## 1. 分层架构边界

六层流水线，每层职责严格隔离：

```
L0 (Intake)  → L1 (Enrichment) → L2 (Library) → L3 (Parsing) → L5 (Extraction) → L6 (Review) → L8 (Backtest)
```

### 层间调用规则

| 层 | 代码目录 | 职责 | 可调用 |
|---|---|---|---|
| L0 | `ingestion/` | 多源数据接入（飞书/B站/微信） | `services/llm.py`, `services/converter.py` |
| L1 | `enrichment/` | 话题拆分、实体抽取、市场数据融合 | `services/finance_skills_client.py`, `parsing/slang.py` |
| L3 | `parsing/` | OCR/ASR/文本解析、情绪标注 | `services/llm.py`, `parsing/slang.py` |
| L5 | `extraction/` | 投资事件提取、TradeAction 生成 | `services/llm.py`, `enrichment/market_context.py` |
| L6 | `api/routes/` | 人工审核、RLHF 反馈收集 | `services/`, `ml/` |

**禁止**：
- 跨层直接调用（如 `extraction/` 直接调 `ingestion/`）
- 在 API route 中写业务逻辑（route 只做参数解析和响应格式化，逻辑放 `services/`）
- `parsing/` 调 `extraction/`（解析层不依赖提取层）

**公共模块**（任何层可调用）：
- `services/llm.py` — LLM 统一调用
- `services/finance_skills_client.py` — 金融数据（带 TTL 缓存）
- `schemas/` — 数据契约
- `config.py`, `paths.py`, `manifests.py` — 配置与路径

---

## 2. Schema 即真相源

**唯一真相源**：`src/finer/schemas/` 下的 Pydantic 模型。

### 规则

- 数据结构变更**只改 Pydantic 模型**，不改 JSON Schema
- `/schemas/` 目录下的 JSON Schema 保留为文档参考，标注 `<!-- AUTO-GENERATED, DO NOT EDIT -->`
- 新增字段必须有 `Field(description=...)` 说明
- 前端 `contracts.ts` 必须与 Pydantic 模型字段名、类型一致

### 核心 Schema 依赖关系

```
ContentRecord (L0)
  └→ SegmentRecord (L3)
       └→ EventWithActions (L5)
            └→ EnrichedEventWithActions (L5+L1)
                 └→ TradeAction (全生命周期)
```

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
| 图像 OCR/图表分析 | Qwen-VL-Plus | Qwen-VL-Max |
| 结构化提取 (Instructor) | Qwen-Max | — |

模型注册表在 `model_config.py`，自动 fallback。

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

### L0-L8 层目录

```
data/L0_ingest/       ← ingestion/ 写入
data/L1_enrichment/   ← enrichment/ 写入
data/L1_inbox/        ← enrichment/ 写入（待处理队列）
data/L2_standardized/ ← 标准化后的内容
data/L3_aligned/      ← parsing/ 写入
data/L4_parsed/       ← parsing/ 写入
data/L5_candidate/    ← extraction/ 写入
data/L6_annotated/    ← review 流程写入
data/L7_model_results/ ← ml/ 写入
data/L8_metrics/      ← backtest 写入
```

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
| `.env` | API 密钥（GLM_API_KEY, DASHSCOPE_API_KEY） | 是 |
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

### 多 Agent 并行调试

涉及 **3+ 问题** 的复杂调试场景，使用并行 Agent 模式：

1. 每个 Agent 独立调查一个问题
2. 所有 Agent 完成后汇总发现
3. 统一应用修复，避免冲突
4. 并行数量控制在 3-4 个，避免超时

示例场景：
- 同时诊断 B站/微信/Trade Action/L4 层/摘要生成等多个问题
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
