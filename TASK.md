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
  new production range directly; completed Job/casting snapshots remain
  immutable while each chapter retains only its current audio bundle, and persistent book/character voice configuration is clearly
  presented as input for future PREPARE/render rather than as mutation of old audio.
- **Non-goals:** no parallel orchestration/framework subsystem, no unrelated repo
  cleanup, no generalized policy engine for a local defect, and no provider-cost
  action merely to prove engineering progress.
- **Constraints:** canonical data and immutable text/casting/Job records remain protected;
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
  duplicated; historical Text Revisions, Casting Plans and Jobs remain
  immutable, while superseded audio/QA is not retained.

## Current bounded UX correction

### Keep one current audio and remove audio history

Owner decision (2026-09-12): Story Audio does not retain historical audio
generations or QA history. Each chapter keeps at most one current verified audio
bundle. Activating a replacement clears QA and permanently removes the previous
final/master/timeline and segment WAV files. Explicit delete removes the selected
current bundle permanently. Jobs, current text/casting state, and custom voice
revisions remain; custom voice is the reusable long-lived media resource.

Acceptance:

1. Given an approved current audio, when a verified replacement becomes active,
   then only the replacement bundle remains and its QA state is pending.
2. Given selected current audio, when the owner confirms deletion, then those
   files and artifact rows are removed and the chapters can be produced again;
   text, casting, Job records and custom voices remain.
3. Given existing historical bundles, when the one-time reconciliation runs,
   then all non-current audio/QA history is removed without changing current
   audio or custom voice data.

### Leave post-render review pending and start the next production cycle

```text
UX_CONTRACT
PRIMARY_USER=Owner who has finished rendering a range but wants to postpone Human QA and start another production range
PRIMARY_JOURNEY=see rendered range waiting for review -> either open Audio review or start a new production cycle -> choose the next Book/chapter range
PRIMARY_SURFACE=the Audio chờ duyệt handoff state in Sản xuất, plus the Chờ duyệt filter in Duyệt audio
INFORMATION_HIERARCHY=review the delivered audio remains primary; starting another production cycle is a visible secondary action; technical Job details stay contextual
SCOPE_MODEL=starting a new cycle clears only local production navigation context and opens the existing scope chooser; pending audio, Jobs, snapshots, and QA state remain unchanged
PRIMARY_CONTROLS=Mở Duyệt audio; Bắt đầu lượt sản xuất mới
ADVANCED_CONTROLS=technical Job and artifact identity remain in their existing disclosures
STATES=all current pending audio is visible under Chờ duyệt; a replacement always begins pending and never inherits an earlier approval; empty/error states retain existing recovery
BULK_DESTRUCTIVE=NOT_APPLICABLE; neither exit action approves, removes, or replaces audio
DISCOVERABILITY=both valid next actions are visible at the post-render handoff; no approval is required to reach the scope chooser
ACCESSIBILITY=explicit button labels; pending-count and filtered-result status remain live text
OWNER_PREFERENCE=owner explicitly wants to postpone review and begin another production cycle
```

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Start another bounded production cycle while preserving the current range in the Audio review queue
LINEAR_OR_NONLINEAR=nonlinear because post-render Human QA may be deferred while production continues on another range
STEPS=render completes -> choose review now or start another cycle -> existing scope chooser -> normal production journey
STEP_DEPENDENCIES=the new-cycle action is available only after render handoff; subsequent production still obeys all normal readiness, PREPARE, and START_RENDER gates
BACK_BEHAVIOR=closing the scope chooser leaves persisted pending audio untouched and allows returning to Duyệt audio
NEXT_VALIDATION=the existing scope chooser validates Book/range before restoring production context
FINAL_REVIEW_STEP=the existing preflight remains the required review before PREPARE/render; deferring Human QA does not bypass it
PRIMARY_COMMIT_ACTION=Bắt đầu lượt sản xuất mới opens the existing scope chooser and performs no production mutation
CANCEL_EXIT_BEHAVIOR=canceling the chooser creates no Job or audio and does not change QA state
DRAFT_PERSISTENCE=pending current audio, its Job/configuration snapshot, and current QA state remain durable in Duyệt audio
POST_SUBMIT_DESTINATION=Sản xuất with the next likely range suggested in the existing scope chooser
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: Audio chờ duyệt shows both Mở Duyệt audio and Bắt đầu lượt sản xuất mới
SCOPE_CLARITY=PASS: the handoff names the delivered range and states that the pending audio and Job stay unchanged
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS: starting a new cycle only clears local navigation context and opens the existing scope chooser
ADVANCED_WITHOUT_DOMINATING=PASS: Job/artifact details remain contextual
DISABLED_STATE_EXPLANATION=NOT_APPLICABLE
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE: neither new behavior is destructive
VISIBLE_HIERARCHY=PASS: review now is primary; defer review and start another cycle is secondary
CONTROL_DENSITY=PASS: one secondary action is added to the post-render handoff only
COHERENT_APPLICATION_COMPOSITION=PASS: production hands persisted outputs to the existing Audio resource workspace
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS: Human QA, repair, PREPARE, START_RENDER, and Jobs are unchanged; audio retention follows the one-current-audio decision above
INFORMATION_ARCHITECTURE=PASS: execution completion and deferred resource review are explicitly separated
NAVIGATION=PASS: the existing scope chooser is the destination for a new cycle
WORKSPACE_LAYOUT=PASS: both valid next actions are grouped in the handoff card; the Audio queue remains master-detail
VIEWPORT_BUDGET=PASS: browser acceptance covers desktop and 820px without horizontal overflow
PERSISTENT_CONTEXTUAL_CONTROLS=PASS: the delivered range remains visible until the owner starts another cycle
LAYOUT_ARCHETYPE_FIT=PASS: handoff actions fit the linear production state; Audio remains a resource-review workspace
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS: the existing action group wraps and browser acceptance covers the narrow viewport
VERTICAL_SPRAWL_REDUCED=NOT_APPLICABLE
WORKSPACE_LAYOUT_SOLUTION=PASS: all five matching review rows exist in the queue; internal list scrolling remains bounded
TASK_FLOW_ARCHITECTURE=PASS: post-render review is optional before beginning another independent production cycle
LINEAR_MULTISTEP_REASONING=PASS: the new cycle re-enters at the existing scope-selection step
REVIEW_BEFORE_COMMIT=PASS: the existing production preflight remains mandatory before any later PREPARE/render
EXECUTION_STATE_SEPARATION=PASS: completed render is handed off before another cycle begins
RESOURCE_MANAGEMENT_SEPARATION=PASS: deferred audio remains in Duyệt audio rather than the new production setup
POST_COMPLETION_DESTINATION=PASS: owner may choose Audio review now or the next scope chooser
TECHNICAL_VALIDATION=PASS: focused UI and browser checks pass; the known unrelated range-input browser failure remains outside this correction
CANDIDATE_PREVIEW=PASS: live read-only candidate shows 5/5 under Chờ duyệt and opens the next suggested range 6-10 without a production mutation
OWNER_ACCEPTANCE=REQUIRED: owner should confirm the two-action handoff wording and queue grouping
```

### Save scoped voice before Final Voice Map approval

```text
UX_CONTRACT
PRIMARY_USER=Owner choosing the effective voice for a known speaker in the current chapter range
PRIMARY_JOURNEY=review speaker identity -> choose a usable preset/custom voice -> save it for the selected chapter/range -> review and approve the resulting Final Voice Map once
PRIMARY_SURFACE=the voice editor for the current speaker in Gán giọng
INFORMATION_HIERARCHY=voice and scope choice first; saved-draft feedback next; Final Voice Map review remains the following journey step
SCOPE_MODEL=chapter or range save affects only future PREPARE/render for chapters where the speaker appears; approved plans and existing audio remain unchanged until the new draft is explicitly approved
PRIMARY_CONTROLS=Lưu giọng cho chương / Lưu giọng cho phạm vi
ADVANCED_CONTROLS=technical plan identity remains outside the primary action
STATES=speaker review incomplete with exact remedy; saving; saved as draft and ready for map review; stale/conflicting save rejected without partial write
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=the save action remains beside the selected scope and voice; no premature Final Voice Map approval detour
ACCESSIBILITY=explicit action labels and inline status/error feedback remain keyboard reachable
OWNER_PREFERENCE=owner explicitly rejects approving the old voice map before saving the desired custom voice
```

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Save a scoped voice choice into the next reviewable Final Voice Map draft
LINEAR_OR_NONLINEAR=linear because speaker identity precedes voice configuration and one Final Voice Map review follows it
STEPS=review speaker -> choose scope and voice -> save draft -> review Final Voice Map -> approve
STEP_DEPENDENCIES=scoped save requires current approved speaker identity and an available voice; approval requires the newly created eligible draft
BACK_BEHAVIOR=unsaved choice remains local until save; approved plans and existing audio remain unchanged
NEXT_VALIDATION=server revalidates speaker state, voice availability, active text revision, and latest plan identity atomically
FINAL_REVIEW_STEP=Final Voice Map is the single review immediately after scoped voice saves
PRIMARY_COMMIT_ACTION=Lưu giọng cho phạm vi creates a new immutable draft revision; it does not approve or render
CANCEL_EXIT_BEHAVIOR=Hủy lựa chọn chưa lưu restores the current effective voice without persistence
DRAFT_PERSISTENCE=successful scoped saves persist as Casting Plan draft revisions and survive reload
POST_SUBMIT_DESTINATION=the same assignment surface confirms the saved voice; production projection advances to Final Voice Map review
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: the scoped save action stays beside the chosen voice and scope
SCOPE_CLARITY=PASS: the row states the affected chapters and that only future PREPARE/render uses the saved choice
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS: save and cancel-unsaved remain separate explicit actions
ADVANCED_WITHOUT_DOMINATING=PASS: technical Casting Plan identity is not introduced into the primary save decision
DISABLED_STATE_EXPLANATION=PASS: only incomplete speaker review blocks save and the UI names that prerequisite and recovery
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS: choose voice, save scoped draft, then review the Final Voice Map once
CONTROL_DENSITY=PASS: the premature Duyệt bản đồ giọng trước detour was removed without adding another control
COHERENT_APPLICATION_COMPOSITION=PASS: the existing assignment surface owns both the scoped choice and its save feedback
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS: approved Casting Plans, existing audio, Jobs, and PREPARE/render authority remain unchanged until explicit approval
INFORMATION_ARCHITECTURE=PASS: speaker review remains step 1, voice configuration step 2, and Final Voice Map approval the next step
NAVIGATION=PASS: no route change is required before saving the custom voice
WORKSPACE_LAYOUT=PASS: the primary row action remains in context with the selected speaker
VIEWPORT_BUDGET=PASS: the correction removes a blocking callout/action branch and adds no layout region
PERSISTENT_CONTEXTUAL_CONTROLS=PASS: current Book/range context and unsaved voice choice stay visible
LAYOUT_ARCHETYPE_FIT=PASS: the existing scoped editor remains the bounded configuration workspace
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS: no new width-dependent control or panel was introduced
VERTICAL_SPRAWL_REDUCED=PASS: the redundant approval detour is removed
WORKSPACE_LAYOUT_SOLUTION=PASS: Hứa Thanh can be assigned the custom voice for the selected range before reviewing the resulting map
TECHNICAL_VALIDATION=PASS: 161 affected tests pass; syntax and Python compilation checks pass
CANDIDATE_PREVIEW=PASS: the served Book 1 range 1-5 registry shows the Hứa Thanh custom voice and Lưu giọng cho phạm vi while the latest plan is draft, with no premature approval action
OWNER_ACCEPTANCE=REQUIRED: live save was intentionally not invoked against canonical data; owner should confirm the corrected interaction before any production mutation
```

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
PRIMARY_JOURNEY=select an audio row -> listen/read its metadata -> review or act in Human QA -> inspect optional current configuration/details
PRIMARY_SURFACE=Duyệt audio detail pane
INFORMATION_HIERARCHY=selected audio and player first; Human QA immediately after; current render configuration and technical details remain optional disclosures
SCOPE_MODEL=the currently selected audio only; scrolling never changes selection or QA state
PRIMARY_CONTROLS=player, download/export, and available Human QA action
ADVANCED_CONTROLS=current configuration snapshot, repair details, and technical details
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
CONTEXTUAL_REGIONS=selected audio player, QA controls, current configuration, and technical details
NAVIGATION_MODEL=select a queue row, then scroll naturally through that row's detail
LAYOUT_ARCHETYPE=master-detail desktop, stacked detail and queue at narrower widths
VIEWPORT_BUDGET=detail content uses one continuous readable column without overlapping layers
CONTENT_REPLACEMENT_STRATEGY=the selected detail replaces the empty state
ADVANCED_CONTROL_STRATEGY=current configuration and technical details remain disclosures in normal document flow
EXPECTED_SCROLL_BEHAVIOR=page/detail content scrolls in source order; the player is not sticky inside the Audio review detail and never covers Human QA
ARCHETYPE_RATIONALE=the owner needs list context beside detail, but no detail subsection is important enough to obscure another action
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS: existing Duyệt audio master-detail surface
SCOPE_CLARITY=PASS: selected chapter identity remains visible in detail
APPLY_REAPPLY_RESET_EXPLICITNESS=NOT_APPLICABLE
ADVANCED_WITHOUT_DOMINATING=PASS: current configuration and technical details remain disclosures in document flow
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
ADVANCED_CONTROLS=current configuration snapshot, video export, and storage cleanup stay contextual or under Tài nguyên
STATES=loading and errors disable deletion; empty selection explains how to enable it; preview lists count/books/chapters/bytes; stale targets reject the whole request and reload; success reconciles the library
BULK_DESTRUCTIVE=two-step preview plus confirmation; exact current artifact IDs and hashes are server-revalidated; operation permanently deletes selected current audio bundles, preserves Job/text/casting/custom voices, and does not create new audio
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
BULK_DESTRUCTIVE=Audio supports separately confirmed permanent removal of selected or currently filtered current outputs; Jobs, text, casting, and custom voices remain preserved
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

