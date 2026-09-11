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

### Contextual custom voice creation and return

```text
UX_CONTRACT
PRIMARY_USER=Owner resolving a missing or unsuitable character voice inside the current production scope
PRIMARY_JOURNEY=character voice field -> add custom voice for the current Book -> save one sample-backed usable voice -> explicitly use it -> return to the exact field with an unsaved preselection
PRIMARY_SURFACE=the existing Thêm giọng mới action beside the character or Book voice selector
INFORMATION_HIERARCHY=custom voice creation first during a create detour; current Book and return destination supporting; existing voice management, revisions, and provider preview secondary
SCOPE_MODEL=a new custom voice belongs to the originating Book and becomes selectable only in that Book; the chapter range is preserved context, not voice ownership scope
PRIMARY_CONTROLS=Tên giọng, audio tham chiếu, transcript chính xác, Lưu giọng, Dùng giọng này
ADVANCED_CONTROLS=existing voice management, immutable revision history, preferred revision, deactivate/reactivate, and provider-backed preview remain available without leading the create flow
STATES=loading; inline validation with retained inputs; saved-and-ready with exact voice identity; safe cancel/no-change; stale return context rejected
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=Thêm giọng mới opens and focuses the creation form rather than the generic selected-voice detail
ACCESSIBILITY=labelled inputs, status region, deterministic focus, explicit disabled reason, and keyboard-reachable use/return actions
OWNER_PREFERENCE=owner requires a saved voice to appear immediately in the originating character voice list
```

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Create one usable Book-owned custom voice and make it available to the originating character voice selector
LINEAR_OR_NONLINEAR=linear create-and-return path; library management remains a separate peer task
STEPS=open from character/Book voice -> confirm Book scope -> enter name/audio/transcript -> Lưu giọng -> see saved-ready result -> Dùng giọng này -> verify unsaved selection at origin -> explicit Lưu applies it
STEP_DEPENDENCIES=save requires all mandatory fields; use requires the exact successful active usable voice and a fresh Book-scoped catalog
BACK_BEHAVIOR=return/cancel preserves production scope and unsaved source fields and does not substitute an old library selection
NEXT_VALIDATION=validate before upload; verify returned voice identity and catalog selectability after save; reject stale origin before preselection
FINAL_REVIEW_STEP=NOT_APPLICABLE because saving a local reference resource does not call TTS or alter an assignment
PRIMARY_COMMIT_ACTION=Lưu giọng creates the logical voice and immutable first reference revision atomically
CANCEL_EXIT_BEHAVIOR=Quay lại không thay đổi restores the exact origin without changing its selected voice
DRAFT_PERSISTENCE=source assignment draft is preserved for the bounded same-tab detour; incomplete new-voice form is not persisted
POST_SUBMIT_DESTINATION=saved-ready result in Voice Library, followed by explicit Dùng giọng này and unsaved preselection in the exact originating selector
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: every current narrator/character voice selector exposes Thêm giọng custom locally
SCOPE_CLARITY=PASS: Voice Library locks and names the originating Book; chapter 1-5 remains return context rather than voice ownership
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS: Lưu giọng creates the resource; Dùng giọng này preselects it; the originating Lưu action remains the only assignment commit
ADVANCED_WITHOUT_DOMINATING=PASS: preset preview and revision management no longer lead the create detour
DISABLED_STATE_EXPLANATION=PASS: Dùng giọng này stays disabled until an active selectable custom voice is explicitly selected
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS: Book scope, create form, saved voices, then revision details
CONTROL_DENSITY=PASS: one local create action per voice editor and one explicit use/return action group
COHERENT_APPLICATION_COMPOSITION=PASS: create is a contextual detour from Gán giọng, not a competing production stage
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS: source draft and exact chapter range survive create/cancel/use; no automatic assignment save
INFORMATION_ARCHITECTURE=PASS: reusable Book voice is created in Giọng and consumed in Gán giọng
NAVIGATION=PASS: runtime check returned from Hứa Thanh to the exact selector at Book 1, chapters 1-5
WORKSPACE_LAYOUT=PASS: custom creation is first in create mode; supporting management remains below
VIEWPORT_BUDGET=PASS: default runtime viewport reflows to the compact top navigation without horizontal overlap
PERSISTENT_CONTEXTUAL_CONTROLS=PASS: the return banner states the destination and save boundary throughout the detour
LAYOUT_ARCHETYPE_FIT=PASS: bounded contextual creation flow with progressive disclosure
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS: default narrow runtime view stacks controls and preserves readable labels
VERTICAL_SPRAWL_REDUCED=PASS: preset section is hidden during the create intent and the form opens directly
WORKSPACE_LAYOUT_SOLUTION=PASS: current Book custom-voice workspace is prioritized for creation
CREATE_FLOW_COMPLETENESS=PASS: open -> locked Book -> create-ready form -> explicit use -> exact unsaved selector was exercised; isolated tests cover successful save/catalog refresh
TECHNICAL_VALIDATION=PASS: 270 focused contract tests and 11 browser/voice-regression tests pass at final working tree
CANDIDATE_PREVIEW=PASS: served runtime shows ChanLee on direct assignment entry, exact-scope cancel, explicit use, and no browser errors
OWNER_ACCEPTANCE=REQUIRED: no new production voice was created during verification; owner should supply a real reference sample and approve the live save result
```

### Custom voice detail hierarchy

```text
UX_CONTRACT
PRIMARY_USER=Owner inspecting a saved custom voice and deciding whether its current reference is suitable for future synthesis
PRIMARY_JOURNEY=select saved voice -> understand which reference revision is current -> listen to the original reference or optionally create a synthesized test -> manage revisions only when needed
PRIMARY_SURFACE=selected custom voice detail in Giọng
INFORMATION_HIERARCHY=voice identity and current reference first; original-reference playback and synthesized test as two explicitly different actions; history, upload, and technical metadata advanced
SCOPE_MODEL=one Book-owned logical voice; changing the current reference affects future synthesis only and never changes already-created audio
PRIMARY_CONTROLS=Nghe audio tham chiếu, optional preview text, Tạo bản nghe thử, deactivate/reactivate
ADVANCED_CONTROLS=revision history, set another revision as current, upload immutable revision, technical metadata
STATES=no revision with an explanation; current revision ready; generating test; generated result; recoverable error
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=the current revision summary sits immediately below voice identity; the synthesized test has a separate labelled result area
ACCESSIBILITY=clear Vietnamese labels, live status for generated output, explicit button names, keyboard-reachable advanced disclosure
OWNER_PREFERENCE=owner explicitly reports that Used for synthesis, Generate Test Audio, and Nghe thử appear confusing or duplicated
```

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=understand and verify the selected custom voice without deciphering revision terminology
PRIMARY_WORKSPACE=compact selected-voice summary followed by one quality-check action
PERSISTENT_REGIONS=voice identity, current reference, reference-listen action, and synthesized-test action
CONTEXTUAL_REGIONS=generated test result and error state
NAVIGATION_MODEL=remain in Giọng; no route change for playback or test generation
LAYOUT_ARCHETYPE=single-column detail with one primary verification card and one advanced disclosure
VIEWPORT_BUDGET=summary and controls wrap vertically below 700px without horizontal scrolling
CONTENT_REPLACEMENT_STRATEGY=a new generated test replaces the previous test result; selecting another voice resets stale playback/result state
ADVANCED_CONTROL_STRATEGY=history, revision switching, upload, and technical metadata live under one collapsed Nâng cao disclosure
EXPECTED_SCROLL_BEHAVIOR=opening advanced content expands in place; playback and generated-result updates do not move page scroll
ARCHETYPE_RATIONALE=voice verification is the frequent task; revision administration is occasional and must not dominate
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: selecting a saved custom voice reveals its identity and current reference immediately
SCOPE_CLARITY=PASS: the current Book remains visible; the copy states that only future synthesis uses the selected reference and existing audio is unchanged
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS: changing the current reference remains an explicit Advanced action; test generation is a separate explicit action
ADVANCED_WITHOUT_DOMINATING=PASS: revision history, revision switching, upload, and technical metadata are collapsed under one Nâng cao disclosure
DISABLED_STATE_EXPLANATION=PASS: no current reference disables test generation and gives the exact recovery path
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS: current reference, original-reference playback, synthesized test, then Advanced administration
CONTROL_DENSITY=PASS: duplicate disabled voice and revision controls were removed; one primary Tạo bản nghe thử action remains
COHERENT_APPLICATION_COMPOSITION=PASS: reference playback verifies source material while generated playback verifies synthesized output, with distinct labels and endpoints
DESTRUCTIVE_DIFFERENTIATION=PASS: deactivate remains outside the verification actions and no new destructive control was introduced
EXISTING_WORKFLOW_PRESERVATION=PASS: the preview endpoint, preferred-revision endpoint, immutable revision upload, and Book-scoped voice model are unchanged
INFORMATION_ARCHITECTURE=PASS: frequent verification is visible; occasional resource administration is advanced
NAVIGATION=PASS: all actions remain inside Giọng and preserve the production return context
WORKSPACE_LAYOUT=PASS: one compact current-reference card and one quality-check card precede a single Advanced disclosure
VIEWPORT_BUDGET=PASS: live 1366px and 700px inspections show no horizontal overflow; controls stack at the narrow viewport
PERSISTENT_CONTEXTUAL_CONTROLS=PASS: the current revision summary is persistent; generated output appears only after explicit generation
LAYOUT_ARCHETYPE_FIT=PASS: single-column resource detail matches the bounded inspection task
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS: the reference action and test controls become full-width at 700px
VERTICAL_SPRAWL_REDUCED=PASS: history, upload, and per-revision technical metadata no longer occupy the default detail view
WORKSPACE_LAYOUT_SOLUTION=PASS: the owner can distinguish source playback from synthesized preview without reading implementation terms
TECHNICAL_VALIDATION=PASS: JavaScript syntax, 275 focused contract tests, and the 11-stage browser journey assertions pass
CANDIDATE_PREVIEW=PASS: canonical read-only runtime inspection shows ChanLee Revision 1 auto-selected, Advanced collapsed, distinct playback labels, and no horizontal overflow at 1366px/700px
OWNER_ACCEPTANCE=REQUIRED: provider-backed test generation and live playback were intentionally not invoked; owner should visually confirm the revised wording and may explicitly test audio later
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
