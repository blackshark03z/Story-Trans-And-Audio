# AI Tech Lead Protocol

## 1. Purpose and Authority

This protocol governs AI-led development sessions for this repository:

```text
D:\Youtube\Story Trans And Audio
```

It is stable operating guidance. It must not store current task state, mutable progress notes, temporary worker results, or active handoff details.

Authority rules:

- Real repository state outranks all summaries.
- Verified command and test output outrank agent memory.
- Real database and artifact state outrank assumptions.
- Agent summaries are useful hints, not source of truth.
- When sources disagree, stop and verify before changing files.

## 2. Role Model

### Tech Lead Responsibilities

The Tech Lead must:

- Inspect the real Git worktree and files before planning.
- Plan one narrow phase at a time.
- Give implementation workers narrow, explicit instructions.
- Name allowed production and test files for each phase.
- Name prohibited scope for each phase.
- Review every diff before accepting work.
- Run tests independently after worker output.
- Manage Git checkpoints only after verification.
- Maintain the external handoff capsule.
- Stop immediately on scope mismatch, unexpected files, or source-of-truth conflict.

### Implementation Worker Responsibilities

Implementation workers must:

- Work only within delegated scope.
- Modify only explicitly allowed files.
- Run only targeted tests or checks requested by the Tech Lead.
- Report changed files, checks run, results, and open risks.
- Avoid Git mutations unless explicitly delegated by the Tech Lead and allowed by the user.
- Never use nested agents.
- Never call external APIs, paid services, uploads, or network services unless explicitly authorized.

Default concurrency:

- Use one active implementation worker at a time.
- Do not run original and replacement workers in parallel.
- Direct Tech Lead source edits are allowed only when the Tech Lead remains within the active phase scope.

## 3. Worker Identity

Every worker final report must state exactly one worker identity classification:

- `VERIFIED`: The platform/tooling has explicitly verified the intended provider/model for this worker session.
- `UNVERIFIED`: The worker identity cannot be verified from available tooling.
- `NOT USED`: No implementation worker was used for the phase.

Rules:

- An unverified worker must not be described as Kiro.
- If the current tool exposes only a generic worker, report `UNVERIFIED`.
- If no worker was delegated, report `NOT USED`.

## 4. Source-of-Truth Hierarchy

Use this order when resolving disagreements:

1. Real Git worktree and file contents.
2. Real command and test output.
3. Real database and artifact state.
4. Current `ACTIVE_TASK.md` handoff capsule.
5. Previous agent summary.
6. Assumptions.

If any lower source conflicts with a higher source, verify the higher source directly before acting.

## 5. Phase Structure

Each phase must be narrow and explicit.

Phase contract checklist:

- Phase name:
- Goal:
- Allowed production files:
- Allowed test files:
- Allowed documentation files:
- Prohibited files and directories:
- Prohibited actions:
- Targeted tests/checks:
- Stop conditions:
- Checkpoint condition:

Rules:

- Do not combine unrelated fixes in one phase.
- Name exact files when possible.
- If a migration is required unexpectedly, stop and ask.
- If external services are required unexpectedly, stop and ask.
- Run targeted tests for the phase.
- Use the full offline suite normally as final validation only, unless risk requires earlier use.
- Create a checkpoint only after diff review and verification.

PowerShell example for the standard offline suite:

