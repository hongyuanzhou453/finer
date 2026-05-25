# Vibe Agent Operating Model

> Status: draft
> Scope: 通用 multi-agent / vibe-coding 工作流
> Reference case: Finer OS 的 F-stage、Line V、任务卡和架构锁实践

## 1. 核心结论

vibe-coding 不能按“最低成本优先”来调度 Agent。

更稳的通用策略是：

```text
能力强的模型先决定方向
中强模型拆解和审查
低成本模型在任务卡边界内批量执行
自动化测试和人工验收负责最终事实判断
```

换句话说：

```text
架构阶段能力优先
执行阶段成本优先
验收阶段可靠性优先
```

强模型不应该一上来写大量代码；它应该先完成高杠杆决策：项目目标、架构边界、风险点、任务拆解和禁止事项。低成本模型只有在边界清晰时才适合批量执行。

## 2. 适用范围

本文档适用于以下项目：

- 前端应用
- 后端服务
- 数据处理项目
- AI / LLM 应用
- 自动化脚本项目
- 科研或知识管理项目
- 多 Agent 并行开发项目

它不绑定某一个仓库。Finer OS 只是参考案例：Finer 的经验是用 `AGENTS.md`、架构契约、Line V 验证和任务卡把多个 Agent 收束在可审计边界内。

## 3. 基本原则

### 3.1 规则先行

任何项目在让 Agent 写代码前，必须先明确项目规则。

推荐最小文档集：

```text
AGENTS.md
docs/architecture_lock.md
docs/agent_task_template.md
docs/verification_plan.md
```

如果项目已经有自己的规范文件，可以复用现有文件，不必机械新增同名文档。关键是必须存在以下信息：

- 项目目标
- 技术栈
- 目录结构
- 架构边界
- 允许修改区域
- 禁止修改区域
- 验证命令
- 红线操作

### 3.2 架构先行

不要让低成本模型直接从开放式需求开始写代码。

错误流程：

```text
DeepSeek 直接开始写代码
↓
越写越偏
↓
Claude / GPT 后期救火
```

推荐流程：

```text
Claude / GPT 先锁定方向
↓
GPT 把架构拆成任务卡
↓
DeepSeek 在边界内执行
↓
Gemini / GPT 做审查
↓
Claude 处理高风险问题
```

### 3.3 任务卡驱动

低成本模型只适合执行边界清晰的任务卡，不适合处理开放式架构问题。

不要给低成本模型这种任务：

```text
帮我优化整个项目架构。
```

应该给：

```text
只修改 components/UserCard.tsx。
参考 components/Button.tsx 和 components/Avatar.tsx。
不得新增依赖。
不得修改 API。
完成后运行 npm test。
```

### 3.4 风险分级路由

模型选择应由任务风险决定，而不是由单价决定。

```text
高返工风险任务用强模型
低返工风险任务用低成本模型
可自动验证任务优先交给执行层
不可自动验证任务必须加强审查
```

### 3.5 验证优先

Agent 自述“完成”不算完成。完成必须由以下证据支持：

- 测试结果
- 构建结果
- 类型检查
- lint
- diff 审查
- 产物截图或快照
- schema / contract 验证

没有验证命令的任务卡是不完整的。

## 4. 推荐工作流

完整流程：

```text
0. 项目规则初始化
   ↓
1. 只读理解项目
   ↓
2. 架构方案 / 技术路线
   ↓
3. 反方审查 / 压缩方案
   ↓
4. 生成架构锁
   ↓
5. 拆成任务卡
   ↓
6. 低成本 Agent 执行
   ↓
7. 低成本初审
   ↓
8. 高可靠终审
   ↓
9. 高风险问题交给强模型
   ↓
10. 验证、提交、沉淀规则
```

精简流程：

```text
Claude / GPT 定架构
GPT 拆任务
DeepSeek 执行
Gemini 初审
GPT 终审
Claude 攻坚
测试 / CI 裁决
```

## 5. 项目规则文件

### 5.1 `AGENTS.md`

项目最高规则入口。

应包含：

- 项目定位
- 技术栈
- 架构边界
- 目录 ownership
- 禁止事项
- 验证命令
- 红线操作
- Agent 沟通和交付格式

