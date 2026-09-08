# Story Audio Finish Product

## Outcome

Converge the existing Story Audio capabilities into one natural daily-production
product journey. This is one product Goal and ends only at owner acceptance,
owner action required for a protected production effect, or a proven product
capability blocker.

## CADS current Goal contract

- **Goal:** Converge the existing Story Audio capabilities into one usable daily
  production flow that reaches final downloadable audio through the supported UI.
- **Critical User Journey (CUJ):** select Book/chapter range → inspect/fix text and
  speaker identity → review characters and voices with dialogue context → approve
  casting/settings → PREPARE → explicit START_RENDER → monitor → listen/repair →
  Human QA → download → close the completed production context → start the next
  production range without leaking Job/range state from the completed run.
- **Acceptance Fixture / Golden Input:** canonical runtime `127.0.0.1:8772`, Book 1
  `Quang Âm Chi Ngoại`, contiguous Chapters 2–8. Owner real-use resumes this same
  fixture after each blocker instead of starting a new Goal.
- **Acceptance:** the Owner can complete the full CUJ without DevTools, manual DB
  edits, hidden endpoints, or knowledge of backend terminology; every successful
  action exposes one valid next action; speaker/voice review exposes the actual
  assigned dialogue and local context before a voice decision; final audio is
  playable, reviewable and downloadable. After COMPLETE the Owner can start a
  new production range directly; completed Job/artifact/casting snapshots remain
  immutable, while persistent book/character voice configuration is clearly
  presented as input for future PREPARE/render rather than as mutation of old audio.
- **Non-goals:** no parallel orchestration/framework subsystem, no unrelated repo
  cleanup, no generalized policy engine for a local defect, and no provider-cost
  action merely to prove engineering progress.
- **Constraints:** canonical data and immutable product records remain protected;
  PREPARE and START_RENDER stay separate and explicit; owner/provider-cost/Human
  QA authority is preserved; one authoritative product path only.
- **Material owner decisions:** Owner acceptance is the final oracle. Job #35 was
  intentionally cancelled during owner testing to revisit speaker/voice choices;
  this is part of the same golden journey, not a new Goal.
- **Knowledge-gap responsibility:** the AI Tech Lead must discover and resolve
  ordinary engineering gaps from source/runtime evidence without delegating
  technical diagnosis to the Owner. Ask the Owner only for product facts,
  material trade-offs, consequential authorization, or subjective real-use
  acceptance that cannot reasonably be inferred.
- **Journey evidence rule:** isolated feature/subsystem PASS results are checkpoint
  evidence only. The complete Book -> voice/text review -> save -> PREPARE ->
  explicit START_RENDER -> progress -> listen/repair -> QA/download composition
  remains `UNVERIFIED` until representative end-to-end evidence exists on the
  supported UI and the Owner has completed subjective real-use acceptance.

### CADS event routing for this Goal

Normal work uses Goal Execution. Any owner-test defect temporarily enters
Systematic Debugging for the first CUJ blocker, then returns immediately to the
same Chapters 2–8 journey. Use Product Acceptance only when the predefined CUJ
appears complete. Tests and commits are `CHECKPOINT_OK` evidence, never product
acceptance by themselves. Cleanup belongs to Workspace Hygiene only after Goal
closure or when disk/worktree pressure directly blocks this Goal.

## Delivery and boundaries

- Delivery delta: `USER_VISIBLE_BEHAVIOR`.
- Risk/state floor: `R2 / S3` because the UI coordinates immutable revisions,
  explicit production commands, and background Job progress.
- Reuse, wire, or replace-and-delete only. Do not add a parallel subsystem.
- Allowed: the current product UI, the smallest blocking API/domain correction,
  focused/regression/browser tests, and this active work record.
- Prohibited without separate owner authority: Gemini, VieNeu/TTS, provider-cost
  actions, canonical DB mutation, Human QA decisions, PREPARE, START_RENDER,
  push, merge, deployment, and protected-root changes.
- Authoritative state: existing API/domain projections backed by the configured
  database. Representative transition: casting approved -> PREPARE pins inputs
  -> prepared Job -> separately authorized START_RENDER -> progress/result.
- Invariant: PREPARE never starts rendering; START_RENDER is never implicit or
  duplicated; historical Text Revisions, Casting Plans, Jobs, snapshots, QA,
  and Artifacts remain immutable.

## UX contract

```text
UX_CONTRACT
PRIMARY_USER=Story Audio owner producing and correcting narrated chapters every day
PRIMARY_JOURNEY=Book -> chapters -> text/characters/voices -> casting/settings review -> PREPARE -> explicit START_RENDER -> progress -> listen/fix/regenerate -> Human QA/download
PRIMARY_SURFACE=Sản xuất for the current production task; Gán giọng for speaker/voice decisions; Công việc for monitor/recovery; Audio for playback/QA/output; Sách/Giọng/Storage/Settings remain under Tài nguyên or contextual detours
INFORMATION_HIERARCHY=current owner action and blocker first; scope/status second; diagnostics/history advanced
SCOPE_MODEL=one selected Book plus one chapter or contiguous chapter range; contextual routes preserve that scope
PRIMARY_CONTROLS=state-specific owner actions with concrete labels; Back/return links preserve scope
ADVANCED_CONTROLS=settings, history, Jobs, Storage, and diagnostics remain reachable without competing with daily navigation
STATES=meaningful empty/loading/disabled-with-reason/error-with-recovery/running/completed states
BULK_DESTRUCTIVE=no new destructive or bulk operation; existing archive/deactivate semantics remain explicit
DISCOVERABILITY=top-level Sản xuất / Gán giọng / Công việc / Audio; Tài nguyên exposes Sách / Giọng / Storage / Settings without competing with the daily CUJ
ACCESSIBILITY=semantic labels, visible focus, keyboard order, live status, adequate targets and responsive reflow
OWNER_PREFERENCE=NONE; the Goal already fixes the product journey and top-level intent model
```

