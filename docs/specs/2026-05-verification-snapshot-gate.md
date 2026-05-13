# 2026-05 Verification Snapshot Gate

> Status: active gate spec
> Created: 2026-05-12
> Scope: Line V read-only verification snapshot for Finer OS parallel work
> Canonical architecture: F0-F8 only

## 1. Mission

Line V creates a current-state baseline before implementation agents start or continue parallel work.

The gate agent must:

- run the agreed core checks,
- confirm package manifest and lockfile consistency,
- list deprecated-path, mock-data, contract-only, and `NotImplementedError` gaps,
- identify ownership conflicts for upcoming agents,
- produce a concise baseline report.

The gate agent must not edit source code, docs, tests, package files, data, git history, or environment files.

## 2. Agent Identity

```text
Parallel line: V — Verification Snapshot
F-stage: cross-stage read-only verification
Input schema: repository state, AGENTS.md, CLAUDE.md, docs/specs/*, tests, package manifests
Output schema: markdown baseline report in final response only
Allowed files: read-only access to repository files
Forbidden files: all writes, all deletions, all migrations, all generated commits
```

## 3. Read-Only Boundary

Allowed behavior:

- read files,
- run tests,
- run build/type-check commands,
- run `rg`, `git status`, `git diff`, `git log`, `npm` read/verify commands,
- report findings with file and line references,
- recommend next agent ownership.

Forbidden behavior:

- no `apply_patch`,
- no source/doc/test/package edits,
- no file deletion or cleanup,
- no git stage/commit/push/rebase/reset,
- no database schema creation, migration, rebuild, or data mutation,
- no `.env`, token, CI/CD, or system config changes,
- no attempt to fix failures.

Test/build commands may create local caches or ignored build artifacts. The gate agent must not stage, delete, or clean those artifacts; it must report any tracked file changes observed after verification.

## 4. Required Checks

### Check 1. Repository State

Commands:

```bash
pwd
git branch --show-current
git log --oneline -5
git status --short
git diff --name-only
git diff -- src/finer_dashboard/package.json src/finer_dashboard/package-lock.json
```

Report:

- branch,
- latest commit,
- tracked modified files,
- untracked files/directories,
- whether any active worktree changes could conflict with planned agents.

### Check 2. Core Backend Test Baseline

Commands:

```bash
pytest tests/test_errors.py tests/test_f0_project_memory.py tests/test_f0_contract.py tests/test_wechat_f0_contract.py tests/test_bilibili_f0_contract.py -q
pytest tests/test_canonical_f3_f4_f5_contract.py tests/test_canonical_action_builder.py tests/test_intent_extractor_canonical.py tests/test_policy_mapper.py tests/test_execution_timing_policy.py -q
pytest tests/test_backtest.py tests/test_backtest_extended.py -q
```

Report:

- pass/fail for each command,
- total tests run when visible,
- first failing test and error summary if a command fails,
- warnings only when they affect future implementation risk.

### Check 3. Frontend Build And Lockfile Baseline

Commands:

```bash
cd src/finer_dashboard && npm run build
cd src/finer_dashboard && node - <<'NODE'
const fs = require("fs");
const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
const root = lock.packages && lock.packages[""] ? lock.packages[""] : {};
const pkgDeps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
const lockDeps = { ...(root.dependencies || {}), ...(root.devDependencies || {}) };
const missing = Object.keys(pkgDeps).filter((name) => !(name in lockDeps));
const extra = Object.keys(lockDeps).filter((name) => !(name in pkgDeps));
const mismatched = Object.keys(pkgDeps).filter((name) => lockDeps[name] && lockDeps[name] !== pkgDeps[name]);
console.log(JSON.stringify({ missing, extra, mismatched }, null, 2));
if (missing.length || mismatched.length) process.exit(1);
NODE
```

Report:

- build pass/fail,
- whether `package-lock.json` root dependencies match `package.json`,
- any package diff currently present.

### Check 4. Gap Scan

Commands:

```bash
rg -n "extract_from_text\\(|contract only|NotImplementedError|mock|hard-coded|hardcoded|sampleData|demoData|fallback_to_mock|legacy" src/finer src/finer_dashboard/src tests docs/specs
rg -n "data/[A-Z][0-9]_|[A-Z][0-9]_metrics|DEFAULT_STAGES|stage_results|stages_completed" src/finer src/finer_dashboard/src tests docs/specs
rg -n "return \\{.*\"error\"|HTTPException\\(status_code=.*detail=\"" src/finer/api/routes src/finer/ingestion
rg -n "request_id|fix_hint|retryable|source_channel|stage" src/finer src/finer_dashboard/src
```

Classify findings into:

- **Blocking**: prevents Line B/C/D agents from starting safely.
- **High**: must be handled before MVP acceptance.
- **Medium**: should be assigned to a focused agent but does not block current wave.
- **Low**: test-only, doc-only, known compatibility path, or acceptable temporary fallback.

Report only high-signal findings. Do not paste full `rg` output.

### Check 5. Ownership Conflict Map

Inspect current modified files and planned agent surfaces.

Report which agents can safely run in parallel:

- `B1` KOL fixture and end-to-end smoke,
- `C1` canonical runner,
- `D1` F8 backend API,
- `D2` F8 frontend API adapter,
- `A1` F0 Project Memory implementation only after user confirms SQLite schema,
- `F` focused error verification/fixes.