## Automated Audio QA Triage v1

```text
UX_CONTRACT
PRIMARY_USER=Owner reviewing the currently selected audio in Duyệt audio
PRIMARY_JOURNEY=select current audio -> see Máy kiểm tra directly after the player -> seek the bounded shortlist -> make the existing Human QA decision
PRIMARY_SURFACE=Audio review detail; the machine panel is after player/download and before Human QA
STATES=not_loaded -> running -> clear|attention|degraded|blocked; this state is independent of Human QA pending|needs_fixes|accepted
CLEAR_COPY=Máy không phát hiện lỗi kỹ thuật rõ; bạn vẫn cần nghe và quyết định.
ACCESSIBILITY=aria-live status, semantic seek buttons, and keyboard-operable controls; loading/error never lock player, download, or Human QA
```

## Automated Audio QA score and review-workspace correction

```text
UX_CONTRACT
PRIMARY_USER=Owner reviewing one current chapter audio and deciding what must be heard before Human QA
PRIMARY_JOURNEY=select current audio -> see machine status and an explainable technical score -> seek only the highest-risk points -> accept or request repair
PRIMARY_SURFACE=the selected-audio detail pane in Duyệt audio, directly after the player and before Human QA
INFORMATION_HIERARCHY=machine outcome, score, coverage and next action first; component evidence and listening points second; Human QA remains the decision surface
SCOPE_MODEL=analysis is bound to the exact current artifact ID and SHA-256 and never applies to another generation
PRIMARY_CONTROLS=seek buttons for suggested timestamps; Chấp nhận; Cần sửa
ADVANCED_CONTROLS=render configuration and technical evidence remain disclosures
STATES=running with named work -> scored full|scored limited -> blocked with recovery; changing selection invalidates the prior result
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=the score appears automatically for the selected audio; no settings or manual start action is required
ACCESSIBILITY=plain-language status, semantic score/component labels, keyboard seek controls, visible focus and readable feedback options
OWNER_PREFERENCE=machine scoring should reduce listening time but must not silently replace Human QA
```

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=compare the audio queue with the selected audio while listening and making a Human QA decision
PRIMARY_WORKSPACE=desktop master-detail workspace with queue context on the left and a bounded selected-audio inspector on the right
PERSISTENT_REGIONS=queue and selected-audio identity remain visible together on desktop
CONTEXTUAL_REGIONS=machine result and repair form exist only for the selected current audio
NAVIGATION_MODEL=select a queue row; seek suggestions and QA controls act on that exact selection
LAYOUT_ARCHETYPE=master-detail with independently scrolling queue and detail pane on desktop; stacked document flow at narrow widths
VIEWPORT_BUDGET=the detail pane is bounded to the viewport so its long content does not create an empty left page; form labels receive the full pane width
CONTENT_REPLACEMENT_STRATEGY=selection replaces detail content instead of stacking another chapter
ADVANCED_CONTROL_STRATEGY=configuration and low-level evidence stay collapsed
EXPECTED_SCROLL_BEHAVIOR=desktop wheel scroll inside the pane under the pointer; narrow layout returns to one page scroll without nested height traps
ARCHETYPE_RATIONALE=queue context is needed while reviewing one selected audio, but long detail content must not push the whole page past the queue
```

```text
STATE_HAZARD_R2_S3
AUTHORITATIVE_SOURCE=current chapter active_audio_artifact_id plus artifact SHA/path, matching timeline and retained segment bindings
REPRESENTATIVE_TRANSITION=artifact A finishes scoring -> owner selects artifact B -> A result is discarded and cannot render in B detail
INVARIANT=technical score is explainable guidance only; blocked integrity has no score and only explicit Human QA can accept or reject audio
ACCEPTANCE=full clean fixture exposes 0-100 technical score, 100% deep coverage and a next action; risk fixtures lower the score and expose seek points; missing retained segments disclose limited coverage; stale/broken binding blocks without score or mutation; desktop detail scroll keeps queue context and repair checkboxes remain readable; narrow layout stacks without horizontal overflow
```

```text
WORKSPACE_CONTRACT
IDENTITY=each response is bound to the exact current artifact ID and SHA-256; a non-current/stale request fails closed
ANALYSIS=read-only deterministic inspection of final/master/timeline and segment WAVs when retained; no local persistence, report history, cache, schema, worker, provider, or network
RETENTION=missing segment WAVs with valid final/master/timeline is degraded, not corruption
SHORTLIST=integrity/decode first, hard clipping second, bounded technical risks third, then one realized-voice representative and first/last positions; duplicates collapse
NO_EFFECTS=no Gemini, VieNeu/TTS, PREPARE, START_RENDER, Human QA command, file/DB write, custom-voice change, replacement, or deletion
```

```text
STATE_HAZARD_R2_S3
AUTHORITATIVE_SOURCE=current chapter active_audio_artifact_id plus matching artifact SHA/path and timeline binding
REPRESENTATIVE_TRANSITION=selected artifact A -> selected artifact B invalidates A's pending response before it can render
INVARIANT=machine result can only guide listening; Human QA remains the sole acceptance/rejection authority
ACCEPTANCE=risk fixture yields attention without Human QA mutation; clean full fixture is clear but never accepted; cleaned segment WAVs yield playable degraded; mismatched SHA/path/timeline blocks without mutation; reload recomputes only the current selection
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS - the selected-audio pane starts the machine check automatically and names its current state
SCOPE_CLARITY=PASS - the result is bound to the selected current artifact and is replaced when selection changes
APPLY_SEMANTICS=NOT_APPLICABLE - machine analysis has no save/apply action and performs no mutation
ADVANCED_WITHOUT_DOMINATING=PASS - score, coverage and next action precede collapsed configuration and technical evidence
DISABLED_STATE_EXPLANATION=PASS - running, limited and blocked states explain both cause and available next action
BULK_ACTION_PREDICTABILITY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS - machine guidance and Human QA are visually distinct; Human QA remains the decision surface
CONTROL_DENSITY=PASS - listening shortcuts are bounded in their own scroll region and repair labels use the full available width
COHERENT_VISUAL_SYSTEM=PASS - existing cards, status colors, spacing and controls are reused
DESTRUCTIVE_ACTION_SAFETY=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS - accept, repair, download and queue selection semantics are unchanged
INFORMATION_ARCHITECTURE=PASS - evidence sits with the selected audio, before Human QA, rather than becoming a new navigation destination
NAVIGATION_MODEL=PASS - selecting a row replaces the detail; suggested timestamps seek within that selected audio
WORKSPACE_LAYOUT=PASS - desktop remains master-detail with independent queue/detail scrolling; narrow widths use one stacked flow
VIEWPORT_BUDGET=PASS - desktop detail height is viewport-bounded and the page no longer leaves a long blank queue column
PERSISTENT_CONTEXTUAL_CONTROLS=PASS - queue identity and selected-audio identity remain together on desktop
LAYOUT_ARCHETYPE_FIT=PASS - master-detail matches compare-and-review work
RESPONSIVE_BEHAVIOR=PASS - verified at 1440x900 and 820x900 without horizontal overflow
VERTICAL_SPRAWL_REDUCED=PASS - long evidence scrolls inside the desktop detail pane and returns to document flow on narrow screens
WORKSPACE_LAYOUT_SOLUTION=PASS - no overlay or viewport-fixed action hides content
TASK_FLOW_ARCHITECTURE=PASS - select -> machine guidance -> seek -> Human QA remains one coherent journey
LINEAR_MULTISTEP_REASONING=NOT_APPLICABLE
REVIEW_BEFORE_COMMIT=NOT_APPLICABLE - machine analysis commits no product state
EXECUTION_STATE_SEPARATION=PASS - running, scored, limited and blocked are explicit and separate from Human QA status
RESOURCE_MANAGEMENT_SEPARATION=PASS - no model download, provider call, report retention or new resource library was introduced
POST_COMPLETION_DESTINATION=NOT_APPLICABLE - the score guides the next Human QA action on the same surface
TECHNICAL_VALIDATION=PASS - 137 relevant tests passed; JavaScript syntax and diff whitespace checks passed
CANDIDATE_PREVIEW=PASS - live current artifact 24 rendered 65/100, 100% deep coverage, high confidence, 7 technical risks and 8 suggested listening points without mutation
OWNER_ACCEPTANCE=REQUIRED - thresholds and weights are provisional until the owner confirms that machine ordering agrees with representative listening
OWNER_UX_GATE=PENDING
```

## Machine listening-list readability correction

```text
UX_CONTRACT
PRIMARY_USER=Owner switching among chapter audio while using machine suggestions to reduce listening time
PRIMARY_JOURNEY=select another chapter -> detail returns to its identity/player -> review the first five suggested points -> reveal more only when needed -> make the existing Human QA decision
PRIMARY_SURFACE=the selected-audio detail pane in Duyệt audio
INFORMATION_HIERARCHY=selected audio identity/player first; score and five highest-priority listening points second; remaining points on demand; Human QA decision after guidance
SCOPE_MODEL=scroll position and listening points belong to the currently selected artifact only
PRIMARY_CONTROLS=timestamp seek buttons and an explicit Xem thêm/Thu gọn control when more than five points exist
ADVANCED_CONTROLS=remaining listening points are progressively disclosed; technical configuration remains collapsed
STATES=selection change resets detail to top; five-or-fewer points have no disclosure; more-than-five points expose exact remaining count
BULK_DESTRUCTIVE=NOT_APPLICABLE
DISCOVERABILITY=the first five seek points remain directly visible below the machine score
ACCESSIBILITY=native details disclosure, full-width keyboard-operable seek rows, readable wrapping and no nested shortlist scrollbar
OWNER_PREFERENCE=NONE - this corrects the pictured clipping and scroll behavior without changing scoring or Human QA semantics
```

```text
WORKSPACE_CONTRACT
PRIMARY_TASK=compare queue items and review one selected audio
PRIMARY_WORKSPACE=master-detail review workspace
PERSISTENT_REGIONS=queue and selected detail remain side by side on desktop
CONTEXTUAL_REGIONS=machine result is replaced for the selected artifact
NAVIGATION_MODEL=selecting a different queue row resets its detail pane to the identity/player at the top
LAYOUT_ARCHETYPE=master-detail with one scrollbar per pane; progressive disclosure inside detail
VIEWPORT_BUDGET=five priority points are visible before optional expansion; no third nested scrollbar
CONTENT_REPLACEMENT_STRATEGY=new selection replaces the prior detail and prior scroll context
ADVANCED_CONTROL_STRATEGY=remaining points use native disclosure with an exact count
EXPECTED_SCROLL_BEHAVIOR=queue and detail may scroll independently on desktop; shortlist itself never scrolls independently
ARCHETYPE_RATIONALE=the user needs queue context and one readable detail, not a scroll area nested inside another scroll area
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS - five highest-priority timestamps remain visible directly under the machine summary
SCOPE_CLARITY=PASS - changing the selected artifact returns its detail pane to the identity/player at scroll position zero
APPLY_REAPPLY_RESET_EXPLICITNESS=NOT_APPLICABLE
ADVANCED_WITHOUT_DOMINATING=PASS - six remaining points in the representative case are behind an exact-count Xem thêm disclosure
DISABLED_STATE_EXPLANATION=PASS - unchanged from the accepted machine running/blocked states
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE
VISIBLE_HIERARCHY=PASS - player, machine summary, five priority points, next action and Human QA remain ordered
CONTROL_DENSITY=PASS - each point has a stable timestamp column and a wrapping text column; no clipped overlapping rows
COHERENT_APPLICATION_COMPOSITION=PASS - native disclosure and existing seek-button language are reused
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE
EXISTING_WORKFLOW_PRESERVATION=PASS - scoring, seeking and Human QA behavior are unchanged
INFORMATION_ARCHITECTURE=PASS - extra evidence remains contextual to the selected audio
NAVIGATION=PASS - Xem thêm/Thu gọn has an exact effect and selection replacement resets stale scroll context
WORKSPACE_LAYOUT=PASS - the detail pane is the only scroll owner around the machine list on desktop
VIEWPORT_BUDGET=PASS - five points are shown before progressive disclosure
PERSISTENT_CONTEXTUAL_CONTROLS=PASS - queue context and selected detail remain available together
LAYOUT_ARCHETYPE_FIT=PASS - master-detail plus progressive disclosure fits repeated chapter review
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS - rendered at 762px with no horizontal overflow and readable stacked rows
VERTICAL_SPRAWL_REDUCED=PASS - initial machine list changed from 11 nested-scroll rows to five rows plus one disclosure
WORKSPACE_LAYOUT_SOLUTION=PASS - the shortlist no longer owns a nested scrollbar
TASK_FLOW_ARCHITECTURE=PASS - select -> see identity/player -> inspect priority points -> optionally expand -> Human QA
LINEAR_MULTISTEP_REASONING=NOT_APPLICABLE
REVIEW_BEFORE_COMMIT=NOT_APPLICABLE
EXECUTION_STATE_SEPARATION=PASS - no change to machine-versus-Human-QA authority
RESOURCE_MANAGEMENT_SEPARATION=PASS - no persistence or resource-management behavior added
POST_COMPLETION_DESTINATION=NOT_APPLICABLE
TECHNICAL_VALIDATION=PASS - JavaScript syntax, 38 focused tests and diff whitespace checks passed
CANDIDATE_PREVIEW=PASS - live Chapter 2 showed 53/53 analyzed, 18 risks grouped into 11 points, five initially visible, Xem thêm 6 điểm, detail scrollTop zero, visible overflow and no horizontal overflow
OWNER_UX_GATE=NOT_REQUIRED - the owner already identified the concrete layout defect and this correction does not introduce a new product choice
```

## Machine finding to repair candidate v1

Owner decision (2026-09-12): machine QA must help improve the selected current
audio, not only assign a score. The first bounded slice supports deterministic,
offline correction for excessive leading/trailing silence and loudness mismatch.
Pacing, clipping, spoken-content, voice-match, and naturalness findings remain
Human-QA evidence until a remediation with a real controllable parameter exists.

```text
UX_CONTRACT
PRIMARY_USER=Owner reviewing one current chapter audio and deciding whether a machine finding should become a safe repair candidate
PRIMARY_JOURNEY=select current audio -> inspect a machine finding -> create an offline candidate for the exact segment when supported -> compare current and candidate -> accept or discard -> machine rechecks the resulting current artifact
PRIMARY_SURFACE=each actionable finding inside Điểm máy & đoạn cần nghe, before the existing Human QA decision
INFORMATION_HIERARCHY=current artifact and machine result first; one selected candidate comparison second; Human QA remains the final chapter decision
SCOPE_MODEL=a repair is bound to the exact current artifact ID/SHA and exact segment ID/audio SHA; only that segment may change after explicit acceptance
PRIMARY_CONTROLS=Nghe; Tạo bản sửa thử; Giữ bản hiện tại; Dùng bản sửa
ADVANCED_CONTROLS=unsupported findings may be copied into the existing Human QA repair form; technical evidence stays contextual
STATES=available -> creating -> candidate ready with before/after evidence -> accepting|discarding -> current artifact reloaded and rescored; stale/unsupported/failure states name the safe next action
BULK_DESTRUCTIVE=NOT_APPLICABLE; only one current candidate exists and it never replaces current audio before explicit acceptance
DISCOVERABILITY=the action sits on the exact machine finding; no Diagnostics route or backend term is required
ACCESSIBILITY=semantic buttons and audio labels, keyboard operation, live status, explicit effect and recovery copy
OWNER_PREFERENCE=never auto-replace audio from a machine score and do not retain rejected or superseded audio-attempt history
```

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Create and evaluate one bounded technical repair without calling TTS or changing the current audio prematurely
LINEAR_OR_NONLINEAR=linear for one finding: choose -> create candidate -> compare -> accept or discard
STEPS=choose supported finding -> create candidate -> inspect before/after evidence and listen A/B -> use repaired segment or keep current -> rerun machine QA
STEP_DEPENDENCIES=the artifact and segment bindings must still be current; only leading/trailing silence and loudness strategies are supported in v1
BACK_BEHAVIOR=leaving the candidate unaccepted keeps current audio and Human QA unchanged; selecting another audio discards local comparison context
NEXT_VALIDATION=server revalidates current artifact ID/SHA, segment membership/SHA, output path and measurable improvement before returning a candidate
FINAL_REVIEW_STEP=A/B playback and before/after metric are the review immediately before replacing current audio
PRIMARY_COMMIT_ACTION=Dùng bản sửa revalidates exact identity, promotes the candidate, rebuilds the chapter and removes superseded audio; it is not Human QA acceptance
CANCEL_EXIT_BEHAVIOR=Giữ bản hiện tại deletes the candidate file/row and changes no current artifact, segment, Job or QA state
DRAFT_PERSISTENCE=at most one temporary machine candidate per current chapter; it is restored after reload until explicitly used or discarded; rejected and superseded attempts are not retained
POST_SUBMIT_DESTINATION=the same selected chapter reloads at its new current artifact and machine QA runs again; Human QA returns to pending
```

