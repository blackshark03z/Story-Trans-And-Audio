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
- **Decision traceability:** use
  `docs/STORY_AUDIO_GOLDEN_JOURNEY_DECISION_MATRIX.md` to bind each observed
  defect to its accept/change/defer/cancel/failure path, invalidated state,
  preserved state, and next action. The matrix is subordinate implementation
  guidance; it does not amend this Goal or its acceptance.

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

## Current bounded UX correction

### Production scope action placement

```text
UX_CONTRACT
PRIMARY_USER=Owner continuing production for a selected Book and chapter range
PRIMARY_JOURNEY=see current Book/chapters -> understand the active scope -> change the Book or chapters when needed
PRIMARY_SURFACE=Phạm vi đang làm header on Sản xuất
INFORMATION_HIERARCHY=current Book/chapter range first; its local change action beside it; progress and character inspection remain separate supporting controls
SCOPE_MODEL=Đổi sách / chương opens the existing scope chooser and does not mutate the current scope until the existing confirmation flow completes
PRIMARY_CONTROLS=Đổi sách / chương next to the current scope summary
ADVANCED_CONTROLS=technical details remain separate
STATES=the action is hidden before an initial scope exists and visible beside the scope after selection
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=the action is visually attached to the object it changes and names the fields it changes
ACCESSIBILITY=button remains keyboard reachable after the current scope summary and keeps the existing focus behavior
OWNER_PREFERENCE=owner requests a more logical, immediately understandable placement
```

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=advance the current production scope
PRIMARY_WORKSPACE=Sản xuất task workspace
PERSISTENT_REGIONS=current scope, progress, production stages, chapter queue, and task surface
CONTEXTUAL_REGIONS=character inspection and technical details
NAVIGATION_MODEL=changing scope opens the existing modal from its current-scope context
LAYOUT_ARCHETYPE=task workspace with compact scope header
VIEWPORT_BUDGET=scope summary and its action share one flexible region; progress and character action keep their own columns
CONTENT_REPLACEMENT_STRATEGY=no new region; the orphan action is moved into the scope identity group
ADVANCED_CONTROL_STRATEGY=unchanged
EXPECTED_SCROLL_BEHAVIOR=scope identity and action remain together without creating a second header row
ARCHETYPE_RATIONALE=the action edits the named scope, so proximity communicates effect better than an isolated centered link
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: change action is beside the current scope summary
SCOPE_CLARITY=PASS: label names Book and chapters explicitly
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS: existing scope chooser and confirmation behavior preserved
ADVANCED_WITHOUT_DOMINATING=NOT_APPLICABLE
DISABLED_STATE_EXPLANATION=PASS: action remains hidden until a scope exists
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS: scope identity and local action precede progress and stages
CONTROL_DENSITY=PASS: one existing control moved; no duplicate added
COHERENT_APPLICATION_COMPOSITION=PASS: orphan second-row link removed
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS: existing openProductionScopeDialog handler retained
INFORMATION_ARCHITECTURE=PASS: action is grouped with the object it changes
NAVIGATION=PASS: existing modal route remains unchanged
WORKSPACE_LAYOUT=PASS: three logical header regions now occupy three grid columns
VIEWPORT_BUDGET=PASS: Chromium 1366x768 and 820x900 checks have no horizontal overflow
PERSISTENT_CONTEXTUAL_CONTROLS=PASS: current-scope action remains persistent only after scope selection
LAYOUT_ARCHETYPE_FIT=PASS: compact task-workspace header preserved
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS: title row wraps and stacks at <=560px
VERTICAL_SPRAWL_REDUCED=NOT_APPLICABLE
WORKSPACE_LAYOUT_SOLUTION=PASS: orphan second row is removed at the reported desktop state
TASK_FLOW_ARCHITECTURE=PASS: scope change remains an edit of step 1, not a new step
LINEAR_MULTISTEP_REASONING=PASS: production stage order is unchanged
REVIEW_BEFORE_COMMIT=NOT_APPLICABLE
EXECUTION_STATE_SEPARATION=PASS: no execution-state behavior changed
RESOURCE_MANAGEMENT_SEPARATION=NOT_APPLICABLE
POST_COMPLETION_DESTINATION=NOT_APPLICABLE
```

### Audio detail scroll correction

```text
UX_CONTRACT
PRIMARY_USER=Owner listening to and reviewing one completed chapter audio
PRIMARY_JOURNEY=select an audio row -> listen/read its metadata -> review or act in Human QA -> inspect optional history/details
PRIMARY_SURFACE=Duyệt audio detail pane
INFORMATION_HIERARCHY=selected audio and player first; Human QA immediately after; immutable configuration and technical history remain optional disclosures
SCOPE_MODEL=the currently selected audio only; scrolling never changes selection or QA state
PRIMARY_CONTROLS=player, download/export, and available Human QA action
ADVANCED_CONTROLS=configuration snapshot, repair details, QA history, and technical details
STATES=empty selection, selected audio, accepted, needs-fixes, loading/error behavior remain unchanged
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=detail follows the selected queue row without a floating layer obscuring later controls
ACCESSIBILITY=source order and keyboard order match the visible scroll order; no sticky overlap hides focused controls
OWNER_PREFERENCE=NONE; this restores the already visible document order reported by the owner
```

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=listen to one selected audio and complete or inspect Human QA
PRIMARY_WORKSPACE=master-detail audio workspace
PERSISTENT_REGIONS=queue and selected detail column; the top application shell remains fixed
CONTEXTUAL_REGIONS=selected audio player, QA controls, configuration, history, and technical details
NAVIGATION_MODEL=select a queue row, then scroll naturally through that row's detail
LAYOUT_ARCHETYPE=master-detail desktop, stacked detail and queue at narrower widths
VIEWPORT_BUDGET=detail content uses one continuous readable column without overlapping layers
CONTENT_REPLACEMENT_STRATEGY=the selected detail replaces the empty state
ADVANCED_CONTROL_STRATEGY=configuration and history remain disclosures in normal document flow
EXPECTED_SCROLL_BEHAVIOR=page/detail content scrolls in source order; the player is not sticky inside the Audio review detail and never covers Human QA
ARCHETYPE_RATIONALE=the owner needs list context beside detail, but no detail subsection is important enough to obscure another action
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: existing Duyệt audio master-detail surface
SCOPE_CLARITY=PASS: selected chapter identity remains visible in detail
APPLY_REAPPLY_RESET_EXPLICITNESS=NOT_APPLICABLE
ADVANCED_WITHOUT_DOMINATING=PASS: configuration/history remain disclosures in document flow
DISABLED_STATE_EXPLANATION=NOT_APPLICABLE
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS: player precedes Human QA without overlap
CONTROL_DENSITY=PASS: no controls added
COHERENT_APPLICATION_COMPOSITION=PASS: master-detail composition preserved
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS: CSS-only positioning correction plus regression coverage
INFORMATION_ARCHITECTURE=PASS: selected output and QA relationship unchanged
NAVIGATION=PASS: route and selection behavior unchanged
WORKSPACE_LAYOUT=PASS: detail subsections remain in one non-overlapping flow
VIEWPORT_BUDGET=PASS: Chromium 1366x768 geometry check
PERSISTENT_CONTEXTUAL_CONTROLS=PASS: application shell stays persistent; detail content does not float
LAYOUT_ARCHETYPE_FIT=PASS: master-detail remains legible
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS: existing <=1100px stacked rule preserved
VERTICAL_SPRAWL_REDUCED=NOT_APPLICABLE
WORKSPACE_LAYOUT_SOLUTION=PASS: removed the conflicting sticky layer
TASK_FLOW_ARCHITECTURE=PASS: listen -> QA source order now matches visible order
LINEAR_MULTISTEP_REASONING=NOT_APPLICABLE
REVIEW_BEFORE_COMMIT=NOT_APPLICABLE
EXECUTION_STATE_SEPARATION=PASS: no production execution state changed
RESOURCE_MANAGEMENT_SEPARATION=PASS: fix remains within Audio resource review
POST_COMPLETION_DESTINATION=NOT_APPLICABLE
```

