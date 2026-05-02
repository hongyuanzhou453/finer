# 快速开始指南

本指南帮助你在 5 分钟内运行 Finer OS。

---

## 环境要求

### 必需

- **Python 3.11+**
- **Node.js 18+**
- **Git**

### 可选

- **Redis** - 用于缓存加速
- **PostgreSQL** - 用于持久化存储（生产环境）

### 外部服务

- **LLM API** - 至少一个：
  - MiMo API Key（F1 图片/PDF OCR 主力）
  - OpenAI API Key
  - DeepSeek API Key
  - 通义千问（DashScope）API Key

- **飞书** - 如需同步飞书群：
  - Lark CLI 工具
  - 飞书 App ID 和 Secret

---

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/kelipovanatalja453-bot/finer.git
cd finer
```

### 2. 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -e .
```

### 3. 安装前端依赖

```bash
cd src/finer_dashboard
npm install
cd ../..
```

---

## 配置说明

### 1. 环境变量

创建 `.env` 文件或设置环境变量：

```bash
# LLM 配置（至少配置一个）
export MIMO_API_KEY="..."      # MiMo-V2.5，F1 图片/PDF OCR
# Token Plan key（tp-*）必须配置对应 token-plan base URL；标准 API key 可省略
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"
# 可选：单独指定 vision base URL（优先于 MIMO_BASE_URL）
export MIMO_VISION_BASE_URL="..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="..."
export DASHSCOPE_API_KEY="..."  # 通义千问

# 可选：Finance Skills API
export FINANCE_SKILLS_API_KEY="..."

# 可选：Redis 缓存
export REDIS_URL="redis://localhost:6379"
```

### 2. 飞书配置

如需使用飞书同步功能，创建 `configs/feishu.yaml`：

```yaml
feishu:
  lark_cli_path: "/opt/homebrew/bin/lark-cli"
  state_file: "data/.feishu_sync_state.json"
  
  watched_chats:
    - chat_id: "oc_xxx"
      name: "投资研究群"
      notebook_id: "nlm_xxx"  # 可选：NotebookLM 同步
      default_creator: "trader_jiu"
    
    - chat_id: "oc_yyy"
      name: "策略讨论群"
      default_creator: "analyst"

  classification_rules:
    - pattern: "周报"
      content_type: "weekly_strategy"
      creator_id: "trader_jiu"
    
    - pattern: "盘前"
      content_type: "daily_pre_post"
      creator_id: "trader_jiu"

notebooklm:
  nlm_cli_path: "/Users/xxx/.local/bin/nlm"
```

### 3. 模型配置

在 `src/finer/model_config.py` 中可自定义模型优先级：

```python
TEXT_MODELS = [
    ModelConfig(
        name="deepseek-chat",
        provider=ModelProvider.DEEPSEEK,
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        priority=1,  # 优先级
    ),
    # 其他模型...
]
```

---

## 运行命令

### 启动后端 API

```bash
cd src

# 开发模式（自动重载）
uvicorn finer.api.server:app --port 8000 --reload

# 生产模式
uvicorn finer.api.server:app --port 8000 --workers 4
```

### 启动前端 Dashboard

```bash
cd src/finer_dashboard

# 开发模式
npm run dev

# 生产构建
npm run build
npm run start
```

### 访问应用

- **Dashboard**: http://localhost:3000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/health

---

## 快速验证

### 1. 检查 API 健康状态

```bash
curl http://localhost:8000/api/health
# 返回: {"status": "ok", "service": "finer-canonic-api"}
```

### 2. 查看数据目录状态

```bash
curl http://localhost:8000/api/files/diagnostics
```

### 3. 预热缓存

```bash
curl -X POST http://localhost:8000/api/files/cache/warmup
```

### 4. 上传测试文件

```bash
curl -X POST -F "file=@test.pdf" http://localhost:8000/api/files
```

---

## 常见工作流

### 工作流 1: 飞书同步

```bash
# 1. 获取飞书群列表
curl http://localhost:8000/api/integrations/feishu/chats

# 2. 同步指定群
curl -X POST http://localhost:8000/api/integrations/feishu/fetch \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "oc_xxx"}'

# 3. 查看同步池文件
curl http://localhost:8000/api/integrations/pool

# 4. 导入文件到 F0 Intake
curl -X POST http://localhost:8000/api/integrations/import \
  -H "Content-Type: application/json" \
  -d '{"filenames": ["test.png"], "pool_type": "feishu"}'
```

### 工作流 2: 内容处理与事件抽取