所有 Agent 进入项目后必须先读 `AGENTS.md`。

### 5.2 `docs/architecture_lock.md`

记录当前已确认的架构决策。

应包含：

- 当前采用的架构
- 技术栈
- 目录结构
- 状态管理方式
- 数据流
- API / schema contract
- 不允许普通 Agent 修改的区域
- 需要强模型或人工确认的区域

注意：如果项目已有更权威的架构文件，`architecture_lock.md` 可以只做索引，不重复定义规则。

### 5.3 `docs/agent_task_template.md`

任务卡模板。

用于把开放式需求转成低成本模型可执行的小任务。

### 5.4 `docs/verification_plan.md`

记录不同类型任务的验证命令。

示例：

```text
前端 UI 修改:
- npm run lint
- npm run build
- Playwright screenshot

后端 API 修改:
- pytest tests/api -q
- mypy / pyright
- contract tests

schema 修改:
- backend schema tests
- frontend type sync
- serialization roundtrip tests
```

## 6. Agent 身份卡

每个 Agent 开工前必须声明身份。

模板：

```text
Agent Identity

- Agent source: Claude Code / Codex / DeepSeek / Gemini / Cursor / Other
- Model:
- Role: Architect / Task Planner / Implementer / Reviewer / Auditor / Orchestrator
- Project area:
- Risk level: R0 / R1 / R2 / R3 / R4
- Input:
- Output:
- Allowed files:
- Forbidden files:
- Can edit code: yes/no
- Can edit tests: yes/no
- Can edit architecture: yes/no
- Can change contracts: yes/no
- Required verification:
- Stop conditions:
```

最重要的问题：

```text
我是谁？
我负责什么？
我不能碰什么？
我完成后怎么证明？
失败时谁接手？
```

没有身份卡，不允许进入实现阶段。

## 7. 模型和 Agent 来源分工

### 7.1 Claude / Claude Code

定位：

```text
首席架构师 + 高难度攻坚手
```

适合：

- 项目架构设计
- 大代码库理解
- 跨文件重构
- 核心数据流设计
- 状态管理设计
- 权限系统设计
- 复杂 bug 定位
- 高风险合并前审查

不适合：

- 大量重复组件
- 机械改名
- 简单文档搬运
- 低风险批量测试补齐

使用原则：

```text
Claude 先定方向，少做体力活。
```

### 7.2 GPT / Codex

定位：

```text
技术总控 + 任务编译器 + 实现审查员
```

适合：

- 方案反方审查
- 压缩过度设计
- 任务拆解
- 任务卡生成
- diff review
- 测试设计
- 自动化验证
- 局部工程实现

不适合：

- 在没有架构锁时直接大范围开工
- 长时间无边界探索

使用原则：

```text
GPT 负责把“方向”编译成“可执行任务”。
```

### 7.3 DeepSeek

定位：

```text
低成本执行层
```

适合：

- 单文件实现
- 单个组件
- 类型定义
- mock 数据
- 文档补充
- 单元测试
- 样式微调
- 重复性重构
- 低风险 bug 修复

不适合：

- 架构设计
- schema / contract 变更
- 数据库设计
- 权限系统
- 跨模块状态流
- 核心业务 pipeline
- 高风险重构

使用原则：

```text
DeepSeek 只能在任务卡内执行，不应该自由探索架构。
```

### 7.4 Gemini

定位：

```text
低成本审计员 / 初筛员
```

适合：

- 大上下文只读扫描
- 文档一致性检查
- UI 截图初审
- 明显 bug 检查
- 规范符合度检查
- mock / deprecated / TODO 扫描

不适合：

- 高风险代码落地
- 核心业务逻辑重构
- 最终架构裁决

使用原则：

```text
Gemini 适合发现明显问题，不负责最终结构性决策。
```

### 7.5 本地脚本 / 测试 / CI

定位：

```text
事实层裁判
```

适合：

- lint
- typecheck
- unit test
- integration test
- build
- snapshot
- schema validation
- contract test

使用原则：

```text
Agent 说完成不算，验证产物说完成才算。
```

## 8. 风险分级

### R0: 只读任务

例子：

- 阅读项目
- 总结架构
- 找风险
- 跑测试
- 扫描 deprecated code
- 审查 diff

推荐模型：

