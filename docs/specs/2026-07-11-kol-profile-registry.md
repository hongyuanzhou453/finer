# KOL Profile Registry 服务化（P1-4）

## 概述（Overview）

按 roadmap P1-4 落地 KOL 元数据的单一真相源：`configs/creators/*.yaml`（文件真值）+ `services/kol_registry.py`（TTL 60s 只读缓存 + alias/平台身份解析）+ `GET /api/kol/registry`（只读 API）。radar/snapshot/异动/legacy 列表的 KOL 元数据全部从「action 反推/硬编码占位」切换为注册表真值；**「加一个 KOL = 加一份 YAML + 渠道映射」已被证明**——maodaren/9you 建档当天即以真名出现在 /api/kol/list/enriched（零评级数据）。全量 3200 tests 通过，前端 build 通过，live /radar 页 raw creator_id 文本节点归零。

## 变更清单（Changes）

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/schemas/kol_profile.py` | 修改 | 新增 `CreatorProfile`（主键 creator_id=文件名 stem；display_name/handle/style_label 均 Optional；复用 PlatformIdentity/DeclaredTradingStyle） |
| `src/finer/services/kol_registry.py` | 新增 | `KOLRegistry`：TTL 重建缓存（audit_assembler 模式）、`get`（精确）/`resolve`（alias/display_name/handle/`{platform}:{account_id}`，大小写不敏感）/`get_resolved`/`display_name`（miss 回退 raw id）/`declared_style`；坏 YAML 单文件隔离；trading_style 块单独校验（块无效不丢 display_name）；`get_registry(root)` per-root 实例 |
| `src/finer/api/routes/kol_registry.py` | 新增 | `GET /registry`、`GET /registry/{key}`（支持 alias）；404 走 Line F envelope；第三个挂 /api/kol 的 router |
| `configs/creators/_template.yaml` | 新增 | 带注释的建档模板（下划线 stem 不被加载），含 onboarding 指引 |
| `configs/creators/maodaren.yaml` / `9you.yaml` | 新增 | 从 feishu.yaml watched_chats 与 creator_patterns.json 既有真值建档；`kol_cat_lord_fire` 作为 maodaren 的 alias（不独立建档），`resolve()` 为 F0 断链修复铺路；未知字段标「待补」 |
| `configs/creators/trader_ji.yaml` | 修改 | 补 handle/style_label（板块与主题轮动）/specialties/aliases，notes 标「待人工复核」 |
| `src/finer/services/trading_style.py` | 修改 | declared 层与 display_name 解析改走 registry（函数签名不变） |
| `src/finer/api/routes/opinions.py` | 修改 | topKols 增 `displayName`/`styleLabel`（`author` 保持 raw join key）；`/changes` 在 API 边界统一装饰事件 kolName（覆盖历史派生与快照 diff 两个来源） |
| `src/finer/api/routes/kol.py` | 修改 | `_registry_identity()` 替换三处硬编码 name/platform（**精确匹配不走 alias**——kol_cat_lord_fire 在 legacy 列表保留独立行）；`_discover_kol_ids` union 注册表 id（加 YAML 即上架）；enriched 填 `enabled` |
| `src/finer/ingestion/classifier.py` | 修改 | `_merged_creator_tags()`：静态 `_TAG_TO_CREATOR` baseline（伪 creator 路由 研报→_research 留静态层）+ registry aliases 覆盖；registry 异常兜底静态 map（F0 摄入不因 services 失败挂掉） |
| `src/finer_dashboard/src/lib/contracts.ts` | 修改 | `CreatorProfile`/`PlatformIdentity` 类型镜像 |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 修改 | `fetchRegistry()` 容错 fetch + RadarKOL merge（name/handle/style/specialties/platform 兜底）；客户端派生异动事件同样装饰真名 |
| `CLAUDE.md` | 修改 | 公共模块表 +`services/kol_registry.py` |
| `tests/test_kol_registry.py` / `test_kol_registry_api.py` / `test_classifier_creator_tags.py` | 新增 | 28 个新测试；`test_trading_style.py` 增块隔离钉子 |

提交：`96062bb9`(schema+服务) `d03892ce`(API+建档) `18f2fc5f`(后端消费者) `7b65c96c`(前端)。

## 架构影响（Architecture Impact）

- **注册表成为公共模块**（CLAUDE.md §1）：与 `config.py` 同级的配置读层，任何 F-stage 可只读查询。F0（classifier）、F6（trading_style/kol routes）、F7 边界（changes 装饰）均已接线。
- **id 语义分层明确**：`creator_id`（raw）永远是 join key（topKols.author、RadarKOL.kolId、事件 kolId）；display 字段只做展示装饰。alias 解析（含历史 canonical id `kol_cat_lord_fire`→maodaren）只在注册表 API 与 classifier 生效，legacy 数据面精确匹配避免双行合并歧义。
- **孤儿 KOLProfileManager**（`kol_{uuid}` 体系）维持隔离，未复活未删除；`data/kol_profiles/` 命名空间归 annotation_store 速记。
- 前端零组件改动：RadarKOL 是元数据唯一发源节点，adapter 单点 merge 全链路生效。

## 关键决策（Key Decisions）

1. **文件真值 + creator_id 主键**，不复活 UUID CRUD：与「加一份 YAML」的 onboarding 语义天然一致；注册表无写 API。
2. **kol_cat_lord_fire 不建档而作 alias**：它是 importer 默认参数造出的历史 canonical id，与 maodaren 同人；alias 归并避免双档案，`resolve()` 为 F0 creator_mapping 断链修复铺路。
3. **classifier 合并不迁移**：`_TAG_TO_CREATOR` 零测试覆盖 + 含伪 creator 路由 + F0 不允许因 services import 挂掉——静态 baseline + registry 覆盖 + 异常兜底三层。收编价值实证：`#九友` 静态 map 不识别、merged map 正确归 9you。
4. **kolName 装饰收在 API 边界**（`/changes` 一处）而非散进 stance_snapshot/事件生成器：时间线引擎保持纯函数，展示映射留在 route 层。
5. **trading_style 对损坏 YAML 的行为宽松化**（500 穿透→优雅降级）：注册表加载器统一「坏文件隔离」语义，有意变更。