For each, report:

- files likely owned,
- known conflict files,
- prerequisite checks,
- whether it can start now.

## 5. Output Format

The final response must use this structure:

```markdown
## Verification Snapshot

Date: YYYY-MM-DD
Branch: <branch>
Head: <short-sha> <subject>

### Gate Result
PASS | WARN | BLOCKED

### Command Results
| Check | Command | Result | Notes |
|---|---|---|---|

### Current Worktree
- Tracked changes:
- Untracked files:
- Package lock status:

### Findings
| Severity | Area | Finding | Evidence | Recommended owner |
|---|---|---|---|---|

### Parallel Readiness
| Agent | Can start? | Reason | Conflict files |
|---|---|---|---|

### Next Actions
1. ...
2. ...
3. ...
```

Gate result rules:

- `PASS`: all required tests/build pass, lockfile is consistent, no blocking worktree conflicts.
- `WARN`: tests/build pass but there are known high/medium implementation gaps.
- `BLOCKED`: required tests/build fail, package lock is inconsistent, or current modified files overlap with the next implementation wave in a way that could cause overwrite risk.

## 6. Copy-Paste Prompt

Use this prompt when assigning the Line V gate agent:

```text
You are Line V: Verification Snapshot Gate for the Finer OS repository.

You are a read-only verification agent. Your job is to freeze the current project baseline before implementation agents continue parallel work.

Repository root:
/Users/zhouhongyuan/Desktop/finer

Mandatory rules:
- Read AGENTS.md, CLAUDE.md, and docs/specs/2026-05-parallel-agent-execution.md before running checks.
- Declare: parallel line V, F-stage cross-stage verification, input repository state, output markdown baseline report.
- Do not edit any file. Do not call apply_patch. Do not create, delete, rename, stage, commit, push, rebase, reset, migrate, or clean files.
- Do not modify .env, tokens, CI/CD config, database schema, package manifests, lockfiles, or data.
- Running tests/builds is allowed. If they produce local caches or build artifacts, do not clean them. Report any tracked file changes after verification.
- If a command fails, capture the exit code and concise failure summary, then continue with the remaining checks when safe.
- Do not fix anything. Report findings and recommended owners only.

Required checks:
1. Repository state:
   pwd
   git branch --show-current
   git log --oneline -5
   git status --short
   git diff --name-only
   git diff -- src/finer_dashboard/package.json src/finer_dashboard/package-lock.json

2. Backend core tests:
   pytest tests/test_errors.py tests/test_f0_project_memory.py tests/test_f0_contract.py tests/test_wechat_f0_contract.py tests/test_bilibili_f0_contract.py -q
   pytest tests/test_canonical_f3_f4_f5_contract.py tests/test_canonical_action_builder.py tests/test_intent_extractor_canonical.py tests/test_policy_mapper.py tests/test_execution_timing_policy.py -q
   pytest tests/test_backtest.py tests/test_backtest_extended.py -q

3. Frontend build and lock consistency:
   cd src/finer_dashboard && npm run build
   cd src/finer_dashboard && node - <<'NODE'
   const fs = require("fs");
   const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
   const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
   const root = lock.packages && lock.packages[""] ? lock.packages[""] : {};
   const pkgDeps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
   const lockDeps = { ...(root.dependencies || {}), ...(root.devDependencies || {}) };
   const missing = Object.keys(pkgDeps).filter((name) => !(name in lockDeps));
   const extra = Object.keys(lockDeps).filter((name) => !(name in pkgDeps));
   const mismatched = Object.keys(pkgDeps).filter((name) => lockDeps[name] && lockDeps[name] !== pkgDeps[name]);
   console.log(JSON.stringify({ missing, extra, mismatched }, null, 2));
   if (missing.length || mismatched.length) process.exit(1);
   NODE

4. Gap scans:
   rg -n "extract_from_text\\(|contract only|NotImplementedError|mock|hard-coded|hardcoded|sampleData|demoData|fallback_to_mock|legacy" src/finer src/finer_dashboard/src tests docs/specs
   rg -n "data/[A-Z][0-9]_|[A-Z][0-9]_metrics|DEFAULT_STAGES|stage_results|stages_completed" src/finer src/finer_dashboard/src tests docs/specs
   rg -n "return \\{.*\"error\"|HTTPException\\(status_code=.*detail=\"" src/finer/api/routes src/finer/ingestion
   rg -n "request_id|fix_hint|retryable|source_channel|stage" src/finer src/finer_dashboard/src

5. Ownership readiness:
   Evaluate whether B1, C1, D1, D2, A1, and F agents can start now.
   For each, list likely owned files, conflict files, prerequisite checks, and readiness.

Final report format:
## Verification Snapshot
Date: 2026-05-12
Branch: <branch>
Head: <short-sha> <subject>

### Gate Result
PASS | WARN | BLOCKED

### Command Results
| Check | Command | Result | Notes |
|---|---|---|---|

### Current Worktree
- Tracked changes:
- Untracked files:
- Package lock status:

### Findings
| Severity | Area | Finding | Evidence | Recommended owner |
|---|---|---|---|---|

### Parallel Readiness
| Agent | Can start? | Reason | Conflict files |
|---|---|---|---|

### Next Actions
1. ...
2. ...
3. ...

Keep the report concise. Include file:line evidence for important findings. Do not paste full command output unless it is a failure summary.
```
