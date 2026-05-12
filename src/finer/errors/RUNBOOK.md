# Finer 错误码 Runbook

> 本文档是错误码的运维参考手册。错误码定义在 `codes.py`，元数据在 `ERROR_CODE_DEFINITIONS`。
> 完整错误系统文档见 `README.md`。

---

## Line F: Error Feedback Foundation — 快速参考

新建或改动的错误路径必须返回 canonical error envelope，包含以下必填字段。历史路径由 verification agent 记录缺口并逐步迁移，不做无边界全量替换。

| 字段 | 说明 |
|------|------|
| request_id | 自动生成，贯穿请求生命周期 |
| stage | F0/F1/F2/.../F8/cross |
| operation | 操作标识（如 wechat_import） |
| retryable | 是否可重试 |
| fix_hint | 人类可读修复建议 |

可选字段：source_channel、content_id、import_run_id、external_source_id、exception_type。

details 中**禁止**出现：token、secret、password、cookie、authorization、api_key。

F0 错误码速查：

| Code | 含义 | retryable |
|------|------|-----------|
| F0_AUTH_001 | 认证/会话失效 | true |
| F0_EXT_001 | 外部服务不可达 | true |
| F0_EXT_002 | 外部返回异常数据 | false |
| F0_IO_001 | raw 文件写入失败 | true |
| F0_STATE_001 | cursor/session 状态异常 | true |
| F0_TMO_001 | 操作超时 | true |

完整规范见 `docs/specs/2026-05-parallel-agent-execution.md` Line F 章节。

### 第一轮任务拆分

| Task | 类型 | 允许范围 | 验收 |
|------|------|----------|------|
| ERR-0 | 契约/文档 | 并行规范、`CLAUDE.md`、错误系统文档 | 字段、敏感过滤、任务卡齐全 |
| ERR-1 | 后端薄层 | `src/finer/errors/` 和 `tests/test_errors.py` | `pytest tests/test_errors.py -q` |
| ERR-2 | F0 映射 | F0 routes/adapters 和对应测试 | F0 失败返回 code/request_id/stage/operation/source_channel/retryable/fix_hint |
| ERR-3 | 前端展示 | dashboard error contracts、api-client、Import Console | build/tsc 通过，UI 展示 code/request_id/retryable/fix_hint |
| ERR-4 | 只读验证 | 读文件和运行命令 | 报告 raw error、敏感字段、前端展示缺口 |

第一轮禁止新增错误历史库、生产数据迁移、SQLite schema 变更或观测平台。

---

## 错误码格式

```
{DOMAIN}_{CATEGORY}_{SEQUENCE}
```

- **DOMAIN**: SYS / API / F0-F8 / F15 / LLM / WX / BILI / FEISHU / NLM
- **CATEGORY**: IN / AUTH / PERM / NTF / CNF / STATE / RLM / SCHEMA / PARSE / POLICY / CFG / IO / INT / EXT / TMO

## 错误码查询 API

```
GET /api/system/error-codes
GET /api/system/error-codes?domain=F1
GET /api/system/error-codes?category=EXT
```

返回格式：
```json
{
  "ok": true,
  "data": {
    "codes": [
      {
        "code": "SYS_IN_001",
        "domain": "SYS",
        "category": "IN",
        "status_code": 400,
        "title": "Invalid input",
        "root_cause": "...",
        "fix_hint": "..."
      }
    ],
    "categories": ["IN", "AUTH", "PERM", ...]
  }
}
```

---