## Create-flow contract

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Produce or repair chapter audio with pinned reviewed inputs and explicit production authority
LINEAR_OR_NONLINEAR=linear through casting review and PREPARE; separate execution; bounded correction loop after listening
STEPS=Select Book/chapters -> review text/characters/voices/assignment/settings -> approve casting -> PREPARE -> review prepared Job -> START_RENDER -> monitor -> listen/QA/fix
STEP_DEPENDENCIES=each next action comes from authoritative readiness; blockers return to the exact relevant surface
BACK_BEHAVIOR=preserve Book/range and unsent local choices; immutable accepted records are never rewritten
NEXT_VALIDATION=validate at each consequential action and return actionable blockers in context
FINAL_REVIEW_STEP=effective scope, text revision, voice routing, synthesis settings, and estimated work immediately before PREPARE
PRIMARY_COMMIT_ACTION=Chuẩn bị audio; after success, Bắt đầu tạo audio is a separate action that may call TTS
CANCEL_EXIT_BEHAVIOR=close review safely before submission; after submission show reconciliation/progress instead of duplicate dispatch
DRAFT_PERSISTENCE=use existing revision, assignment, override, repair-plan, and Job semantics
POST_SUBMIT_DESTINATION=Job progress, then authoritative Audio playback/QA/output
```

## Workspace and execution contracts

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=advance the selected Book/chapter range to usable final audio or a bounded correction
PRIMARY_WORKSPACE=state-specific Sách, Sản xuất, Giọng, or Audio workspace
PERSISTENT_REGIONS=compact top primary navigation and current Book/range context
CONTEXTUAL_REGIONS=chapter detail, casting blockers, voice settings, repair controls, QA/history
NAVIGATION_MODEL=four daily owner-intent destinations: Sản xuất, Gán giọng, Công việc, Audio; resource/configuration destinations stay under Tài nguyên
LAYOUT_ARCHETYPE=compact top navigation plus state-specific master-detail/contextual workspaces
VIEWPORT_BUDGET=current list/task dominates; secondary detail reflows below at narrow widths
CONTENT_REPLACEMENT_STRATEGY=route and production state replace unrelated work instead of stacking every subsystem
ADVANCED_CONTROL_STRATEGY=secondary navigation and labelled disclosure
EXPECTED_SCROLL_BEHAVIOR=workspace-local lists and explicit progress/history regions may scroll; polling replaces current status in place and remains bounded; the primary action remains reachable without a control wall
ARCHETYPE_RATIONALE=owners repeatedly select a Book/chapter, then act on authoritative contextual state

EXECUTION_CONTRACT
TRIGGER=separate Bắt đầu tạo audio action on an already prepared Job
RUNNING_STATE=queued/running stage, progress, current Job, and plain-language status
STATUS_SURFACE=Sản xuất with Jobs as secondary history/diagnostics
LOGS_DETAIL=contextual only
CANCEL_OR_STOP=only existing backend-authorized recovery actions
COMPLETED_STATE=open/listen/download/fix next actions
FAILED_STATE=plain-language failure plus only backend-authorized retry/resume/recovery
RETURN_PATH=preserve Book/range when returning to setup or opening Audio

RESOURCE_LIBRARY_CONTRACT
RESOURCE_SCOPE=authoritative current/historical chapter audio and Jobs
ROW_OR_ITEM_ACTIONS=play/open, inspect QA, fix through existing repair path, download current/final artifact
STATUS_AND_OUTPUT=chapter, artifact identity, QA state/history, timestamps where already authoritative
EMPTY_STATE=explain no usable audio and link to create/continue production
SEARCH_FILTER=existing filters only where scale already justifies them
```

## Acceptance

The final served candidate must support the owner journey in the Goal prompt:
Book/chapter state and actions; immutable text correction; Book characters and
custom voices; preview and assignment/override; effective synthesis settings;
human casting approval; separate PREPARE and START_RENDER; Job progress and
recovery; Audio playback, repair/targeted regeneration, Human QA, and download.
Focused tests, relevant regression, final served UI inspection at desktop and
narrow widths, runtime source identity, and the real owner-style journey are all
required. User-facing saves must verify the authoritative postcondition and
preserve local interaction state; polling must not accumulate duplicate DOM;
UTF-8 text must remain readable without pathological single-word/character
wrapping at owner viewports. Provider-cost or canonical mutations remain
owner-gated.