```text
STATE_HAZARD_R2_S3
AUTHORITATIVE_SOURCE=chapter active_audio_artifact_id plus artifact SHA/path, matching timeline, JobChapter and verified segment audio SHA
REPRESENTATIVE_TRANSITION=current artifact A plus segment S -> offline candidate C -> explicit accept -> reassembled current artifact B with only S changed and Human QA pending
INVARIANT=creating/discarding C never changes A, S, Job, casting, text, custom voice or Human QA; stale identity fails closed; machine evidence never accepts Human QA
ACCEPTANCE=a supported silence/loudness point exposes exact-segment repair; candidate creation is offline and proves a changed SHA plus improved target metric; discard removes C with A unchanged; accept replaces only S, purges superseded audio/attempt history, resets Human QA, and rescans B; unsupported findings disclose the limitation and route to the existing Human QA repair form without silent rerender
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS - each supported finding has Tạo bản sửa thử; unsupported findings have Đưa vào yêu cầu sửa
SCOPE_CLARITY=PASS - candidate copy says it is for the exact segment and current chapter audio has not changed
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS - Dùng bản sửa and Giữ bản hiện tại are separate; reload restores the unresolved candidate instead of duplicating it
ADVANCED_WITHOUT_DOMINATING=PASS - machine evidence stays between the player and Human QA; render snapshot remains collapsed
DISABLED_STATE_EXPLANATION=PASS - unsupported findings explain that machine repair is not reliable and hand off to Human QA
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE - v1 operates on one exact segment candidate
VISIBLE_HIERARCHY=PASS - finding -> A/B comparison -> explicit candidate decision -> Human QA
CONTROL_DENSITY=PASS - one contextual action per finding; only five findings are initially visible
COHERENT_APPLICATION_COMPOSITION=PASS - current audio review remains the only post-render workspace
DESTRUCTIVE_DIFFERENTIATION=PASS - keeping current is secondary and non-destructive; replacing current is explicit and removes superseded audio under the one-current-audio contract
EXISTING_WORKFLOW_PRESERVATION=PASS - no provider call, PREPARE, START_RENDER or automatic Human QA decision was introduced
INFORMATION_ARCHITECTURE=PASS - score and limitations precede remediation; Human QA remains the final authority
NAVIGATION=PASS - candidate creation, comparison and decision stay in the selected chapter detail
WORKSPACE_LAYOUT=PASS - desktop detail owns its scroll; narrow layout stacks queue and detail without horizontal overflow
VIEWPORT_BUDGET=PASS - live 746px preview has no page-level horizontal overflow and retains readable action labels
PERSISTENT_CONTEXTUAL_CONTROLS=PASS - selected chapter, current player and candidate decision remain together
LAYOUT_ARCHETYPE_FIT=PASS - the master-detail Audio workspace is preserved
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS - finding and action columns remain legible at the live narrow viewport
WORKSPACE_LAYOUT_SOLUTION=PASS - live Chapter 5 shows actionable 491/519 ms trailing-silence findings and explicit Human-QA handoff for clipping/pacing
TASK_FLOW_ARCHITECTURE=PASS - an unresolved candidate is durable across reload and cannot silently replace current audio
REVIEW_BEFORE_COMMIT=PASS - A/B playback plus before/after metric precede Dùng bản sửa
EXECUTION_STATE_SEPARATION=PASS - creating a candidate is distinct from activating it and from Human QA
RESOURCE_MANAGEMENT_SEPARATION=PASS - rejected/superseded attempt history is removed while custom voices remain reusable resources
POST_COMPLETION_DESTINATION=PASS - after activation the same chapter reloads, rescans and returns to pending Human QA
TECHNICAL_VALIDATION=PASS - 86 focused integration tests, JavaScript syntax, Python compile and diff whitespace checks pass
CANDIDATE_PREVIEW=PARTIAL - live read-only preview confirms findings/actions/layout on canonical data; A/B mutation was intentionally verified only with isolated offline fixtures
OWNER_ACCEPTANCE=REQUIRED - owner should try one low-risk candidate and judge the A/B interaction before product acceptance
CADS_LIFECYCLE=BLOCKED - canonical executor hash is valid, but bootstrap fails closed because immutable legacy receipt expects AGENTS.md replacement hash 426790a9... while current committed AGENTS.md is 5d084edb...; no receipt or worker instruction was rewritten
```