## 系统级错误码 (SYS)

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| SYS_IN_001 | 400 | 无效输入 | 请求参数缺失或格式错误 | 检查请求字段和必填标识符 |
| SYS_IN_002 | 422 | 请求校验失败 | FastAPI/Pydantic 拒绝请求体 | 检查 `details.errors`，对齐客户端与路由 schema |
| SYS_AUTH_001 | 401 | 认证失败 | 请求未提供有效凭证 | 提供有效的 X-API-Key 或 bearer token |
| SYS_AUTH_002 | 500 | 认证配置错误 | 认证已启用但未配置验证器 | 设置环境变量 API_KEY 或 JWT_SECRET |
| SYS_PERM_001 | 403 | 权限不足 | 已认证但无权执行操作 | 检查操作敏感性，提供二次认证 |
| SYS_NTF_001 | 404 | 资源不存在 | 请求的资源或路由目标不存在 | 检查标识符、路径和存储 |
| SYS_CNF_001 | 409 | 资源冲突 | 请求操作与当前状态冲突 | 刷新状态后用非冲突更新重试 |
| SYS_CFG_001 | 500 | 配置错误 | 运行时配置缺失或无效 | 检查 config.py、configs/*.yaml、环境变量 |
| SYS_IO_001 | 500 | 文件系统错误 | 读写操作失败 | 检查路径存在性、权限、数据目录契约 |
| SYS_STATE_001 | 409 | 系统状态无效 | 操作合法但当前状态不允许执行 | 检查当前状态，完成前置转换 |
| SYS_TMO_001 | 504 | 系统超时 | 本地或基础设施操作超时 | 增加超时或检查阻塞依赖 |
| SYS_INT_001 | 500 | 内部服务器错误 | 未预期的服务端错误 | 用 request_id 查日志，在源头加更精确的 FinerError |

## API 级错误码 (API)

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| API_IN_001 | 400 | 无效 API 请求 | API 路由收到不支持的请求格式 | 修正客户端请求或路由请求模型 |
| API_AUTH_001 | 401 | API 认证失败 | API 凭证校验失败 | 检查请求头和已配置凭证 |
| API_PERM_001 | 403 | API 权限不足 | 已认证但缺少 API 操作权限 | 检查路由级授权和敏感操作要求 |
| API_NTF_001 | 404 | API 资源不存在 | API 路由找不到请求的资源 | 验证资源 id 和存储索引 |
| API_STATE_001 | 409 | API 状态冲突 | API 请求与当前工作流状态冲突 | 刷新前端状态，用最新资源版本重试 |
| API_EXT_001 | 502 | API 上游失败 | API 路由依赖返回错误 | 检查依赖健康和路由日志 |
| API_TMO_001 | 504 | API 超时 | API 请求等待依赖超时 | 重试或增加依赖超时 |
| API_INT_001 | 500 | API 内部错误 | 未预期的路由失败 | 检查路由日志，用具体 FinerError 替换宽泛异常 |

## F0 接入层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F0_IN_001 | 400 | F0 输入无效 | 接入源载荷缺少必填字段 | 入库前校验 ContentRecord 源元数据 |
| F0_EXT_001 | 502 | F0 源不可达 | 外部接入源无法连接 | 检查源凭证、网络和适配器健康 |
| F0_EXT_002 | 502 | F0 源返回无效数据 | 源响应格式错误或不支持 | 捕获原始响应，更新源适配器解析器 |
| F0_AUTH_001 | 401 | F0 源认证失败 | 接入适配器凭证过期或无效 | 刷新源 token 或登录会话 |
| F0_TMO_001 | 504 | F0 接入超时 | 源入库超时 | 分页重试或检查外部源延迟 |
| F0_STATE_001 | 409 | F0 状态无效 | 接入会话或游标不一致 | 重置或修复源游标/会话状态 |
| F0_IO_001 | 500 | F0 产物写入失败 | 接入产物无法持久化 | 检查 data/F0_intake 权限和存储路径 |
| F0_INT_001 | 500 | F0 内部错误 | 未预期的接入阶段失败 | 检查 F0 适配器日志，加更精确的错误码 |

## F1 标准化层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F1_IN_001 | 400 | F1 输入无效 | 收到无效的 ContentRecord 或源产物 | 确保 F0 输出满足 ContentRecord |
| F1_SCHEMA_001 | 422 | F1 envelope schema 无效 | ContentEnvelope 或 ContentBlock 校验失败 | 修正标准器输出以符合 F1 schema |
| F1_PARSE_001 | 422 | F1 文本解析失败 | 标准器无法将源文本解析为规范块 | 检查原始文本边界和解析器假设 |
| F1_PARSE_002 | 422 | F1 媒体解析失败 | OCR/ASR/布局提取产出不可用内容 | 检查媒体产物和感知服务输出 |
| F1_EXT_001 | 502 | F1 感知服务失败 | OCR/ASR/视觉依赖失败 | 检查感知服务健康和请求载荷大小 |
| F1_TMO_001 | 504 | F1 标准化超时 | 标准化超时 | 拆分大输入或增加 F1 超时 |
| F1_STATE_001 | 409 | F1 来源状态无效 | 块来源与源产物不匹配 | 修复源 id 和块来源引用 |
| F1_INT_001 | 500 | F1 内部错误 | 未预期的标准器失败 | 检查标准器日志，加更精确的 F1 错误码 |

## F1.5 主题组装层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F15_IN_001 | 400 | F1.5 输入无效 | 主题组装收到无效的 ContentBlock 输入 | 传入规范的 F1 ContentEnvelope 和 ContentBlock id |
| F15_SCHEMA_001 | 422 | F1.5 主题 schema 无效 | TopicBlock 或 TopicAssemblyResult 校验失败 | 修正主题组装输出以匹配 topic_block.py |
| F15_STATE_001 | 409 | F1.5 状态无效 | 主题边界或源块引用不一致 | 检查 source_block_ids 和组装诊断 |
| F15_EXT_001 | 502 | F1.5 LLM 提案失败 | 约束主题提案依赖失败 | 使用确定性降级或检查 LLM 适配器输出 |
| F15_TMO_001 | 504 | F1.5 组装超时 | 主题组装超时 | 拆分输入或减少 LLM 提案范围 |
| F15_INT_001 | 500 | F1.5 内部错误 | 未预期的主题组装失败 | 检查主题组装器日志，加更精确的 F1.5 错误码 |

## F2 锚定层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F2_IN_001 | 400 | F2 输入无效 | 锚定阶段收到无效的主题或证据输入 | 确保 F1.5 输出满足 TopicBlock |
| F2_NTF_001 | 404 | F2 实体不存在 | 实体解析找不到必需实体 | 在实体注册表添加别名或放宽解析器查询 |
| F2_EXT_001 | 502 | F2 市场数据失败 | 金融数据或富化依赖失败 | 检查 finance-skills 服务健康和符号映射 |
| F2_TMO_001 | 504 | F2 富化超时 | 锚定或富化工作超时 | 缓存金融查询或减少批次大小 |
| F2_SCHEMA_001 | 422 | F2 schema 无效 | QualityCard/TemporalAnchor/EntityAnchor/EvidenceSpan 校验失败 | 修正富化输出字段和证据引用 |
| F2_STATE_001 | 409 | F2 锚定状态无效 | 证据 span 或锚定与源内容矛盾 | 检查 span 偏移和源块 id |
| F2_INT_001 | 500 | F2 内部错误 | 未预期的锚定阶段失败 | 检查 F2 日志，加更精确的错误码 |

## F3 意图提取层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F3_IN_001 | 400 | F3 输入无效 | 意图提取收到无效的锚定内容 | 传入 F2 锚定证据，非原始文本 |
| F3_SCHEMA_001 | 422 | F3 意图 schema 无效 | NormalizedInvestmentIntent 校验失败 | 修正意图提取器输出和必填 id |
| F3_PARSE_001 | 422 | F3 意图解析失败 | 提取器无法识别有效投资意图 | 检查证据 span 和提取规则 |
| F3_EXT_001 | 502 | F3 LLM 提取失败 | 意图提取 LLM 依赖失败 | 检查 LLM 提供商健康和结构化输出 |
| F3_TMO_001 | 504 | F3 提取超时 | 意图提取超时 | 减少输入大小或拆分提取批次 |
| F3_STATE_001 | 409 | F3 追踪状态无效 | 意图追踪与上游证据不对齐 | 确保 intent_id 和 evidence_span_ids 由 F2 生成 |
| F3_INT_001 | 500 | F3 内部错误 | 未预期的意图阶段失败 | 检查 F3 日志，加更精确的错误码 |

## F4 策略映射层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F4_IN_001 | 400 | F4 输入无效 | 策略映射收到无效的意图输入 | 传入规范的 NormalizedInvestmentIntent |
| F4_POLICY_001 | 422 | F4 策略拒绝意图 | 策略层拒绝了不可操作或不安全的意图 | 检查 rejection_reason 和策略规则元数据 |
| F4_POLICY_002 | 422 | F4 无匹配策略 | 无策略规则可映射该意图 | 为该意图类型添加或调整策略规则 |
| F4_SCHEMA_001 | 422 | F4 策略 schema 无效 | PolicyMappingResult 校验失败 | 修正策略映射器输出和 id |
| F4_STATE_001 | 409 | F4 策略状态无效 | 策略映射状态与意图追踪不一致 | 检查 intent_id、policy_id 和映射诊断 |
| F4_EXT_001 | 502 | F4 策略依赖失败 | 策略查找依赖失败 | 检查策略数据源可用性 |
| F4_INT_001 | 500 | F4 内部错误 | 未预期的策略阶段失败 | 检查 F4 日志，加更精确的错误码 |

## F5 执行层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F5_IN_001 | 400 | F5 输入无效 | 执行收到无效的策略映射意图 | 传入 F4 PolicyMappingResult，非原始文本 |
| F5_SCHEMA_001 | 422 | F5 交易动作 schema 无效 | TradeAction 或 ExecutionTiming 校验失败 | 包含 intent_id、policy_id、evidence_span_ids 和四个执行时钟 |
| F5_STATE_001 | 409 | F5 规范追踪无效 | TradeAction 追踪缺少上游 id | 通过 F3->F4->F5 构造器构建动作 |
| F5_POLICY_001 | 422 | F5 策略守卫失败 | 执行尝试了策略禁止的动作 | 构造 TradeAction 前检查策略守卫结果 |
| F5_EXT_001 | 502 | F5 执行依赖失败 | 执行或市场依赖失败 | 检查市场数据和执行服务健康 |
| F5_TMO_001 | 504 | F5 执行超时 | 交易动作构造或执行超时 | 用更小批次重试或检查依赖延迟 |
| F5_INT_001 | 500 | F5 内部错误 | 未预期的执行阶段失败 | 检查 F5 日志，加更精确的错误码 |

## F6 复核层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F6_IN_001 | 400 | F6 复核输入无效 | 复核或 RLHF 端点收到无效反馈输入 | 校验复核载荷和必填动作 id |
| F6_NTF_001 | 404 | F6 复核项不存在 | 请求的复核项不存在 | 检查复核 id 和已复核数据目录 |
| F6_SCHEMA_001 | 422 | F6 反馈 schema 无效 | RLHFFeedback 校验失败 | 修正反馈载荷字段和标签 |
| F6_STATE_001 | 409 | F6 复核状态无效 | 复核状态转换不允许 | 更新前检查当前复核状态 |
| F6_INT_001 | 500 | F6 内部错误 | 未预期的复核阶段失败 | 检查 F6 路由和服务日志 |

## F7 时间线层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F7_IN_001 | 400 | F7 时间线输入无效 | 时间线引擎收到无效的 KOL 或动作输入 | 传入已复核动作和有效 KOL 标识符 |
| F7_NTF_001 | 404 | F7 时间线不存在 | 请求的时间线或 KOL 状态不存在 | 检查 KOL id 和时间线存储 |
| F7_SCHEMA_001 | 422 | F7 时间线 schema 无效 | KOLTimeline 或 ViewpointState 校验失败 | 修正时间线 schema 输出 |
| F7_STATE_001 | 409 | F7 时间线状态无效 | 时间线状态无法从当前输入推进 | 检查观点转换和动作排序 |
| F7_INT_001 | 500 | F7 内部错误 | 未预期的时间线阶段失败 | 检查 F7 日志，加更精确的错误码 |

## F8 回测层错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| F8_IN_001 | 400 | F8 回测输入无效 | 回测收到无效的动作、周期或价格输入 | 校验动作列表、日期范围和符号 |
| F8_NTF_001 | 404 | F8 回测不存在 | 请求的回测结果不存在 | 检查回测 id 和结果存储 |
| F8_EXT_001 | 502 | F8 价格数据失败 | 回测价格依赖失败 | 检查数据提供商健康和 ticker 可用性 |
| F8_TMO_001 | 504 | F8 回测超时 | 回测计算超时 | 缩小日期范围或缓存价格数据 |
| F8_INT_001 | 500 | F8 内部错误 | 未预期的回测阶段失败 | 检查 F8 日志，加更精确的错误码 |

## LLM 服务错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| LLM_AUTH_001 | 401 | LLM 认证失败 | 提供商拒绝已配置的 API 凭证 | 刷新环境配置中的提供商 API key |
| LLM_CFG_001 | 500 | LLM 配置缺失 | 必需的模型或提供商配置缺失 | 检查 model_config.py 和提供商环境变量 |
| LLM_EXT_001 | 502 | LLM 提供商不可用 | 提供商返回不可用或服务器错误 | 带退避重试，检查提供商状态 |
| LLM_EXT_002 | 429 | LLM 限流 | 提供商因配额或速率限制拒绝请求 | 等待提供商重试窗口后重试，或降低并发 |
| LLM_TMO_001 | 504 | LLM 请求超时 | 提供商未在超时内响应 | 增加超时或缩小 prompt |
| LLM_SCHEMA_001 | 422 | LLM 结构化输出无效 | 提供商响应不匹配预期 Pydantic 模型 | 检查原始 completion，收紧约束解码或校验 |
| LLM_INT_001 | 500 | LLM 客户端内部错误 | LLM 客户端包装器内未预期失败 | 检查客户端日志和提供商响应元数据 |

## 微信集成错误码 (WX)

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| WX_AUTH_001 | 401 | 微信认证失败 | 微信会话或 cookie 无效 | 刷新登录会话和导出器 auth key |
| WX_EXT_001 | 502 | 微信导出器不可达 | wechat-article-exporter 不可达或返回错误 | 启动导出器并验证 exporter_url |
| WX_TMO_001 | 504 | 微信导出器超时 | 微信导出器请求超时 | 检查导出器健康，增加超时重试 |
| WX_NTF_001 | 404 | 微信资源不存在 | 请求的微信会话、账号或文章不存在 | 检查 session_id、account_id 或文章 URL |

## B站集成错误码 (BILI)

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| BILI_IN_001 | 400 | B站输入无效 | B站 URL 或 BV 号无法解析 | 提供有效的 B站 URL 或 BV 号 |
| BILI_EXT_001 | 502 | B站上游失败 | B站 API、下载或转录依赖失败 | 检查上游响应和本地媒体工具 |
| BILI_NTF_001 | 404 | B站资源不存在 | 请求的 B站视频或生成产物不存在 | 验证 BV 号和产物路径 |

## 飞书集成错误码 (FEISHU)

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| FEISHU_AUTH_001 | 401 | 飞书认证失败 | 飞书/Lark 凭证或租户访问失败 | 刷新 lark-cli auth 和应用权限 |
| FEISHU_EXT_001 | 502 | 飞书上游失败 | 飞书/Lark API 返回错误 | 检查 lark-cli 输出和 API 权限 |
| FEISHU_TMO_001 | 504 | 飞书上游超时 | 飞书/Lark API 请求超时 | 重试或缩小请求数据范围 |

## NLM 集成错误码

| 错误码 | HTTP | 含义 | 触发条件 | 修复建议 |
|--------|------|------|----------|----------|
| NLM_EXT_001 | 502 | NLM 上游失败 | NLM 笔记本或文档依赖返回错误 | 检查 NLM 配置和上游状态 |
| NLM_TMO_001 | 504 | NLM 上游超时 | NLM 依赖超时 | 用更小范围重试或增加超时 |

---

## 新增错误码流程

1. 在 `codes.py` 的 `ErrorCode` 枚举中添加新成员（遵循 `{DOMAIN}_{CATEGORY}_{SEQUENCE}` 格式）
2. 在 `ERROR_CODE_DEFINITIONS` 字典中添加对应的 `_info(...)` 元数据
3. 如需新的异常子类，在 `exceptions.py` 中添加
4. 在业务代码中使用 `raise FinerError(ErrorCode.XXX_YYY_ZZZ, "...")` 抛出
5. 运行 `pytest tests/test_errors.py -v` 验证

## 前端错误展示

前端应统一处理 API 错误响应：

```typescript
interface FinerErrorResponse {
  ok: false;
  error: {
    code: string;      // 如 "LLM_EXT_002"
    message: string;   // 人类可读消息
    details: {
      request_id: string;  // 用于日志追踪
      [key: string]: any;
    };
  };
}
```

前端展示建议：
- 用 `error.code` 做精确匹配和国际化
- 用 `error.message` 做兜底展示
- 用 `error.details.request_id` 关联后端日志
- 429 错误码自动重试（指数退避）
