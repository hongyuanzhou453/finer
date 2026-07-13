# Audit Trace Backend API — Implementation Notes

Date: 2026-06-04

## Summary

The Audit Trace backend now exposes read-only API endpoints for the dashboard `/audit` page:

- `GET /api/audit/actions`
- `GET /api/audit/actions/{trade_action_id}/trace`

The implementation is a cross-stage read-only aggregator. It does not run F-stage pipeline code, mutate artifacts, change schemas, or update frontend contracts.

## Data Sources And Cache

The API reads canonical golden-path artifacts by ID:

- F5: `data/F5_executed/{trade_action_id}.json`
- F3: `data/F3_intents/{intent_id}.json`
- F4: `data/F4_policy_mapped/{policy_id}.json`
- F2/F1 context: `data/F2_anchored/{envelope_id}.json`, when present

The list endpoint builds a lazy TTL index from F5 files. The cached index stores list-ready projection fields, including materialized trace status and KOL id, so repeated list calls do not re-read F3/F4 files per action. Single-action trace requests still read linked F3/F4/F2 files to assemble the full bundle.

Files named `*_actions.json` under `data/F5_executed` are explicitly skipped. Those files are batch wrapper outputs from older extraction routes (`{"source_file", "actions": [...]}`), not canonical single `TradeAction` artifacts, and including them would mix producer semantics in the audit list.

## Error Envelope

Unknown `trade_action_id` returns the canonical Finer error envelope with:

- `code=API_NTF_001`
- `stage=F5_audit`
- `operation=get_trace`
- `retryable=false`
- `request_id` injected by the FastAPI error handler
- a route-specific `fix_hint`

Sensitive detail keys such as token, secret, password, cookie, authorization, and api_key are not added by the route.

## Evidence MVP Status

`AuditTraceBundle.evidence_spans` intentionally returns `[]` in this implementation.

This means the API currently has no stable F2 `EvidenceSpan` body to load. It does not mean the action lacks `evidence_span_ids`, nor does it mean the source action lacks `source.evidence_text`. The dashboard should treat the empty array as an MVP limitation of the F2 evidence materialization layer.

Future options:

- Add a golden-path evidence sidecar such as `data/F2_anchored/{envelope_id}.evidence.json` and filter it by `TradeAction.evidence_span_ids`.
- Implement the F2 EvidenceResolver as the canonical producer of EvidenceSpan bodies.

Both options are outside the current backend-only follow-up scope because they change pipeline or F2 production behavior.

## Operational Notes

Current production-like data directories may be empty until `run_golden_path()` or an equivalent canonical producer is run. Empty canonical directories yield an empty audit action list by design.

Validation commands used for this implementation:

```bash
pytest tests/test_audit_api.py -v
pytest tests/test_errors.py tests/test_golden_path.py -q
```