```text
Gemini / GPT / Claude
```

规则：

- 不允许编辑文件
- 不允许删除文件
- 不允许 stage / commit / push
- 只能输出报告

### R1: 低风险任务

例子：

- 单个组件
- 单个工具函数
- 类型补充
- 文档补充
- mock 数据
- 单元测试
- 样式微调

推荐模型：

```text
DeepSeek 执行
Gemini 初审
GPT 终审
```

规则：

- 必须有明确 allowed files
- 必须有验证命令
- 不允许修改架构锁
- 不允许新增依赖

### R2: 中风险任务

例子：

- 2 到 5 个文件
- 一个 API route
- 一个页面
- 一个小模块
- 在已有模式下扩展功能

推荐模型：

```text
GPT 拆任务
DeepSeek 执行
GPT 审查
Claude 只处理异常
```

规则：

- 必须拆成子任务
- 必须声明共享文件
- 必须有回滚策略
- 必须跑 targeted tests

### R3: 高风险任务

例子：

- 架构调整
- schema 变更
- 数据流变更
- 状态管理变更
- 数据库设计
- 权限系统
- 跨模块重构
- 核心业务 pipeline
- 前后端 contract 变化

推荐模型：

```text
Claude / GPT 设计
GPT 生成任务卡
Claude 或 Codex 实现关键部分
DeepSeek 只做外围子任务
GPT / Claude 终审
```

规则：

- 先设计，后实现
- 先锁 contract，再并行
- 必须有审查 Agent
- 必须有完整验证计划

### R4: 红线任务

例子：

- 删除文件或目录
- 数据库 schema 变更
- 数据迁移
- 改 `.env`
- 改密钥、token、CI/CD
- `git push`
- `git rebase`
- `git reset --hard`
- 强制推送
- 生产部署
- 公开发布

规则：

```text
必须先获得人工确认。
```

## 9. 通用任务卡模板

```text
# Agent Task Card

## Identity
- Role:
- Recommended model:
- Risk level:
- Project area:

## Goal
一句话说明要完成什么。

## Context
必须阅读的文件：
- ...

## Allowed Files
只允许修改：
- ...

## Forbidden Files
禁止修改：
- ...

## Input Contract
输入是什么。

## Output Contract
输出是什么。

## Steps
1. ...
2. ...
3. ...

## Acceptance Criteria
- ...
- ...

## Verification Commands
```bash
...
```

## Stop Conditions
遇到以下情况立刻停止：
- 需要改架构
- 需要新增依赖
- 需要改数据库
- 需要修改 forbidden files
- 测试失败但原因不明
- 发现任务卡边界不够
```

## 10. 架构锁模板

```text
# Architecture Lock

## Project Goal
这个项目最终解决什么问题。

## Core Users
谁使用这个系统。

## MVP Scope
当前阶段必须做什么。

## Out Of Scope
当前阶段明确不做什么。

## Tech Stack
- Frontend:
- Backend:
- Storage:
- Runtime:
- External services:

## Directory Ownership
| Directory | Owner | Rule |
|---|---|---|
| ... | ... | ... |

## Data Flow
数据从哪里来，经过哪些层，最后到哪里。

## State Management
状态放在哪里，谁可以修改。

## API / Contract Rules
哪些 schema 或 API 是真相源。

## Component / Module Boundaries
哪些模块可以互相调用，哪些不可以。

## Forbidden Changes
1. 不允许普通执行 Agent 修改架构锁。
2. 不允许随意新增依赖。
3. 不允许绕过既有 API 封装。
4. 不允许跨模块直接调用内部实现。
5. 不允许为了测试通过删除或绕过错误。

## High Risk Areas
必须由强模型或人工确认的区域。

## Verification
每类修改需要运行什么命令。
```

## 11. 审查流程

### 11.1 初审

适合 Gemini 或低成本 GPT。

检查：

- 是否遵守任务卡
- 是否修改 forbidden files
- 是否存在明显 mock / hardcoded / TODO
- 文档和实现是否一致
- UI 是否明显错位
- 测试是否运行

### 11.2 终审

适合 GPT / Claude。

检查：

- 架构方向是否正确
- diff 是否过大
- contract 是否漂移
- 是否引入长期技术债
- 测试是否证明真实路径
- 是否需要拆分提交