## One repair path per chapter — superseding SOT

Owner decision (2026-09-12, later decision): the repeated per-finding actions in
the machine shortlist are not the product workflow. This decision supersedes the
primary-surface and per-segment interaction choices in **Machine finding to
repair candidate v1** above. Exact-segment candidate APIs may remain for safe
recovery of an already-created candidate, but the normal owner journey is one
chapter-scoped repair request and one replacement revision.

Durable decision: [DR-0001 — One chapter repair request and one replacement
revision](docs/decisions/0001-one-chapter-one-repair-request.md).

```text
UX_CONTRACT
PRIMARY_USER=Owner reviewing the current audio for one chapter
PRIMARY_JOURNEY=listen to prioritized findings -> select or skip findings -> create one repair request -> review the combined request -> create one replacement revision -> listen and decide Human QA
PRIMARY_SURFACE=one aggregate repair control below Điểm máy & đoạn cần nghe
INFORMATION_HIERARCHY=current audio and machine evidence first; per-row selection second; one chapter repair action third; Human QA remains final
SCOPE_MODEL=all selected findings belong to the exact current artifact and one chapter; a request never crosses chapter boundaries
PRIMARY_CONTROLS=Nghe; Chọn sửa or bỏ chọn; Tạo yêu cầu sửa cho N điểm
ADVANCED_CONTROLS=technical evidence and recovery of a pre-existing single-segment candidate stay contextual
STATES=no finding | findings selected | no selection | combined request review | repair plan | separate PREPARE | separate START_RENDER | replacement Human QA
BULK_DESTRUCTIVE=NOT_APPLICABLE; assembling the request does not change current audio and creates no provider work
DISCOVERABILITY=one visually grouped CTA follows the full finding list; no repeated create action appears on each row
ACCESSIBILITY=semantic checkboxes with finding/time names, exact selected count, keyboard operation and live scope copy
OWNER_PREFERENCE=one chapter repair path and one replacement revision; never require one revision per finding
```

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Combine the selected technical and listening findings into one repair request for the chapter
LINEAR_OR_NONLINEAR=linear: listen and select -> review one request -> create one replacement revision
STEPS=inspect findings -> select or skip -> create combined request -> review/edit Human QA details -> submit -> open repair plan -> separately PREPARE and START_RENDER
STEP_DEPENDENCIES=the exact artifact must remain current; at least one finding must be selected; Human QA review precedes mutation
BACK_BEHAVIOR=changing selection or leaving before submit changes no audio, Job, QA or provider state
NEXT_VALIDATION=the existing Human QA command revalidates current artifact scope and the repair plan freezes the reviewed request
FINAL_REVIEW_STEP=Human QA repair form summarizes every selected timestamp before submit
PRIMARY_COMMIT_ACTION=Gửi yêu cầu sửa records one request; later existing explicit gates create one replacement audio revision
CANCEL_EXIT_BEHAVIOR=close or navigate away before submit; current audio remains authoritative
DRAFT_PERSISTENCE=selection is local to the current artifact until the Human QA request is submitted
POST_SUBMIT_DESTINATION=the chapter repair plan in Production, followed by separate PREPARE and START_RENDER
```

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS - one aggregate CTA follows the complete machine shortlist; no create action repeats on a finding row
SCOPE_CLARITY=PASS - the bar says selected/available count, one chapter request and that current audio is unchanged
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS - every finding is selected by default and can be explicitly skipped before creating the combined request
ADVANCED_WITHOUT_DOMINATING=PASS - technical detail and recovery of an already-created exact-segment candidate remain contextual
DISABLED_STATE_EXPLANATION=PASS - zero selection changes the CTA to Chọn điểm cần sửa
BULK_DESTRUCTIVE_SAFETY=NOT_APPLICABLE - this step only drafts Human QA input and makes no audio/provider mutation
VISIBLE_HIERARCHY=PASS - listenable finding rows lead to one chapter-level repair bar and then the Human QA review form
CONTROL_DENSITY=PASS - repeated primary buttons were replaced by compact semantic checkboxes
COHERENT_APPLICATION_COMPOSITION=PASS - the existing Audio master-detail and downstream repair plan are reused
DESTRUCTIVE_DIFFERENTIATION=NOT_APPLICABLE - current audio is unchanged while assembling the request
EXISTING_WORKFLOW_PRESERVATION=PASS - Human QA submit, repair plan, PREPARE and START_RENDER remain separate
INFORMATION_ARCHITECTURE=PASS - finding evidence is item-level while repair creation is chapter-level
NAVIGATION=PASS - the aggregate action opens the existing Human QA review in the same selected chapter
WORKSPACE_LAYOUT=PASS - desktop keeps finding and checkbox on one row; narrow layout stacks them without horizontal overflow
VIEWPORT_BUDGET=PASS - one CTA replaces repeated wide buttons and remains visible after the five-point shortlist
PERSISTENT_CONTEXTUAL_CONTROLS=PASS - selected count and exact current chapter stay visible in the existing detail pane
LAYOUT_ARCHETYPE_FIT=PASS - master-detail with one contextual chapter action remains appropriate
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS - Chromium evidence at 1366x768 and 700x900 has no horizontal overflow
VERTICAL_SPRAWL_REDUCED=NOT_APPLICABLE - this goal removes repeated actions but does not claim fewer finding rows
WORKSPACE_LAYOUT_SOLUTION=PASS - one aggregate action replaces per-item create actions on the reported surface
TASK_FLOW_ARCHITECTURE=PASS - listen/select -> one request review -> existing repair plan -> separate PREPARE -> separate START_RENDER
LINEAR_MULTISTEP_REASONING=PASS - the user reviews combined timestamps before the existing Human QA submit
REVIEW_BEFORE_COMMIT=PASS - the Human QA form contains every selected timestamp and preserves manual options before submit
EXECUTION_STATE_SEPARATION=PASS - selecting or drafting creates no provider work; rendering remains separately authorized
RESOURCE_MANAGEMENT_SEPARATION=PASS - current artifact and historical resource rules are unchanged
POST_COMPLETION_DESTINATION=PASS - existing Production repair plan remains the destination after submit
TECHNICAL_VALIDATION=PASS - 99 focused tests, JavaScript syntax and diff whitespace checks passed
CANDIDATE_PREVIEW=PASS - isolated Chromium rendered six findings with zero per-item create actions; deselect changed 6 to 5; one CTA drafted five timestamps; desktop/narrow overflow false; mutation calls empty
FUNCTION_EXISTS=PASS
DISCOVERABLE=PASS
UNDERSTANDABLE=PASS
HIERARCHY_SUPPORTS_WORKFLOW=PASS
OWNER_UX_ACCEPTED=PENDING_REAL_USE - the owner approved the structural SOT; the changed candidate has not yet been accepted through owner real use
OWNER_UX_GATE=NOT_REQUIRED - no unresolved material product choice remains
```

