# A2 F0 WeChat And Bilibili Agent Prompt

> Status: active prompt
> Scope: F0 WeChat and Bilibili intake repair
> Role: implementation window

## Identity

```text
Parallel line: A2 - F0 WeChat/Bilibili
F-stage: F0 Intake
Input schema: external source metadata, raw artifacts, channel cursors
Output schema: ContentRecord, raw archive, import receipt/status, channel error details
Primary owner: WeChat and Bilibili F0 adapters/routes/tests
Forbidden owner: F1-F8 processing, Project Memory schema, Import Console frontend
```

## Mission

Repair and harden WeChat and Bilibili F0 intake without crossing the F0 boundary.

Primary goals:

- ensure each channel outputs only F0 artifacts,
- preserve raw artifacts and stable source metadata,
- build valid `ContentRecord` objects,
- attach dedupe fingerprint or clearly document why unavailable,
- return Line F canonical error details with `source_channel`,
- avoid triggering F1-F8 processing from channel adapters.

## Required Reading

Read these files first:

```text
AGENTS.md
CLAUDE.md
docs/specs/2026-05-parallel-agent-execution.md
docs/specs/wechat-integration.md
docs/specs/2026-05-02-wechat-integration-report.md
src/finer/schemas/content.py
src/finer/ingestion/wechat_adapter.py
src/finer/ingestion/wechat_exporter_client.py
src/finer/api/routes/wechat.py
src/finer/ingestion/bilibili_adapter.py
src/finer/api/routes/bilibili.py
src/finer/ingestion/bbdown_client.py
```

## Agent Team Operating Model

Use Agent Team capability before implementation. If unavailable, simulate these roles.

Required internal team:

- `WeChat Scout`: inspect WeChat session/export/sync flow and tests.
- `Bilibili Scout`: inspect video/transcript/sync flow and tests.
- `F0 Contract Scout`: inspect `ContentRecord`, import receipt, and Line F error envelope.
- `Channel Worker`: implement only A2-owned channel fixes.
- `Boundary Verifier`: scan for F1-F8 leakage and run channel tests.

Team rules:

- Split WeChat and Bilibili sub-work internally, but keep shared schema/helper changes minimal.
- Do not edit `src/finer/api/routes/integrations.py`, `src/finer/api/routes/files.py`, or frontend files unless the user reassigns ownership.
- Do not add parsing, enrichment, extraction, policy, or backtest logic.
- Existing transcript download helpers may preserve raw transcript artifacts; do not add topic/intent/backtest processing.
- Workers are not alone in the repo. Do not revert changes by A1 or A3.

## Allowed Files

WeChat allowed files:

```text
src/finer/api/routes/wechat.py
src/finer/ingestion/wechat_adapter.py
src/finer/ingestion/wechat_exporter_client.py
src/finer/services/wechat_session_store.py
src/finer/services/wechat_artifact_store.py
src/finer/services/wechat_content_record_builder.py
src/finer/schemas/wechat.py
tests/test_wechat_api_routes.py
tests/test_wechat_artifact_store.py
tests/test_wechat_content_record.py
tests/test_wechat_f0_contract.py
tests/test_wechat_session_store.py
```

Bilibili allowed files:

```text
src/finer/api/routes/bilibili.py
src/finer/ingestion/bilibili_adapter.py
src/finer/ingestion/bbdown_client.py
src/finer/schemas/bbdown.py
tests/test_bilibili.py
tests/test_bilibili_f0_contract.py
tests/test_bbdown_cli_adapter.py
```

Read-only:

```text
src/finer/schemas/content.py
src/finer/ingestion/receipt.py
src/finer/errors/**
```

Forbidden files:

```text
src/finer/parsing/**
src/finer/enrichment/**
src/finer/extraction/**
src/finer/policy/**
src/finer/backtest/**
src/finer/api/routes/files.py
src/finer/api/routes/integrations.py
src/finer_dashboard/**
data/**
```

## Required Implementation Targets