```bash
# 1. 话题分割（enrichment/ 属 F2 Anchor，legacy API 路径名）
curl -X POST http://localhost:8000/api/enrichment/split \
  -H "Content-Type: application/json" \
  -d '{"content_id": "test", "content": "聊天记录..."}'

# 2. 实体抽取（F2 Anchor）
curl -X POST http://localhost:8000/api/enrichment/extract \
  -H "Content-Type: application/json" \
  -d '{"content_id": "test", "content": "..."}'

# 3. 查看按标的分组
curl http://localhost:8000/api/enrichment/tickers
```

### 工作流 3: RLHF 标注

```bash
# 1. 查看待标注列表
curl http://localhost:8000/api/rlhf/pending

# 2. 提交反馈
curl -X POST http://localhost:8000/api/rlhf/submit \
  -H "Content-Type: application/json" \
  -d '{
    "trade_action_id": "action_001",
    "rating": 4,
    "ticker_correct": true,
    "direction_correct": false,
    "direction_correction": "bullish"
  }'

# 3. 查看统计
curl http://localhost:8000/api/rlhf/stats

# 4. 导出 DPO 数据
curl http://localhost:8000/api/rlhf/export
```

---

## 常见问题

### Q: API 启动失败，提示缺少依赖？

```bash
# 确保在 src 目录下运行
cd src
pip install -e ..

# 检查 Python 版本
python --version  # 需要 3.11+
```

### Q: 前端无法连接后端？

```bash
# 检查后端是否运行
curl http://localhost:8000/api/health

# 检查 CORS 配置（开发环境允许所有来源）
# 生产环境需要在 server.py 中配置 allow_origins
```

### Q: 飞书同步失败？

```bash
# 1. 检查 lark-cli 是否安装
which lark-cli

# 2. 检查飞书配置
cat configs/feishu.yaml

# 3. 检查 API Key
# lark-cli 需要先登录认证
lark-cli auth login
```

### Q: 视觉解析失败？

```bash
# 检查 MiMo API Key 是否已配置；不要把真实 key 打到日志里
test -n "$MIMO_API_KEY" && echo "MIMO_API_KEY configured"

# Token Plan key（tp-*）需要使用订阅页对应的 token-plan base URL
export MIMO_BASE_URL="${MIMO_BASE_URL:-https://token-plan-cn.xiaomimimo.com/v1}"

# 检查模型是否可用
curl -X POST "${MIMO_BASE_URL:-https://api.xiaomimimo.com/v1}/chat/completions" \
  -H "api-key: $MIMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mimo-v2.5","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"https://example-files.cnbj1.mi-fds.com/example-files/image/image_example.png"}},{"type":"text","text":"请描述图片内容"}]}],"max_completion_tokens":1024}'
```

### Q: 如何运行 MiMo 实际 OCR 测试？

```bash
# 需要真实 API Key，默认跳过
FINER_ENABLE_LIVE_MIMO=1 MIMO_API_KEY="your-key" \
  MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1" \
  python -m pytest tests/test_live_mimo_multimodal.py -v
```

### Q: 缓存不生效？

```bash
# 清除缓存
curl -X POST http://localhost:8000/api/files/cache/invalidate

# 重新预热
curl -X POST http://localhost:8000/api/files/cache/warmup
```

### Q: 数据目录不存在？

```bash
# 系统会自动创建，但可以手动初始化（F-stage canonical 目录）
mkdir -p data/{raw,F0_intake,F1_standardized,F2_anchored,F3_intents,F4_policy_mapped,F5_executed,F6_reviewed,F7_timeline,F8_metrics,processed,rlhf,cache}
```

### Q: 如何更新黑话词典？

编辑 `词语个人理解（持续更新）.xlsx`，新增行即可：

| 黑话 | 标准表达 | 类别 |
|:---|:---|:---|
| 新黑话 | 标准表达 | 类别 |

系统会在下次启动时自动加载。

---

## 生产部署建议

### 1. 使用 Docker

```bash
# 构建镜像
docker build -t finer-api .

# 运行容器
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v $(pwd)/data:/app/data \
  finer-api
```

### 2. 配置 Nginx

```nginx
server {
    listen 80;
    
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
    
    location / {
        proxy_pass http://localhost:3000;
    }
}
```

### 3. 数据持久化

- 使用 PostgreSQL 替代文件存储
- 配置 Redis 缓存
- 设置数据备份策略

### 4. 安全加固

- 限制 CORS 来源
- 添加 API 认证
- 配置 HTTPS

---

## 下一步

- 阅读 [架构文档](./ARCHITECTURE.md) 了解系统设计
- 查看 [API 参考](./API_REFERENCE.md) 了解所有端点
- 阅读 [功能详解](./FEATURES.md) 了解各模块

---

*最后更新: 2026-04-23*