## Backend closure for one chapter repair request

Audit verdict (2026-09-12): `MATERIAL_GAPS_FOUND`. The aggregate UI drafts one
request, but the current backend drops machine-repair identity at the Human QA
schema boundary, clears the saved positions when repair review opens, and pins a
`repair_instruction` that no render worker consumes. Persistence and lifecycle
gates exist; executable remediation is incomplete.

Durable design: [DR-0002 — Compile and execute one immutable chapter repair
instruction](docs/decisions/0002-compile-and-execute-one-chapter-repair-instruction.md).

```text
SOT
OUTCOME=Selected findings for one exact current artifact survive Human QA and repair review, compile into one immutable chapter instruction, and are executed together in one replacement Job
DELIVERY_DELTA=EXECUTABLE_CAPABILITY plus USER_VISIBLE_BEHAVIOR
RISK_STATE=R2/S3
AUTHORITATIVE_SOURCE=chapter active_audio_artifact_id, artifact SHA/job_chapter_id, verified source segment IDs/audio SHA, Human QA evidence, reviewed repair draft, prepared Job snapshot
REPRESENTATIVE_TRANSITION=current artifact A + selected findings -> one reviewed immutable instruction I -> explicit PREPARE -> explicit START_RENDER -> replacement artifact B pending Human QA
INVARIANT=A remains current until B files and hashes are verified; PREPARE never renders; automatic execution never calls a provider; unsupported or stale instructions fail closed
ALLOWED=repair marker schema, Human QA/repair evidence propagation, immutable instruction compiler, existing Pipeline worker integration, focused offline tests and UI handoff correction
PROHIBITED=canonical DB mutation, PREPARE, START_RENDER, Gemini/VieNeu/provider calls, Human QA decision, destructive cleanup, push/merge/deploy
```

```text
PLAN
1_AUDIT=Trace selected finding identity through Human QA, plan, draft, PREPARE snapshot and worker
2_SOT=Freeze exact bindings, supported algorithms, fail-closed behavior and acceptance in TASK plus DR-0002
3_CHANGE_A=Preserve artifact-bound segment SHA, risk kind and repair kind through every evidence layer and reload
4_CHANGE_B=Compile deduplicated supported actions during replacement PREPARE and expose unsupported-marker count explicitly
5_CHANGE_C=At explicit START_RENDER, reuse the exact verified source segments, apply every supported offline transform, verify target metrics, and assemble one replacement artifact
6_ACCEPTANCE=Use isolated temporary DB/files, fake TTS that fails if called, stale/hash/unsupported negative paths, API evidence round-trip, JS syntax and browser fixture
7_CONSEQUENCE=Record actual evidence and leave canonical owner/provider acceptance pending
```

Acceptance:

1. One Human QA submission stores every selected timestamp with exact segment ID,
   segment audio SHA, risk kind, repair kind and stable finding key.
2. Plan, draft, review and prepared snapshot preserve those bindings; opening
   draft review preloads them instead of starting from an empty list.
3. PREPARE rejects stale artifact/segment/hash bindings. Duplicate actions are
   deterministic and one source segment may receive multiple compatible filters.
4. START_RENDER for a fully supported instruction copies unchanged verified
   source segments, applies all selected silence/loudness transforms offline,
   verifies every target metric improved, then uses the existing one-artifact
   assembly/activation path. The TTS provider is not called.
5. Any unimplemented semantic repair (for example repeated words or an
   unsupported marker) blocks automatic execution with a named reason. It is
   never silently omitted and never produces an unchanged replacement.
6. The old current artifact remains authoritative after any validation or
   processing failure. A successful replacement returns to pending Human QA.

