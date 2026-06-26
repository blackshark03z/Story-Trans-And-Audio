# AI Active Task Template

Copy this template to:

```text
D:\Youtube_AI_HANDOFFS\Story Audio\ACTIVE_TASK.md
```

This is mutable task state. Do not store active task state in `docs\AI_TECH_LEAD_PROTOCOL.md`.

## 1. Capsule Metadata

- Status: `<NOT_STARTED | IN_PROGRESS | BLOCKED | READY_FOR_REVIEW | COMPLETE>`
- Updated timestamp: `<YYYY-MM-DD HH:MM:SS TZ>`
- Updated by: `<Tech Lead name/session>`
- Tech Lead model: `<provider/model or UNVERIFIED>`
- Repository: `D:\Youtube\Story Trans And Audio`
- Current task: `<short task title>`
- Current phase: `<phase name and number>`

## 2. Worker Contract

- Intended provider/model: `<provider/model or none>`
- Identity classification: `<VERIFIED | UNVERIFIED | NOT USED>`
- Session id: `<worker session id or N/A>`
- One worker at a time: `<YES | NO>`
- Direct Tech Lead source edits allowed: `<YES | NO; scope>`
- Allowed files:
  - `<path 1>`
  - `<path 2>`
- Prohibited files/actions:
  - `<path/action 1>`
  - `<path/action 2>`
- Nested agents allowed: `NO`
- Git mutations allowed for worker: `<NO unless explicitly delegated>`
- External APIs allowed: `<NO unless explicitly authorized>`

## 3. Git Baseline

- Branch: `<expected branch>`
- Expected HEAD: `<full commit SHA>`
- Subject: `<git log -1 --pretty=%s>`
- Last verified clean commit: `<full commit SHA or N/A>`
- Expected worktree state: `<clean | known dirty with listed files>`
- Actual modified files:
  - `<file or none>`
- Unexpected files:
  - `<file or none>`
- Diff stat:

```text
<git diff --stat output>
```

- Line-ending/encoding concerns:
  - `<none or details>`

## 4. Completed Work

### Investigation

- `<what was inspected>`

### Implementation

- `<what changed>`

### Verified Invariants

- `<invariant checked>`

### Tests Run

| Command | Result | Count | Notes |
| --- | --- | --- | --- |
| `<command>` | `<pass/fail/skipped>` | `<count or N/A>` | `<notes>` |

### Diff Review

- Reviewed by: `<actor>`
- Files reviewed:
  - `<file>`
- Issues found:
  - `<none or details>`

### Checkpoint Commits

| Commit | Subject | Verification |
| --- | --- | --- |
| `<SHA or N/A>` | `<subject>` | `<tests/checks>` |

## 5. Current Work In Progress

- Function/component: `<name or N/A>`
- Test added/corrected: `<test name or N/A>`
- Partial work to preserve:
  - `<file/section or none>`
- Incomplete implementation:
  - `<details or none>`
- Failing tests:
  - `<test or none>`
- Traceback:

```text
<traceback or none>
```

- Worker response status: `<not started | running | returned | lost | quota blocked | failed>`

## 6. Current Decisions

- Architecture decisions:
  - `<decision or none>`
- Scope decisions:
  - `<decision or none>`
- Rejected approaches:
  - `<approach and reason or none>`
- Migration decision:
  - `<not required | required and approved | required but stopped>`
- External-service decision:
  - `<not required | authorized | required but stopped>`

## 7. Commands Already Executed

Use this repeatable format for each command.

### Command `<number>`

- Command:

```powershell
<exact command>
```

- CWD: `<absolute path>`
- Result: `<pass | fail | interrupted | skipped>`
- Duration: `<duration or unknown>`
- External calls: `<none or details>`
- Artifacts modified: `<none or details>`
- Notes:
  - `<important output summary>`

## 8. Next Exact Action

1. First command:

```powershell
<exact command to run next>
```

2. Expected result:
   `<expected output/status>`

3. Correction decision:
   `<what to do if expected result differs>`

4. Commit condition:
   `<exact conditions required before checkpoint commit>`

5. Next update point:
   `<when to update this capsule again>`

## 9. Stop Conditions

Protocol stop conditions:

- Branch mismatch.
- HEAD mismatch.
- Unexpected modified file.
- More than one implementation worker active.
- Destructive Git action required.
- Migration unexpectedly required.
- External API required without permission.
- Credentials might be exposed.
- Files outside allowed scope would need changes.
- Unexplained test failure.
- Unresolved source-of-truth conflict.

Task-specific stop conditions:

- `<condition 1>`
- `<condition 2>`

## 10. Final Report Contract

The final report must include:

- Ending status: `<complete | blocked | partial>`
- Worker identity classification: `<VERIFIED | UNVERIFIED | NOT USED>`
- Files changed:
  - `<file>`
- Checkpoint subject: `<commit subject or no commit>`
- Required targeted tests:
  - `<command/result>`
- Full suite required: `<YES | NO; reason>`
- Doctor required: `<YES | NO; reason>`
- External APIs used: `<none or details>`
- Database/artifact writes: `<none or details>`
- Open questions:
  - `<question or none>`

## 11. Secret and Safety Confirmation

Check every item before checkpoint or final report:

- [ ] No tokens, API keys, cookies, refresh tokens, passwords, or credentials included.
- [ ] No full environment dumps included.
- [ ] No untracked file contents included.
- [ ] No production database writes performed.
- [ ] No production cache/blob/output/export mutation performed.
- [ ] No external API calls made unless explicitly authorized.
- [ ] No destructive Git operations performed.
- [ ] No files outside allowed scope modified.

## 12. Capsule Update Log

Append one row for each capsule update.

| Timestamp | Actor | Event | Git HEAD | Worktree Status | Next Action |
| --- | --- | --- | --- | --- | --- |
| `<YYYY-MM-DD HH:MM:SS TZ>` | `<name/session>` | `<event>` | `<SHA>` | `<clean/dirty summary>` | `<next action>` |
