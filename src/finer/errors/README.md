# Finer Error Codes

F-stage: cross-stage infrastructure.

This package is the canonical error system for Finer API and pipeline code. It
does not own business logic for any single F-stage; it provides stable error
identity, root-cause lookup, and unified API serialization for all stages.

## Structure

```text
src/finer/errors/
├── __init__.py      # public imports
├── codes.py         # ErrorCode catalog and lookup metadata
├── exceptions.py    # FinerError hierarchy
├── handler.py       # FastAPI exception handlers
└── README.md        # package rules and usage
```

## Code Format

```text
{DOMAIN}_{CATEGORY}_{SEQUENCE}
```

Examples:

- `SYS_IN_001`: invalid request payload
- `WX_EXT_001`: WeChat exporter unavailable
- `LLM_EXT_002`: LLM provider rate limited or overloaded
- `BILI_NTF_001`: Bilibili resource not found

`F15` is the error-code domain for the canonical F1.5 Topic Assembly stage.

## Usage

```python
from finer.errors import FinerError, FinerExternalServiceError
from finer.errors.codes import ErrorCode

raise FinerError(ErrorCode.SYS_IN_001, "Missing content_id")

raise FinerExternalServiceError(
    ErrorCode.LLM_EXT_002,
    "Rate limited",
    service="mimo-api",
    details={"retry_after": 60},
)
```

API responses are serialized as:

```json
{
  "ok": false,
  "error": {
    "code": "WX_EXT_001",
    "message": "Exporter not responding",
    "details": {
      "service": "wechat-exporter",
      "request_id": "..."
    }
  }
}
```

## Rules

- Add a new `ErrorCode` member before using a new code in business code.
- Every code must have catalog metadata: title, root cause, and fix hint.
- Prefer the most specific F-stage or integration domain.
- Do not introduce legacy `L0-L8` or `V0-V6` naming in error codes.
- Sensitive values must not be placed in `details`.

## Canonical Error Envelope (Line F)

新建或改动的 API 错误响应必须遵循以下 envelope 结构。未触及的历史路由由 verification agent 报告并逐步收敛，第一轮不做无边界全量迁移。

```json
{
  "ok": false,
  "error": {
    "code": "F0_EXT_001",
    "message": "微信导出器不可达",
    "details": {
      "request_id": "req-xxx",
      "stage": "F0",
      "operation": "wechat_import",
      "source_channel": "wechat",
      "content_id": "optional",
      "import_run_id": "optional",
      "external_source_id": "optional",
      "retryable": true,
      "fix_hint": "启动 exporter 并验证 exporter_url",
      "exception_type": "optional"
    }
  }
}
```

### Required Fields

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| request_id | string | 是 | 自动生成，贯穿请求生命周期 |
| stage | string | 是 | F0/F1/F2/.../F8/cross |
| operation | string | 是 | 操作标识，如 wechat_import、bilibili_sync |
| source_channel | string | 否 | 数据源渠道：wechat/bilibili/feishu/nlm/local |
| retryable | boolean | 是 | 是否可重试 |
| fix_hint | string | 是 | 人类可读的修复建议 |
| content_id | string | 否 | 关联的内容 ID |
| import_run_id | string | 否 | 导入批次 ID |
| external_source_id | string | 否 | 外部系统 ID |
| exception_type | string | 否 | Python 异常类名（调试用） |

### Sensitive Field Filtering

details 中不得出现：

- token, secret, password, cookie, authorization, api_key

### F0 Error Code Registry

| Code | 含义 | retryable |
|------|------|-----------|
| F0_AUTH_001 | 认证/会话失效 | true |
| F0_EXT_001 | 外部服务不可达 | true |
| F0_EXT_002 | 外部返回异常数据 | false |
| F0_IO_001 | raw 文件写入失败 | true |
| F0_STATE_001 | cursor/session 状态异常 | true |
| F0_TMO_001 | 操作超时 | true |

### First-Round Agent Boundaries

Line F 第一轮只做薄层统一：

- `ERR-0`: 文档和契约，允许改 `docs/specs/2026-05-parallel-agent-execution.md`、`CLAUDE.md`、本 README 和 `RUNBOOK.md`。
- `ERR-1`: 后端 envelope/helper/handler，允许改 `exceptions.py`、`handler.py`、`__init__.py`、`tests/test_errors.py`。
- `ERR-2`: F0 route/adapter 错误映射，限定 F0 route 和 F0 ingestion files。
- `ERR-3`: 前端错误展示契约，限定 dashboard contracts/api-client/error panel/import console。
- `ERR-4`: 只读验证，不改实现。

第一轮禁止新增错误历史数据库、观测平台、队列、生产数据迁移或 SQLite schema 变更。

Recommended verification:

```bash
pytest tests/test_errors.py -q
rg -n "return \\{.*\"error\"|HTTPException\\(status_code=.*detail=\"" src/finer/api/routes src/finer/ingestion
rg -n "token|secret|password|cookie|authorization|api_key" src/finer/errors src/finer/api/routes src/finer/ingestion
```