```text
ACCEPTANCE_RESULT
STATUS=CHECKPOINT_OK
FUNCTION_EXISTS=PASS - the existing Pipeline consumes one compiled chapter instruction and creates one replacement bundle
SCHEMA_ROUND_TRIP=PASS - machine finding segment ID, segment SHA, risk kind, repair kind and stable key survive Human QA, plan, draft and review evidence
MULTI_FIX_EXECUTION=PASS - isolated worker applied leading and trailing silence transforms to one source segment in one batch while copying the unselected segment unchanged
PROVIDER_SAFETY=PASS - fake TTS raises on invocation; completed replacement recorded zero TTS calls
STALE_BINDING=PASS - mismatched source Segment SHA is rejected before replacement files are written
UNSUPPORTED_SEMANTICS=PASS - unsupported/manual, repeated-word, global-speed and local-pacing intent produce explicit execution blockers; START_RENDER is rejected and hidden
ARTIFACT_COMMIT=PASS - isolated Pipeline created the replacement output and did not change the current Artifact before the worker commit point
UI_HANDOFF=PASS - browser fixture preserved 5/5 exact segment SHA bindings, 3 supported automatic actions, manual selections and zero mutation calls; desktop and 700px layouts have no horizontal overflow
REGRESSION=PASS - 143 affected API, PREPARE/START, projection, worker, artifact, repair and browser tests pass; Python compile, JavaScript syntax and diff whitespace checks pass
CANONICAL_RUNTIME=NOT_RUN - no canonical DB mutation, PREPARE, START_RENDER, provider call or Human QA decision was authorized
OWNER_ACCEPTANCE=PENDING_REAL_USE
CADS_MACHINE_STATE=UNAVAILABLE - this worktree has no scripts/ai.py wrapper; checkpoints were not edited by hand
```

Consequence: the backend now has an executable mechanism for the supported
technical repair types and one authoritative chapter-level path. The scope is
intentionally not claimed complete for repeated words, global speed or local
prosody; those requests stop visibly until a truthful executor is implemented.

### Completion amendment — semantic and pacing repairs

Owner direction (2026-09-13): continue and complete the audio-repair path. This
amends the earlier bounded executor without changing DR-0001's one-request / one-
replacement decision or the separate PREPARE and START_RENDER authority gates.

```text
AMENDED_OUTCOME=One reviewed chapter request may combine offline transforms, whole-chapter speed adjustment and exact-segment resynthesis, then produce one replacement revision
EXECUTION_STRATEGY=reuse unchanged source segments; apply deterministic trim/loudness/tempo filters; resynthesize only exact segments whose issue cannot be corrected safely by filtering
MARKER_RESOLUTION=exact machine segment binding when present; otherwise resolve reviewed timestamp through the verified current timeline and freeze the resulting segment ID/SHA at PREPARE
REPEATED_WORDS=re-synthesize only reviewed repeated-word marker segments; a checkbox without a reviewed location fails closed
GLOBAL_SPEED=apply the reviewed tempo multiplier to every segment offline
LOCAL_PACING=apply each reviewed marker local_pace to its exact segment; requesting local pacing without a local pace marker fails closed
UNSUPPORTED_MACHINE_FINDING=hard clipping, abnormal internal silence or pacing may request exact-segment resynthesis; replacement remains pending Human QA
PROVIDER_AUTHORITY=resynthesis is executed only after explicit START_RENDER; tests use fake TTS and no provider call
INVARIANT=every reviewed repair is either executed or named as a blocker; no silent omission or unchanged success
```

```text
COMPLETION_ACCEPTANCE_RESULT
STATUS=IMPLEMENTATION_COMPLETE_OFFLINE
ONE_REPLACEMENT=PASS - one compiled immutable instruction covers all selected findings and produces one replacement chapter artifact
OFFLINE_TRANSFORMS=PASS - silence trim, loudness normalization, whole-chapter tempo and per-segment tempo execute without TTS
TEMPO_PRECEDENCE=PASS - a reviewed local pace overrides, rather than multiplies, the global chapter speed for that exact segment
SEMANTIC_REPAIR=PASS - repeated words and non-filterable findings re-synthesize only the exact timeline/segment binding; unchanged segments are copied
PROVIDER_BOUNDARY=PASS - PREPARE only freezes the instruction; hybrid execution is admitted only by explicit START_RENDER and calls the injected TTS dependency only for exact resynthesis segments
FAIL_CLOSED=PASS - missing repeated-word location, missing local pace, missing timestamp/segment, stale SHA, unsupported repair kind and partial TTS failure stop without changing the current artifact; partial files are removed
UI_TRUTHFULNESS=PASS - aggregate request remains the only primary path; review displays the frozen speed, requires actionable locations, and prepared/start copy distinguishes offline-only from exact-segment TTS
FOCUSED_REGRESSION=PASS - 196 affected API, evidence, PREPARE/START_RENDER, projection, worker, QA and browser tests pass after the completion amendment
FULL_SUITE=PARTIAL - 2132-test discovery completed with 2127 pass, 1 skipped, and 4 unrelated pre-existing/worktree failures in casting marker lookup, two older browser journeys and an outdated asset-version assertion
LIVE_FIXTURE_UI=PASS - 18772 shows one aggregate CTA for six findings and drafts one form with all six timestamps; no submit or mutation was performed
CANONICAL_RUNTIME=NOT_RUN - schema-16 canonical DB is newer than this worktree's schema-12 application; no canonical DB, provider, Human QA, PREPARE or START_RENDER operation was performed
OWNER_ACCEPTANCE=PENDING_REAL_USE
```

Consequence: the requested one-path repair workflow is now implemented end to
end in this worktree. Release/promotion and a real owner-authorized provider run
remain separate gates because the canonical runtime is a different, newer
application/database generation.

## Canonical runtime upgrade — fresh-data authorization

Owner authorization (2026-09-13): “Kệ dữ liệu cũ, có thể render lại.” Existing
project/runtime data may be retired so the completed product can become the
canonical `8772` runtime. Secrets and reusable provider/voice configuration are
not included in that authorization and must be preserved.

```text
PROMOTION_SOT
OUTCOME=Run the 84-commit-newer product-reconciliation branch as the canonical port-8772 application on a fresh schema-16 data root
SIDE_EFFECT=Move the exact old canonical data directory to a timestamped recoverable sibling; initialize a new empty schema-16 data directory; keep the existing secrets junction/target unchanged
ALLOWED=stop the fixture listener on 18772, archive canonical data, bootstrap a fresh runtime schema, start the supervised 8772 launcher from this worktree, verify runtime/data/UI identity
PROHIBITED=delete the archived data, print/copy secrets, invoke PREPARE or START_RENDER, call Gemini/VieNeu/TTS, create owner project data, mutate the dirty main checkout, force-push
PRECHECK=branch ancestry, listener command lines, data/secrets link targets, database quick_check/schema, focused offline acceptance
ACCEPTANCE=8772 reports the intended source root, schema 16, canonical DB, HTTP 200 and empty user/project state; served repair UI is the new one-path version; no provider or production command is issued
ROLLBACK=stop 8772, move the fresh data aside, restore the archived data directory, and relaunch the prior checkout if the owner later requests it
```

```text
PROMOTION_RESULT
STATUS=CANONICAL_RUNTIME_UPGRADED
SOURCE_ROOT=D:\Youtube\_worktrees\story-audio-product-reconciliation
SOURCE_BASELINE=branch codex/story-audio-product-reconciliation at 0b10ebd27325dcf7ea7b1c651a7dd12c8c5bfde4, 84 commits ahead of the previous canonical checkout; the running product also includes the preserved task/owner working-tree changes listed by Git
OLD_DATA=RECOVERABLE at D:\Youtube\Story Trans And Audio\data.__pre_upgrade_20260913_004716; it was moved, not deleted
NEW_DATA=PASS - D:\Youtube\Story Trans And Audio\data\app.db initialized at schema 16; SQLite quick_check is ok, foreign-key violations are zero, and books/chapters/jobs/artifacts/segments all start at zero
RUNTIME=PASS - http://127.0.0.1:8772 reports the intended source root, canonical DB, schema 16/latest 16, PRODUCTION mode, authentication enabled and PREPARE readiness
BACKEND=PASS - the served application includes the hybrid one-request executor that combines offline transforms and exact-segment TTS when a later explicit START_RENDER authorizes it
UI=PASS - a real browser reload on 8772 shows “Hệ thống sẵn sàng”; Sách is empty and presents “Chọn EPUB từ máy”; Duyệt audio reports zero items without stale runtime data
PROVIDER_SIDE_EFFECT=NONE - no EPUB import, PREPARE, START_RENDER, Gemini, VieNeu or TTS action was issued during promotion
ROLLBACK_READY=PASS - the prior canonical data directory remains intact at the recorded sibling path
OWNER_NEXT_ACTION=Import an EPUB on the Sách screen, configure voices, then explicitly start a new render when ready
```

Consequence: port `8772` now serves the completed product-reconciliation
working tree against a clean canonical schema-16 database. This is a runtime
upgrade, not a claim that the dirty multi-owner working tree has been committed
or promoted as an immutable Git release.

## Canonical real-use repair acceptance — Chapter 1

Owner authorization (2026-09-13): create fresh project data, render, use the
machine findings to exercise the one-request repair path, and ignore/re-render
retired data. Human acceptance of the final listening result remains reserved
for the owner.