### 11.3 独立审计

适合高风险项目或多 Agent 并行后。

检查：

- Agent 是否越界
- 架构锁是否被破坏
- 任务卡是否和结果一致
- 是否有局部成功但整体方向错误的问题
- 是否应该继续、修改、暂停或阻断

## 12. 成本和效果平衡

不要把成本理解成单次调用价格。

真实成本包括：

```text
模型成本 = token 单价 × 上下文长度 × 往返次数
返工成本 = 架构错误概率 × 修复复杂度 × 下游影响面
验证成本 = 发现问题所需的人力和机器时间
```

真正省钱的做法：

```text
高返工风险任务先用强模型
低返工风险任务交给低成本模型
可自动验证任务优先批量化
不可自动验证任务提高审查强度
```

推荐预算分配：

| 阶段 | 成本占比 | 推荐模型 |
|---|---:|---|
| 项目理解 | 10% | Gemini / Claude |
| 架构设计 | 15% | Claude |
| 反方审查 | 5% | GPT |
| 任务拆解 | 5% | GPT |
| 批量实现 | 45%-55% | DeepSeek |
| 初步审查 | 5%-10% | Gemini |
| 终审 / 攻坚 | 10%-15% | GPT / Claude |

## 13. 多 Agent 并行规则

多 Agent 并行前必须满足：

- 架构锁存在
- 任务卡存在
- allowed files 不重叠，或已有串行顺序
- shared contract 已冻结
- 验证计划存在
- 当前工作区状态清楚

推荐并行前先跑只读 baseline：

```text
Line V / Verification Snapshot
```

只读 baseline 应报告：

- 当前分支
- 当前 HEAD
- dirty worktree
- 测试状态
- 构建状态
- 已知 legacy / mock / deprecated 缺口
- Agent ownership 冲突

并行实现时：

- 一个实现 Agent 只拥有一个明确模块、一个 feature surface 或一个 stage。
- 共享文件必须串行修改。
- 实现 Agent 不得顺手修 unrelated bug。
- 审查 Agent 默认只读。
- 合并前必须跑回归验证。

## 14. 失败处理

如果低成本模型失败，不要继续加同类 prompt 硬冲。

失败分流：

| 失败类型 | 处理 |
|---|---|
| 任务卡边界不清 | GPT 重新拆任务 |
| 架构理解错误 | Claude / GPT 重新审查方案 |
| 测试失败但原因明确 | DeepSeek 可继续修 |
| 测试失败且原因不明 | GPT / Claude 接手 |
| 触及 forbidden files | 立即停止并审查 |
| 需要新增依赖 | 暂停，人工确认 |
| 需要迁移 / 删除 / 发布 | 暂停，人工确认 |

## 15. 从 Finer OS 泛化出的经验

Finer OS 的实践可以抽象成以下通用模式：

| Finer 实践 | 通用含义 |
|---|---|
| `AGENTS.md` | 项目级 Agent 宪法 |
| F0-F8 stage | 明确架构分层和 ownership |
| `docs/specs/*` | contract 和任务边界 |
| Line V | 只读 baseline / verification gate |
| Agent task cards | 把开放式需求变成可执行任务 |
| Forbidden files | 防止 Agent 越界 |
| Acceptance commands | 用验证产物定义完成 |
| Independent auditor | 防止局部进展偏离总体架构 |

这些实践可以迁移到任何项目。关键不是使用 F0-F8 这个名字，而是建立同样的约束：

```text
每个 Agent 都知道自己是谁
每个任务都有明确边界
每个架构决策都有锁
每个完成状态都有验证
每个高风险操作都需要人工确认
```

## 16. 最小可执行版本

如果项目很小，不需要完整体系，可以使用最小版：

```text
1. 写 AGENTS.md
2. 写 architecture_lock.md
3. 让 Claude / GPT 做只读架构判断
4. 让 GPT 生成 3 到 10 张任务卡
5. 让 DeepSeek 按任务卡执行
6. 让 Gemini 做初审
7. 让 GPT 做终审
8. 跑测试和构建
```

最小版也必须保留三条底线：

```text
没有规则不动手
没有任务卡不交给低成本模型
没有验证不算完成
```