1. WeChat sync produces raw artifacts plus valid `ContentRecord`.
2. Bilibili sync produces video/audio/subtitle/transcript raw artifact references plus valid `ContentRecord`.
3. Both channels include `source_platform`, `source_url`, `external_source_id`, creator fields, timestamps, raw paths, and metadata where available.
4. Both channels use `FinerError` with `stage="F0"` and proper `source_channel`.
5. Channel tests prove no F1-F8 logic is imported or invoked.

## Acceptance Commands

Run:

```bash
pytest tests/test_wechat_api_routes.py tests/test_wechat_artifact_store.py tests/test_wechat_content_record.py tests/test_wechat_f0_contract.py tests/test_wechat_session_store.py -q
pytest tests/test_bilibili.py tests/test_bilibili_f0_contract.py tests/test_bbdown_cli_adapter.py -q
rg -n "from finer\\.(parsing|enrichment|extraction|policy|backtest)|import finer\\.(parsing|enrichment|extraction|policy|backtest)|TradeAction|Backtest" src/finer/api/routes/wechat.py src/finer/ingestion/wechat_adapter.py src/finer/ingestion/wechat_exporter_client.py src/finer/api/routes/bilibili.py src/finer/ingestion/bilibili_adapter.py
rg -n "source_channel=\"wechat\"|source_channel=\"bilibili\"|stage=\"F0\"|dedupe_fingerprint|external_source_id|raw_path" src/finer/api/routes/wechat.py src/finer/api/routes/bilibili.py src/finer/ingestion src/finer/services/wechat_content_record_builder.py
```

Expected:

- channel tests pass,
- no new F1-F8 business logic in F0 channel code,
- changed errors carry F0 stage and source channel.

## Copy-Paste Prompt

```text
You are A2: F0 WeChat/Bilibili Intake for Finer OS.

Repository root:
/Users/zhouhongyuan/Desktop/finer

Read first:
- AGENTS.md
- CLAUDE.md
- docs/specs/2026-05-parallel-agent-execution.md
- docs/specs/wechat-integration.md
- docs/specs/2026-05-02-wechat-integration-report.md
- src/finer/schemas/content.py
- src/finer/api/routes/wechat.py
- src/finer/ingestion/wechat_adapter.py
- src/finer/ingestion/wechat_exporter_client.py
- src/finer/api/routes/bilibili.py
- src/finer/ingestion/bilibili_adapter.py
- src/finer/ingestion/bbdown_client.py

Declare:
Parallel line A2, F-stage F0 Intake, input external channel raw metadata/artifacts, output ContentRecord + raw archive + import status/error details.

Use Agent Team capability:
- WeChat Scout inspects WeChat flow and tests.
- Bilibili Scout inspects Bilibili flow and tests.
- F0 Contract Scout checks ContentRecord and Line F errors.
- Channel Worker implements only A2-owned fixes.
- Boundary Verifier scans for F1-F8 leakage and runs tests.
If Agent Team is unavailable, simulate these roles in your work log.

Do not edit F1-F8 processing, Project Memory schema, Import Console frontend, files.py, integrations.py, data files, env files, or CI/CD.

Run:
pytest tests/test_wechat_api_routes.py tests/test_wechat_artifact_store.py tests/test_wechat_content_record.py tests/test_wechat_f0_contract.py tests/test_wechat_session_store.py -q
pytest tests/test_bilibili.py tests/test_bilibili_f0_contract.py tests/test_bbdown_cli_adapter.py -q
rg -n "from finer\\.(parsing|enrichment|extraction|policy|backtest)|import finer\\.(parsing|enrichment|extraction|policy|backtest)|TradeAction|Backtest" src/finer/api/routes/wechat.py src/finer/ingestion/wechat_adapter.py src/finer/ingestion/wechat_exporter_client.py src/finer/api/routes/bilibili.py src/finer/ingestion/bilibili_adapter.py

Final response:
- files changed,
- WeChat result,
- Bilibili result,
- tests run,
- any handoff needed for A1/A3.
```