```text
REAL_USE_OUTCOME=One current Chapter 1 audio was scored, eight findings were selected once, one replacement was rendered, residual clipping exposed a bounded algorithm defect, and one offline correction produced the current replacement
INITIAL_ARTIFACT=Artifact 3, 300000 ms, machine score 0/100, 17 technical signs, 8 selected findings
FIRST_REPLACEMENT=Artifact 6, 299361 ms, 49/49 verified, five exact clipping segments resynthesized plus three offline transforms, machine signs reduced 17 -> 11 but two clipping findings remained
ROOT_CAUSE=Resynthesis is nondeterministic and cannot guarantee that a full-scale peak disappears
BOUNDED_CORRECTION=Hard clipping now compiles to deterministic reduce_peak; only findings with a supported deterministic repair receive selection controls; listening-only findings stay visible but are not silently turned into resynthesis
SECOND_REPLACEMENT=Artifact 9, 299120 ms, 49/49 verified, four offline transforms, zero segment attempts/provider calls, previous artifact removed only after verified activation
FINAL_MACHINE_QA=64/100, 100 percent coverage, high confidence, 7 technical signs, hard_clipping=0, near_clipping=1, silence=2, pacing=3, loudness=1
STOP_LOSS=No third automatic repair loop. Remaining relative/statistical findings require listening because successive normalization can move the cohort baseline and create new outliers
HUMAN_QA=PENDING_OWNER_LISTENING - machine score is technical triage and does not decide spoken-content correctness, voice match or naturalness
```

```text
REAL_USE_ACCEPTANCE_RESULT
ONE_CHAPTER_REQUEST=PASS - all eight first-pass bindings survived Human QA, plan, draft, review and PREPARE
ONE_REPLACEMENT_JOB=PASS - Job 2 reused unchanged segments, resynthesized exactly five bound segments and applied three offline transforms
DETERMINISTIC_CLIPPING_FIX=PASS - Job 3 applied four offline transforms with zero provider attempts; hard clipping reduced from two findings to zero
SAFE_ACTIVATION=PASS - each prior artifact remained current until its replacement files/hashes were verified, then was removed from the active data set
UI_RECOVERY=PASS - saved markers reload after navigation and machine-bound review rows display Clipping, Khoảng nghỉ dài and Âm lượng không đều instead of the generic manual issue label
SPEED_DEFAULT=PASS - neither Human QA nor repair plan silently selects a chapter speed change
FOCUSED_TESTS=PASS - peak-reduction, aggregate-browser, QA identity, repair compiler, Human QA and production-command checks pass
OWNER_ACCEPTANCE=PENDING_REAL_USE_LISTENING
```

## One continuous post-request repair journey — superseding SOT

Observed owner evidence (2026-09-13): after `Gửi yêu cầu sửa`, the selected
audio disappears from the pending queue while the stale detail remains visible,
and the only continuation is `Mở kế hoạch sửa trong Sản xuất`. The following
contract supersedes the post-submit destination and visible multi-confirmation
steps in **One repair path per chapter — superseding SOT**. Backend evidence
records remain immutable and sequential; only their presentation is converged.

```text
UX_CONTRACT
PRIMARY_USER=Owner who has finished listening, selected all relevant findings, and wants one replacement for the chapter
PRIMARY_JOURNEY=submit one repair request -> review the whole replacement request -> prepare replacement -> explicitly start creation -> listen to the replacement -> accept or request another bounded repair
PRIMARY_SURFACE=one focused Sửa audio journey reached automatically from Duyệt audio; the owner is never left on an empty queue with stale detail
INFORMATION_HIERARCHY=chapter and QA request -> editable combined repair summary and all positions -> safety/retention note -> one next action; evidence IDs and voice-map details stay disclosed
SCOPE_MODEL=one exact current artifact and one chapter; every selected finding is carried into the same replacement revision
PRIMARY_CONTROLS=Xác nhận bản sửa; Chuẩn bị bản thay thế; Bắt đầu tạo bản thay thế; Nghe và duyệt
ADVANCED_CONTROLS=technical evidence, effective voice map, and internal command state
STATES=request recorded and opening review; whole-request review; saving review; ready to prepare; prepared and awaiting explicit render; rendering; replacement awaiting Human QA; complete or actionable error
BULK_DESTRUCTIVE=the old current audio is retained until replacement files are verified, then removed under the existing one-current-audio contract
DISCOVERABILITY=successful repair submission automatically opens the next step; no cross-workspace handoff button or hidden navigation knowledge is required
ACCESSIBILITY=one visible primary action per state, explicit progress text, keyboard controls, no horizontal overflow at desktop or narrow viewport
OWNER_PREFERENCE=one repair path for the whole chapter rather than one path per finding or multiple internal confirmation screens
```

```text
CREATE_FLOW_CONTRACT
TASK_GOAL=Create one reviewed replacement audio from one aggregate chapter repair request
LINEAR_OR_NONLINEAR=linear; the only optional branch is editing the combined request before confirmation
STEPS=submit request -> automatically open combined review -> confirm once -> prepare explicitly -> start render explicitly -> monitor -> listen -> Human QA decision
STEP_DEPENDENCIES=combined review must bind the current artifact and requested positions; PREPARE requires reviewed evidence and storage readiness; START_RENDER requires a prepared Job
BACK_BEHAVIOR=Quay lại nghe returns to Audio without deleting the persisted request; reopening resumes the first incomplete repair state
NEXT_VALIDATION=each existing backend command revalidates exact chapter, artifact, QA, plan, draft, and marker identities; a failed command stops the sequence with an actionable retry
FINAL_REVIEW_STEP=Kiểm tra toàn bộ bản sửa is the single user review before PREPARE
PRIMARY_COMMIT_ACTION=Xác nhận bản sửa stores the plan, compiles the draft, and stores its review through the existing idempotent evidence commands; it does not PREPARE, render, call a provider, or replace audio
CANCEL_EXIT_BEHAVIOR=leaving review preserves the request and current audio; no partial media side effect occurs
DRAFT_PERSISTENCE=successful internal evidence steps remain persisted so retry resumes instead of duplicating or restarting
POST_SUBMIT_DESTINATION=focused Sửa audio review for the same chapter, automatically
```

Acceptance:

1. A successful `HUMAN_QA_NEEDS_FIXES` immediately opens the same chapter's
   combined repair review; the Audio queue is never shown as an apparent dead end.
2. The combined review exposes request settings and every saved position, then
   uses one owner action to persist the existing plan/draft/review evidence chain.
3. A failure at any evidence step stops visibly; retry resumes from persisted
   evidence and never silently reaches PREPARE or START_RENDER.
4. `Chuẩn bị bản thay thế` and `Bắt đầu tạo bản thay thế` remain separate,
   explicit owner actions. Human QA remains the final journey decision.
5. Desktop and narrow browser evidence show one primary action, readable scope,
   no stale empty-queue state, and no horizontal overflow.

```text
UX_IMPLEMENTATION_REVIEW
PRIMARY_SURFACE_DISCOVERABILITY=PASS - successful submit calls the focused repair opener directly; a persisted request reopened from Audio says Tiếp tục sửa audio
SCOPE_CLARITY=PASS - the screen names Chapter, current artifact context, one combined request, and all carried positions
APPLY_REAPPLY_RESET_EXPLICITNESS=PASS - one Xác nhận bản sửa persists only the three existing evidence states; retry resumes from whichever evidence already exists
ADVANCED_WITHOUT_DOMINATING=PASS - evidence IDs, voice map, and version details stay collapsed
DISABLED_STATE_EXPLANATION=PASS - storage failure names required and available space before PREPARE
BULK_DESTRUCTIVE_SAFETY=PASS - current audio is explicitly retained until verified replacement activation
VISIBLE_HIERARCHY=PASS - exactly one primary action is visible in combined review and exactly one primary PREPARE action follows
CONTROL_DENSITY=PASS - five visible internal actions were replaced by one review action; PREPARE and START_RENDER remain later gates
COHERENT_APPLICATION_COMPOSITION=PASS - Audio hands the same chapter context directly into the focused repair task without an empty intermediate queue
EXISTING_WORKFLOW_PRESERVATION=PASS - immutable plan, draft, review, PREPARE, START_RENDER, replacement activation, and Human QA backend semantics remain intact
INFORMATION_ARCHITECTURE=PASS - owner-facing repair intent is separated from collapsed technical evidence records
NAVIGATION=PASS - post-submit destination is automatic and Back returns to Audio with the persisted request intact
WORKSPACE_LAYOUT=PASS - real 8772 data shows the four-step repair sequence and three saved markers in one focused work area
VIEWPORT_BUDGET=PASS - fixture browser at 1366x768 and 700x900 has no horizontal overflow
PERSISTENT_CONTEXTUAL_CONTROLS=PASS - marker bindings survive Audio to repair navigation and reload
LAYOUT_ARCHETYPE_FIT=PASS - linear task flow is used for one dependent repair journey
RESPONSIVE_WORKSPACE_BEHAVIOR=PASS - fields and actions stack at narrow width; checkbox and marker labels remain readable
VERTICAL_SPRAWL_REDUCED=PASS - redundant plan/apply/draft review screens are removed, while long marker evidence remains naturally scrollable
TASK_FLOW_ARCHITECTURE=PASS - submit -> one review -> PREPARE -> START_RENDER -> Human QA
LINEAR_MULTISTEP_REASONING=PASS - four visible steps match the actual dependency order
REVIEW_BEFORE_COMMIT=PASS - the whole request and all marker positions are editable before one confirmation
EXECUTION_STATE_SEPARATION=PASS - unified confirmation performs no PREPARE, provider call, render, or artifact replacement
POST_COMPLETION_DESTINATION=PASS - verified replacement returns to the existing Duyệt audio Human QA endpoint
TECHNICAL_VALIDATION=PASS - 55 focused UI, responsive, command, Phase 5 and isolated full golden-journey tests pass; JavaScript syntax and diff whitespace pass
CANDIDATE_PREVIEW=PASS - live canonical 8772 read-only inspection shows Chapter 1 in Kiểm tra toàn bộ bản sửa with 3 persisted machine positions and one Xác nhận bản sửa action
OWNER_ACCEPTANCE=REQUIRED - the owner should continue from the open canonical screen; no canonical PREPARE, START_RENDER, provider or Human QA decision was issued by this implementation turn
```