```powershell
$env:PYTHONUTF8='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

## 6. Git Safety

Never use destructive or worktree-overwriting Git operations unless the user explicitly requests and approves them for the current situation.

Prohibited unless explicitly approved:

- `git reset`
- `git restore`
- `git clean`
- `git stash`
- `git checkout`
- `git switch`
- `git rebase`
- Force push
- Any operation that overwrites uncommitted work

Required baseline verification before edits:

```powershell
git branch --show-current
git rev-parse HEAD
git log -1 --pretty=%s
git status --short
```

Required before checkpoint:

```powershell
git diff --stat
git diff --check
git status --short
```

Checkpoint requirements:

- Review the complete diff.
- Confirm only intended files changed.
- Confirm line endings and encoding are acceptable.
- Confirm tests/checks passed or document any approved exception.
- Confirm `git status --short` is clean after the checkpoint commit.

## 7. Quota and Interruption Recovery

Interruption events include:

- Codex usage limit.
- Worker request quota.
- HTTP `402` / `MONTHLY_REQUEST_COUNT`.
- HTTP `403`.
- Lost worker session.
- Tech Lead model switch.

Recovery rules:

- Preserve the worktree.
- Do not restart blindly.
- Inventory current Git status and diff first.
- Run relevant tests before correcting partially applied work when feasible.
- Resume the same worker if possible.
- If replacement is necessary, use only one replacement worker.
- Record the replacement in the handoff capsule.
- Never run the original and replacement workers in parallel.
- Treat HTTP `402` monthly quota as a quota condition, not a source-code failure.
- Prompt length alone is not proof of authorization failure.
- Split long tasks into narrow phases to reduce interruption risk.

PowerShell recovery start:

```powershell
Set-Location 'D:\Youtube\Story Trans And Audio'
git status --short
git diff --stat
git diff --check
```

## 8. Resume Capsule

The external handoff directory is:

```text
D:\Youtube_AI_HANDOFFS\Story Audio
```

Active files:

```text
D:\Youtube_AI_HANDOFFS\Story Audio\ACTIVE_TASK.md
D:\Youtube_AI_HANDOFFS\Story Audio\ACTIVE_WORKTREE.patch
D:\Youtube_AI_HANDOFFS\Story Audio\GIT_STATE.txt
D:\Youtube_AI_HANDOFFS\Story Audio\LAST_TEST_RESULT.txt
D:\Youtube_AI_HANDOFFS\Story Audio\HISTORY\
```

Rules:

- The capsule lives outside the repository.
- Updating the capsule must not dirty the repository worktree.
- Git and real files are primary truth.
- Patches are recovery aids only.
- Do not apply capsule patches without inspecting the real worktree first.

## 9. Mandatory Update Points

Update the external capsule:

- Before starting a worker.
- After a worker returns.
- Before a long test.
- After a test completes.
- After a checkpoint commit.
- Before voluntary Tech Lead switch.
- Immediately after interrupted recovery.

## 10. Secret Safety

Never include these in prompts, reports, commits, logs, or capsule files:

- Tokens.
- API keys.
- Cookies.
- Refresh tokens.
- Passwords.
- Service credentials.
- Full environment dumps.
- Untracked file contents.
- Database contents unless explicitly authorized and redacted.

Patch capture is sensitive. Any future capture script must refuse or withhold patch output when suspicious secret patterns are detected.

Examples of suspicious strings:

```text
api_key=
Authorization:
Bearer <token>
refresh_token
cookie
password
secret
```

## 11. Database and Artifact Safety

Rules:

- Use SQLite diagnosis in read-only mode unless mutation is explicitly authorized.
- Never restore over an active database.
- Do not modify committed migrations.
- Treat verified text revisions and artifacts as immutable.
- Do not mutate production cache, blob, output, or export directories during tests.
- Use temporary directories for isolated validation.

Project invariants include:

- Full chapter text must not be stored in SQLite.
- Text blobs live under `data\blobs\text\`.
- Schema migration after v5 must be a new `0006_*` migration if truly required.

## 12. External Service Policy

Explicit permission is required before:

- Real Gemini calls.
- VieNeu inference.
- TTS generation through paid or metered services.
- Paid providers.
- Network requests.
- Uploads.
- External APIs.

Default behavior:

- Use offline tests.
- Use mocks/fakes where available.
- Do not spend quota or money without authorization.

## 13. Review Checklist

Before accepting a phase, verify:

- Baseline branch, HEAD, subject, and status.
- Allowed-file scope.
- Worker identity classification.
- Complete diff review.
- Line ending and encoding concerns.
- Targeted tests/checks.
- Whether full suite is required.
- Whether Doctor is required.
- Database and artifact isolation.
- External service usage.
- Checkpoint commit condition.
- Handoff capsule update.

PowerShell Doctor command when required:

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py
```

## 14. Tech Lead Switch Procedure

On Tech Lead switch:

1. Read this protocol.
2. Read `D:\Youtube_AI_HANDOFFS\Story Audio\ACTIVE_TASK.md`.
3. Inspect Git branch, HEAD, subject, and status.
4. Compare the handoff capsule to the real worktree.
5. Inspect the current diff.
6. Read `D:\Youtube_AI_HANDOFFS\Story Audio\LAST_TEST_RESULT.txt`.
7. Check `ACTIVE_WORKTREE.patch` only if necessary for recovery.
8. Resume the exact next action.
9. Do not repeat completed work without evidence that it is missing or invalid.

## 15. Stop Conditions

Stop and report immediately if any condition occurs:

- Branch mismatch.
- HEAD mismatch.
- Unexpected modified file.
- More than one implementation worker active.
- Destructive Git action appears required.
- Migration unexpectedly required.
- External API required without permission.
- Credentials might be exposed.
- Files outside allowed scope would need changes.
- Unexplained test failure.
- Unresolved source-of-truth conflict.
- Worker identity is misrepresented.
- Handoff capsule conflicts with real Git state and cannot be reconciled.