## 验证结果（Verification）

```bash
pytest tests/ -q      # 3200 passed, 15 skipped（+28 新测试）
cd src/finer_dashboard && npm run build   # exit 0
```

端到端（真实后端 + preview）：
- `GET /api/kol/registry` → 3 档案（9you/maodaren/trader_ji）；`/registry/kol_cat_lord_fire` → maodaren；404 带 canonical envelope（code/retryable/fix_hint/request_id）。
- `topKols[0]` → `{author: trader_ji, displayName: trader韭, styleLabel: 板块与主题轮动}`；`/api/kol/rating/trader_ji` → name=trader韭、platform=bilibili；`/api/kol/style/trader_ji` 回归不变。
- `/api/kol/list/enriched` → `[(kol_cat_lord_fire, 5), (trader韭, 3), (9友, 0), (猫大人, 0)]`——**零数据 creator 以真名上架**。
- `/api/opinions/changes` 事件 kolName 全部为「trader韭」。
- live `/radar`：「trader韭」出现 29 处、raw `trader_ji` 文本节点 0、style_label 与 specialties 上屏；sandbox（无档案）正确显示「风格未标注」回退。

## Onboarding 步骤（加一个新 KOL）

1. 复制 `configs/creators/_template.yaml` → `configs/creators/{creator_id}.yaml`，填 display_name/handle/style_label/aliases/platform_identities。
2. 渠道映射：飞书群在 `configs/feishu.yaml` 的 `watched_chats` 加 `default_creator`；内容 hashtag 放进档案 `aliases`（classifier 自动识别）；本地目录按「顶层目录名=creator_id」约定。
3. 60s 内 registry 生效：`/radar`、topKols、`/kol` 列表自动带出真名与风格（零数据也上架，评级为空态）。
4. 跑 `python -m finer.cli pipeline-drive` 摄入内容后，F5 出现该 creator 的 action，信誉分/收益榜/风格画像 observed 层自动激活。

## 未解决项（Open Issues）

1. **F0 `creator_mapping.canonical_creator_id` 下游断链**（feishu_f0_importer.py:210-213）：registry.resolve 已能解析历史 canonical id，但 F1+ 管线尚未消费该映射——收编时机在 F0 摄入改造（P2）。
2. **kol_cat_lord_fire 在 legacy enriched list 与 maodaren 并存两行**（精确匹配 by design）：等 F0 断链收编后合并归属。
3. **feishu.yaml classification.rules 与 creator_patterns.json 的读取逻辑收编**（P2）：注册表已提供 aliases 单一落点，两处旧配置仍独立生效。
4. maodaren/9you 的 style_label/specialties/markets 标「待补」，需人工标注；trader_ji 的 style_label 拟定值待人工复核。
5. legacy `/kol` 页 masthead 如需 alias 级归并（非精确匹配），需产品决策后另行接线。