## PR #8 release qualification — CADS evidence continuity

Authority (2026-09-13): the Owner explicitly set the starting truth for this
release task to `PRODUCT_ACCEPTED / RELEASE_NOT_YET_QUALIFIED` and authorized
qualification, merge/promotion, activation, and active-runtime verification.
This is acceptance of the unified chapter-audio repair journey delivered by
commit `8268854cfe2d47b14c81485d218836d7241fe23d`; it does not retroactively
declare every older Story Audio UAT or every historical production output
accepted.

The release work follows CADS commit
`3dab33a621c2b25db14a09219a836c628c0a0a83`. Product Acceptance, Release
Qualification, and Runtime Activation are three separate claims.

```text
ACCEPTED_CANDIDATE=8268854cfe2d47b14c81485d218836d7241fe23d
ACCEPTED_BEHAVIOR=one continuous chapter repair journey: submit -> combined review -> confirm once -> PREPARE -> explicit START_RENDER -> replacement Human QA
PRODUCT_ACCEPTANCE=PRODUCT_ACCEPTED_BY_OWNER
RELEASE_QUALIFICATION=RELEASE_NOT_YET_QUALIFIED
RUNTIME_ACTIVATION=NOT_ACTIVATED_BY_THIS_RELEASE_TASK
QUALIFICATION_SUBJECT=the exact PR #8 headRefOid reported by the successful Story Audio Product CI run and repeated in the PR qualification attestation
DELIVERY_FORM=direct Git source; no installer or separately built application bundle
SUPPORTED_PLATFORM=Windows
SUPPORTED_RUNTIME=Python >=3.11; qualification CI uses Python 3.12 and Node 22 for browser acceptance
DEPENDENCIES=pyproject.toml plus system FFmpeg and Chrome or Edge Chromium
PROVIDER_BOUNDARY=offline tests and fakes only; no Gemini, VieNeu/TTS, PREPARE, START_RENDER, Human QA, or canonical-data mutation during qualification
CONFIG_BOUNDARY=isolated temporary STORY_AUDIO_DATA_DIR for checks; canonical activation uses run_app.ps1 and the protected data/app.db only after qualification and promotion
```

### Acceptance continuity after the accepted candidate

| Accepted criterion | Post-candidate assessment | Required evidence on the qualification subject |
| --- | --- | --- |
| Submit opens the same chapter's combined repair review | Application implementation unchanged | Re-run focused repair browser acceptance and the full golden journey |
| One confirmation persists plan, draft, and review | Application implementation unchanged; Human QA fixture was isolated from the real provider | Re-run Human QA API, repair command, and browser acceptance checks with fakes |
| Failure stops visibly and retry resumes persisted evidence | Application implementation unchanged | Re-run negative/retry tests; no oracle weakening permitted |
| PREPARE and START_RENDER remain separate explicit actions | Application implementation unchanged | Re-run command boundary and golden-journey checks; verify zero provider/canonical effects |
| Desktop/narrow layout and navigation remain continuous | Browser harness timing/navigation changed | Treat prior browser evidence as not portable; re-run rendered browser evidence and corroborate Back behavior with the independent contextual-return browser test |

Post-candidate delta classification:

- `QUALIFICATION_ONLY`: CI runner/environment setup, dependency declarations,
  interpreter binding, portable temporary roots, and portable process/path test
  setup. These do not establish Product Acceptance.
- `ACCEPTANCE_PRESERVING`: bounded waits and browser-profile cleanup retries
  where assertions, visible behavior, and failure conditions are unchanged.
- `ORACLE_CHANGING`: golden-journey navigation mechanics, provider-isolation
  fixtures, and integrity-fixture provenance updates. Their old results are not
  carried forward; affected criteria must be rerun on the final subject and
  corroborated where an edited harness would otherwise self-prove its change.
- `ACCEPTANCE_IMPACTING`: the unrelated cross-platform Character Bible source
  behavior introduced after `8268854` is removed from this PR so the accepted
  application surface stays frozen.
- `UNKNOWN`: none after the complete `8268854..qualification-subject` diff is
  reviewed. Any later unknown or application-source delta reopens the affected
  criterion and returns the release to `RELEASE_NOT_YET_QUALIFIED`.

Qualification is achieved only when the exact subject is clean and pushed,
focused affected checks pass, the rendered repair/golden evidence passes, the
complete isolated regression suite passes on that same SHA in the declared
Windows environment, and the PR attestation binds those results to the same
headRefOid. Merge and runtime activation happen only after that point.

### Qualification convergence record

The first qualification subject, commit
`134aff6482ae0e55a7dd2158e6e7d936e5893d6f`, passed all 46 local Project CI
groups but failed GitHub run `34720059221` while waiting 30 seconds for a
speaker-review command observation. The exact failing check passed five
consecutive local reruns in 3.2–3.8 seconds. The failure is therefore handled
as one shared Windows browser-harness timing boundary, not as another product
feature change or a series of per-test exceptions.

```text
STATE_EVENT_EXPECTED_OBSERVED=isolated speaker review + map command -> command is observed and refreshed manual-review count converges -> GitHub Windows runner exceeded the harness's independent 30-second observation budget
SHARED_CORRECTION=all standalone Chromium acceptance harnesses use one bounded timeout floor; GitHub Windows declares 45000 ms while local defaults remain unchanged
ORACLE_PROTECTION=command submission is observed before its asynchronous refresh, and the existing independent assertion still requires the rendered manual-review count to change from 3 to 2
APPLICATION_DELTA=NONE relative to accepted candidate 8268854cfe2d47b14c81485d218836d7241fe23d
FOCUSED_EVIDENCE=17 affected browser tests pass; the exact former failing test passes five consecutive reruns
RELEASE_QUALIFICATION=RELEASE_NOT_YET_QUALIFIED until the final committed subject passes full local Project CI and GitHub Story Audio Product CI
```

GitHub run `34721305622` on subject
`bfbebe08cc1f42f0d4323abfc81a654cc95a5ca7` then passed the affected browser
and golden-journey groups, but failed the listening-checklist symlink rejection
on a runner where native symlink creation is available. This reopens the
artifact-integrity criterion: the absolute-path helper resolved the link before
the shared local-file validator could inspect it. The bounded correction keeps
lexical path identity until validation, while data-root identity is still
resolved explicitly for canonical-root protection. The existing real-symlink
oracle is unchanged and must pass on the final GitHub subject; the
platform-independent mocked symlink check must also remain green.

GitHub run `34722048251` on subject
`ba73e644a117f5c680b306a4b75ea73a72fd4836` passed the browser, golden-journey,
and native-symlink criteria, then reached the TTS integration group and exposed
28 identical fixture setup errors: the offline test attempted to patch
`vieneu.Vieneu` by importing an optional provider package not installed in the
declared qualification environment. The shared correction supplies a local
module fake through `sys.modules`; it neither installs nor loads VieNeu and does
not change product code or provider behavior. All TTS assertions remain
unchanged and must be rerun on the final subject.

The first full local qualification run after that provider-fixture correction,
on subject `394f2185beba0cbd476b343d1aa40cd68d53060e`, passed every group through
the final voice-override browser check, where one immediate layout snapshot
reported the primary action outside the viewport after changing Chromium from
1366x768 to 1920x1080. The same rendered check had passed earlier full runs,
and the sibling character-assignment check already waits for two animation
frames after the identical viewport transition. The bounded correction waits
for the same existing visible-action and no-horizontal-overflow conditions to
converge before recording them; it does not change either assertion, the UI,
or product behavior. The exact check must pass five consecutive focused runs
and the complete Project CI suite on the final qualification subject.

GitHub run `34739318551` on subject
`7b1496f3b730bc83e0b986a816fb0b51811031a9` reproduced a shared route race in
the full golden journey: after Production started an asynchronous scope restore,
the user-visible transition to Jobs could complete before that older request.
The late response then replaced the URL with the Production hash while the
rendered route remained Jobs, so the visible return link pointed at the current
URL and could not trigger a route change. The correction binds each Production
route restore to an application-route epoch and discards its post-await writes
after any newer route transition. This is an acceptance-preserving concurrency
fix at the shared navigation boundary, not a new feature or a relaxed oracle.
The visible link, Back navigation, exact scope restoration, and full golden
journey assertions remain required on the final subject.

The golden browser oracle now reproduces that timing boundary deterministically:
it holds one range-readiness response, moves through the real application router
to Jobs, releases the older response, and requires both the rendered route and
URL to remain on Jobs before exercising the visible return link and browser Back.
This adds discriminating evidence for the root cause without replacing or
weakening the owner-visible navigation assertions.

The deterministic probe also exposed why the first guard attempt had no effect:
`ui/app.js` contained an older function declaration plus a later active
`restoreProductionRangeScope` reassignment. The later path was the writer that
changed the hash. The correction removes the dead duplicate and places the
epoch guard on the single active restore boundary.

Focused evidence after the consolidated boundary: the static route contract
passes 17/17 checks, and the strengthened Chrome golden journey passes five
consecutive runs with the deterministic late-response race, visible return
link, browser Back, and exact chapter scope all enabled.
