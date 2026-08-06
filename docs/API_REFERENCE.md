# API 参考文档

本文档描述 Finer OS 的所有 API 端点。

**Base URL**: `http://localhost:8000`

---

## 目录

- [认证](#认证)
- [文件管理](#文件管理)
- [F2 富化/锚定层](#f2-富化锚定层)
- [可信度与共识（CRD）](#可信度与共识crd)
- [复核系统](#复核系统)
- [RLHF 反馈](#rlhf-反馈)
- [集成接口](#集成接口)
- [数据流](#数据流)
- [统计信息](#统计信息)

---

## 认证

当前版本 API 不需要认证（开发模式）。

生产环境建议配置 API Key 认证：

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8000/api/files
```

---

## 文件管理

### 获取资产列表

**GET** `/api/files`

获取指定层级的资产列表。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|:---|:---|:---|:---|:---|
| `tier` | string | 否 | `F1` | 层级（F0/F1/F2/F3/F5/F6/F8）。旧 L 值（L0/L1/L2/L3/L5/L6/L8）仍兼容。 |
| `source_type` | string | 否 | - | 过滤来源类型（feishu/notebooklm/local） |
| `source_group_id` | string | 否 | - | 过滤来源组 ID |
| `sort_by` | string | 否 | `file_timestamp` | 排序字段 |

**响应示例**：

```json
{
  "contract": "canonical_asset_v1",
  "tier": "F1",
  "workflow": "standardize",
  "files": [
    {
      "id": "content_001",
      "name": "聊天记录 (03-12 14:34 至 04-20 19:19)",
      "size": "2.34 MB",
      "date": "2026-04-20",
      "type": "md",
      "status": "canonical",
      "workflowStage": "standardize",
      "stageBadge": "F1",
      "creatorName": "trader_jiu",
      "sourcePlatform": "feishu",
      "contentType": "weekly_strategy",
      "contentId": "content_001",
      "sourcePath": "/data/L0_ingest/trader_jiu/weekly_strategy/...",  // → F0 intake (legacy physical path)
      "manifestPath": "/data/processed/manifests/content_001.json",
      "evidencePath": "/data/L3_aligned/documents/content_001.md",  // → F2 anchored (legacy physical path)
      "summary": "本周策略回顾...",
      "tags": ["weekly_strategy", "trader_jiu"],
      "sourceType": "feishu",
      "sourceGroupId": "oc_xxx",
      "sourceGroupName": "投资研究群",
      "fileTimestamp": "2026-04-20T19:19:00"
    }
  ],
  "totalBySource": {
    "feishu": 15,
    "notebooklm": 3,
    "local": 2
  },
  "sourceGroups": [
    {
      "id": "oc_xxx",
      "name": "投资研究群",
      "type": "feishu",
      "fileCount": 15
    }
  ]
}
```

---

### 上传文件

**POST** `/api/files`

上传文件到 F0 接入台。

**请求**：

```
Content-Type: multipart/form-data

file: <binary>
```

**响应示例**：

```json
{
  "success": true,
  "contract": "canonical_asset_v1",
  "message": "File test.pdf imported into canonical intake inbox",
  "path": "/data/raw/_inbox/unclassified/test.pdf",
  "workflow": "intake",
  "stageBadge": "F0"
}
```

---

### 获取富化实体内容

**GET** `/api/files/enrichment/{entity}`

获取与指定实体（标的/公司）关联的所有内容。

**响应示例**：

```json
{
  "entity": "AAPL",
  "contents": [
    {
      "id": "content_001",
      "name": "周报 2026-04-15",
      "type": "md",
      "creatorName": "trader_jiu",
      "contentType": "weekly_strategy",
      "sourcePath": "/data/...",
      "manifestPath": "/data/processed/manifests/..."
    }
  ]
}
```

---

### 清除缓存

**POST** `/api/files/cache/invalidate`

手动清除所有缓存。

---

### 预热缓存

**POST** `/api/files/cache/warmup`

预构建缓存以加速后续加载。

---

### 诊断信息

**GET** `/api/files/diagnostics`

获取数据目录和同步状态诊断信息。

**响应示例**：

```json
{
  "dataRoot": "/path/to/data",
  "fileCounts": {
    "l0_ingest": 25,
    "raw": 10,
    "manifests": 20,
    "feishu_pool_pending": 3
  },
  "syncState": {
    "oc_xxx": "2026-04-20T19:19:00"
  },
  "cacheStatus": {
    "assets_cache_entries": 6,
    "manifests_index_built": true
  }
}
```

---

## F2 富化/锚定层

### 话题分割

**POST** `/api/enrichment/split`

将长内容按话题分割。

**请求**：

```json
{
  "content_id": "content_001",
  "content": "聊天记录全文...",
  "force_refresh": false
}
```

**响应示例**：

```json
{
  "content_id": "content_001",
  "topics_count": 3,
  "topics": [
    {
      "title": "腾讯投资策略",
      "tickers": ["TCEHY"],
      "companies": ["腾讯"],
      "summary": "讨论腾讯近期走势和建仓点位...",
      "time_range": {
        "start": "2026-04-15T10:00",
        "end": "2026-04-15T11:30"
      }
    }
  ]
}
```

---

### 实体抽取

**POST** `/api/enrichment/extract`

从内容中提取实体（标的、公司、人物、事件）。

**请求**：

```json
{
  "content_id": "content_001",
  "content": "分析文本...",
  "force_refresh": false
}
```

**响应示例**：

```json
{
  "content_id": "content_001",
  "entities": {
    "tickers": ["AAPL", "TCEHY"],
    "companies": ["苹果", "腾讯"],
    "people": ["巴菲特", "芒格"],
    "events": ["财报发布", "降息"],
    "concepts": ["AI", "云计算"],
    "metrics": ["PE 25", "营收增长 15%"]
  },
  "related_content": ["content_002", "content_003"]
}
```

---

### 按标的查询

**GET** `/api/enrichment/by-ticker/{ticker}`

获取与指定标的相关的所有内容。

**响应示例**：

```json
{
  "ticker": "AAPL",
  "content_count": 5,
  "content_ids": ["content_001", "content_002", ...]
}
```

---

### 按公司查询

**GET** `/api/enrichment/by-company/{company}`

获取与指定公司相关的所有内容。

---

### 列出所有标的

**GET** `/api/enrichment/tickers`

列出所有已索引的标的及其内容数量。

**响应示例**：

```json
{
  "tickers": [
    {
      "ticker": "AAPL",
      "companies": ["苹果"],
      "content_count": 8,
      "content_ids": ["content_001", ...]
    }
  ],
  "total_tickers": 15
}
```

---

### 列出所有公司

**GET** `/api/enrichment/companies`

列出所有已索引的公司及其内容数量。

---

### 重建索引

**POST** `/api/enrichment/rebuild-index`

从所有 manifests 重建内容索引。

---

### 富化状态

**GET** `/api/enrichment/status`

获取 F2 富化/锚定层状态。

**响应示例**：

```json
{
  "l1_dir_exists": true,
  "index_exists": true,
  "by_ticker_dir": true,
  "by_event_dir": false,
  "by_topic_dir": true,
  "indexed_entities": 25,
  "indexed_content": 15
}
```

---

## 可信度与共识（CRD）

> **口径纪律。** 这两组接口返回的是**历史记录**，不是预测。跨期持续性检验
> （`docs/specs/2026-07-30-credibility-persistence-test.md` 附录 B）结论为
> 「前提未获支持」，因此响应恒带 `predictive_claim.permitted=false` 与口径
> `notes`，**前端必须逐条展示，不得折叠或省略**。

### 个股共识记录

**GET** `/api/ticker/{symbol}/consensus`

聚合某标的下所有信源的**最新**立场。`symbol` 接受任意方言写法
（`AZN.LN` / `AZN.L` 归一为同一视图）。

```bash
curl http://localhost:8000/api/ticker/NVDA/consensus
```

```json
{
  "ok": true,
  "data": {
    "ticker": "NVDA",
    "latest_report_date": "2026-06-03",
    "as_of_days": 63,
    "staleness": "current",
    "n_sources": 9,
    "direction_counts": {"bullish": 9},
    "directional_agreement": 1.0,
    "latest_by_source": [
      {
        "creator_id": "摩根士丹利",
        "direction": "bullish",
        "rating": "Overweight",
        "target_price_value": 288.0,
        "target_price_currency": "USD",
        "report_date": "2026-06-03",
        "intent_id": "bri_711f84f1f010804ff02b7ba2",
        "n_reports": 4
      }
    ],
    "target_prices": {
      "currency": "USD", "n": 8,
      "min_value": 205.0, "median_value": 284.0, "max_value": 350.0,
      "excluded_unit_ambiguous": 0, "excluded_currency_mismatch": 0
    },
    "notes": ["共识为等权聚合……", "本视图描述已发生的声明记录……"]
  }
}
```

| 字段 | 含义 |
|---|---|
| `staleness` | `current` / `aging` / `stale` / `archival`（90/180/365 天分档）。**读取时计算**，不物化——距今天数每天都在变 |
| `as_of_days` | `latest_report_date` 距今天数 |
| `n_reports` | 该信源对此标的的历史报告数（共识只计最新一篇，防高频覆盖霸占共识） |
| `intent_id` | 下钻入口 → F3 → F2 证据原文 |
| `target_prices` | 只聚合同币种；`.L` 标的因镑/便士混存显式排除并计数 |

未找到标的返回 404 canonical error envelope（含 `fix_hint`）。

### 信源历史记录卡

**GET** `/api/creator/records?signal_class=broker_recommendation`

**GET** `/api/creator/{creator_id}/record?signal_class=...`

`signal_class` 是**口径隔离键**。不同口径的基准率不同，**不可跨口径比较**：

| 值 | 含义 |
|---|---|
| `broker_recommendation`（默认） | 券商对**个股**的评级 |
| `broker_sector_view` | 券商对**板块**的看法（ETF 代理成交） |
| `kol_statement` | KOL 自述仓位 |

每张卡**必带** `sufficiency`（CRD-2 统计效力门），前端按 `display_policy`
呈现，不得绕过：

| `display_policy` | 前端义务 |
|---|---|
| `show` | 命中率必须与 95% Wilson 区间并排展示 |
| `show_with_warning` | 加「样本偏少」提示 |
| `count_only` | **不得渲染任何比率**，只显计数 |

列表顺序 = 已结算样本量降序。这是**稳定输出序，不是排名**。

---

## 复核系统

### 保存复核结果

**POST** `/api/review/save`

保存事件复核结果。

**请求**：

```json
{
  "content_id": "content_001",
  "review_payload": {
    "ticker": "AAPL",
    "direction": "bullish",
    "timeHorizon": "weekly",
    "rationale": "基本面强劲",
    "evidenceText": "原文引用...",
    "confidence": 0.85,
    "tags": ["AAPL", "bullish"],
    "ambiguityNotes": ["确认触发条件"],
    "actionChain": [
      {
        "id": "action-1",
        "actionType": "long",
        "instrumentType": "stock",
        "triggerCondition": "price <= 180",
        "targetPriceLow": "180",
        "targetPriceHigh": "200",
        "confidence": 0.85,
        "status": "active"
      }
    ]
  }
}
```

**响应示例**：

```json
{
  "success": true,
  "path": "/data/processed/review_store/content_001.review.json",
  "content_id": "content_001"
}
```

---

### 批准事件

**POST** `/api/review/approve`

将事件从候选状态移动到已批准状态。

**请求**：

```json
{
  "content_id": "content_001"
}
```

---

## RLHF 反馈

### 提交反馈

**POST** `/api/rlhf/submit`

提交对 TradeAction 的反馈。

**请求**：

```json
{
  "trade_action_id": "action_001",
  "event_id": "event_001",
  "content_id": "content_001",
  "rating": 4,
  "ticker_correct": true,
  "ticker_correction": null,
  "direction_correct": false,
  "direction_correction": "bullish",
  "action_chain_feedback": [
    {
      "sequence_order": 1,
      "action_type_correct": true,
      "trigger_correct": false,
      "trigger_correction": "price <= 180"
    }
  ],
  "quick_tags": ["方向相反", "触发条件错误"],
  "notes": "方向判断有误，应为看多",
  "reviewer_id": "user_001",
  "preference": {
    "chosen": "{\"ticker\": \"AAPL\", \"direction\": \"bullish\"}",
    "rejected": "{\"ticker\": \"AAPL\", \"direction\": \"bearish\"}",
    "is_original_correct": false
  }
}
```

**响应示例**：

```json
{
  "success": true,
  "feedback_id": "fb_001",
  "path": "/data/rlhf/feedbacks/fb_001.json"
}
```

---

### 获取待标注列表

**GET** `/api/rlhf/pending`

获取待反馈的 TradeAction 列表。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|:---|:---|:---|:---|:---|
| `limit` | int | 否 | 50 | 返回数量 |
| `offset` | int | 否 | 0 | 偏移量 |
| `has_feedback` | bool | 否 | - | 过滤是否已有反馈 |

**响应示例**：

```json
{
  "items": [
    {
      "trade_action_id": "action_001",
      "event_id": "event_001",
      "content_id": "content_001",
      "ticker": "AAPL",
      "direction": "bullish",
      "extracted_at": "2026-04-20T10:00:00",
      "has_feedback": false,
      "feedback_id": null
    }
  ],
  "total": 25,
  "limit": 50,
  "offset": 0,
  "has_more": false
}
```

---

### 获取 Action 详情

**GET** `/api/rlhf/action/{action_id}`

获取 TradeAction 详情及已有反馈。

**响应示例**：

```json
{
  "action_id": "action_001",
  "original_extraction": {
    "ticker": "AAPL",
    "direction": "bearish",
    "actions": [...]
  },
  "feedback": {
    "feedback_id": "fb_001",
    "rating": 4,
    "direction_correct": false,
    "direction_correction": "bullish"
  },
  "feedback_id": "fb_001"
}
```

---

### 更新反馈

**PUT** `/api/rlhf/action/{action_id}`

更新已有反馈。

---

### 反馈统计

**GET** `/api/rlhf/stats`

获取 RLHF 反馈统计。

**响应示例**：

```json
{
  "total_feedbacks": 15,
  "average_rating": 3.8,
  "rating_distribution": {
    "1": 0,
    "2": 1,
    "3": 3,
    "4": 6,
    "5": 5
  },
  "ticker_accuracy": 0.93,
  "direction_accuracy": 0.80,
  "common_tags": [
    {"tag": "触发条件错误", "count": 5},
    {"tag": "价格错误", "count": 3}
  ],
  "pending_reviews": 10,
  "dpo_ready_count": 8
}
```

---

### 导出 DPO 数据

**GET** `/api/rlhf/export`

导出 DPO 训练数据。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|:---|:---|:---|:---|:---|
| `min_rating` | int | 否 | 1 | 最低评分 |
| `only_with_preference` | bool | 否 | true | 仅包含偏好数据 |
| `format` | string | 否 | jsonl | 输出格式（json/jsonl） |

**响应示例**：

```json
{
  "format": "jsonl",
  "count": 8,
  "data": "{\"prompt\": \"从以下文本提取 Trade Action:\\n...\", \"chosen\": \"{...}\", \"rejected\": \"{...}\"}"
}
```

---

### 列出反馈

**GET** `/api/rlhf/feedbacks`

列出所有反馈记录。

---

### 删除反馈

**DELETE** `/api/rlhf/feedback/{feedback_id}`

删除指定反馈记录。

---

## 集成接口

### 获取飞书群列表

**GET** `/api/integrations/feishu/chats`

获取已配置的飞书群列表。

---

### 同步飞书群

**POST** `/api/integrations/feishu/fetch`

同步指定飞书群的消息和附件。

**请求**：

```json
{
  "chat_id": "oc_xxx"
}
```

**响应示例**：

```json
{
  "status": "ok",
  "messages_scanned": 50,
  "downloaded": 5,
  "files": ["image1.png", "report.pdf", "chat_history.md"]
}
```

---

### 获取 NotebookLM 列表

**GET** `/api/integrations/nlm/notebooks`

获取 NotebookLM 笔记本列表。

---

### 同步 NotebookLM

**POST** `/api/integrations/nlm/fetch`

同步指定笔记本的内容。

---

### 查看同步池

**GET** `/api/integrations/pool`

查看飞书和 NotebookLM 同步池中的文件。

**响应示例**：

```json
{
  "files": [
    {
      "name": "image1.png",
      "type": "png",
      "origin": "feishu",
      "date": "2026-04-20T10:00:00",
      "size_bytes": 102400,
      "previewable": true,
      "download_path": "feishu_sync_pool/image1.png"
    }
  ]
}
```

---

### 导入到 F0

**POST** `/api/integrations/import`

从同步池导入文件到 F0 接入台。

**请求**：

```json
{
  "filenames": ["image1.png", "report.pdf"],
  "pool_type": "feishu"
}
```

**响应示例**：

```json
{
  "results": [
    {
      "filename": "image1.png",
      "status": "success",
      "content_id": "content_001",
      "target": "/data/L0_ingest/trader_jiu/weekly_strategy/image1.png"
    }
  ]
}
```

---

## 数据流

### 下载文件

**GET** `/api/streams/download`

下载指定路径的文件。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|:---|:---|:---|:---|
| `path` | string | 是 | 文件相对路径 |

---

## 统计信息

### 获取统计

**GET** `/api/stats`

获取系统统计信息。

---

### 健康检查

**GET** `/api/health`

检查 API 服务健康状态。

**响应示例**：

```json
{
  "status": "ok",
  "service": "finer-canonic-api"
}
```

---

## 错误响应

所有错误响应遵循以下格式：

```json
{
  "detail": "Error message describing what went wrong"
}
```

### 常见错误码

| 状态码 | 说明 |
|:---|:---|
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 请求/响应示例

### 使用 curl

```bash
# 获取文件列表
curl "http://localhost:8000/api/files?tier=F0"

# 提交反馈
curl -X POST http://localhost:8000/api/rlhf/submit \
  -H "Content-Type: application/json" \
  -d '{"trade_action_id": "test", "rating": 5}'
```

### 使用 Python

```python
import httpx

# 获取文件列表
resp = httpx.get("http://localhost:8000/api/files", params={"tier": "F0"})
files = resp.json()["files"]

# 提交反馈
resp = httpx.post(
    "http://localhost:8000/api/rlhf/submit",
    json={
        "trade_action_id": "test",
        "rating": 5,
        "ticker_correct": True,
    }
)
```

### 使用 JavaScript

```javascript
// 获取文件列表
const resp = await fetch('/api/files?tier=F0');
const { files } = await resp.json();

// 提交反馈
const resp = await fetch('/api/rlhf/submit', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    trade_action_id: 'test',
    rating: 5
  })
});
```

---

*最后更新: 2026-08-06 (新增 CRD 可信度与共识接口)*