```text
UX_CONTRACT
PRIMARY_USER=Owner reviewing completed chapter audio and removing outputs that are no longer wanted
PRIMARY_JOURNEY=open Duyệt audio -> scan readable rows -> select one or more current audio outputs -> review exact scope -> remove selected or all currently filtered outputs -> return to the reconciled library
PRIMARY_SURFACE=Duyệt audio queue toolbar and each readable queue row
INFORMATION_HIERARCHY=chapter/title and QA state first; selection second; playback/QA detail contextual; destructive actions visually separate from listen/download
SCOPE_MODEL=checkboxes select exact active artifact IDs; Xóa tất cả means every row currently matching the visible filters, never hidden library rows
PRIMARY_CONTROLS=select row, select all currently filtered, clear selection, Xóa audio đã chọn, Xóa tất cả đang hiển thị
ADVANCED_CONTROLS=configuration snapshot, QA history, video export, and storage cleanup stay contextual or under Tài nguyên
STATES=loading and errors disable deletion; empty selection explains how to enable it; preview lists count/books/chapters/bytes; stale targets reject the whole request and reload; success reconciles the library
BULK_DESTRUCTIVE=two-step preview plus confirmation; exact artifact IDs and hashes are server-revalidated; operation removes current outputs from the library, preserves immutable Job/QA/history records, and does not cascade into text/casting or create new audio
DISCOVERABILITY=selection and delete toolbar sit directly above the audio queue; labels state selected versus all currently displayed
ACCESSIBILITY=row checkboxes have chapter labels; bulk status is live; dialog has named actions, safe cancel, keyboard focus, and no color-only warning
OWNER_PREFERENCE=owner explicitly requests deletion by selection and deletion of all; all is bounded to the currently filtered visible result set to avoid deleting hidden rows
```

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=review and manage completed audio without malformed rows or hidden destructive scope
PRIMARY_WORKSPACE=master-detail audio workspace with the queue dominant until a row is selected
PERSISTENT_REGIONS=summary, filters, compact selection toolbar, queue, and current detail
CONTEXTUAL_REGIONS=player, Human QA, repair, configuration history, and delete confirmation
NAVIGATION_MODEL=Audio remains one top-level destination; deletion does not navigate away
LAYOUT_ARCHETYPE=master-detail desktop, stacked detail then queue below 1100px, card rows below 760px
VIEWPORT_BUDGET=queue columns must fit the left pane without clipping; long chapter text truncates/wraps within its cell; controls wrap instead of squeezing metadata
CONTENT_REPLACEMENT_STRATEGY=detail replaces its empty state; confirmation uses one modal rather than stacking permanent warning panels
ADVANCED_CONTROL_STRATEGY=permanent storage cleanup remains under Dung lượng after a current output is removed
EXPECTED_SCROLL_BEHAVIOR=page owns primary scroll; queue may scroll on wide desktop only; selection, deletion, polling, and reload preserve page position unless the selected detail is explicitly opened
ARCHETYPE_RATIONALE=the owner needs list context while inspecting one audio, but narrow screens need full-width readable rows
```

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
BULK_DESTRUCTIVE=Audio supports separately confirmed removal of selected or currently filtered active outputs; immutable artifacts, Jobs, QA history, text, and casting remain preserved
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
ROW_OR_ITEM_ACTIONS=play/open, inspect QA, fix through existing repair path, download current/final artifact, or explicitly remove the current output from the library while retaining history
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
