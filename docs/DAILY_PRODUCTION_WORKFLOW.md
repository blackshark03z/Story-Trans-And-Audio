# Daily Production Workflow

**Status:** Canonical target product workflow
**Created:** 2026-07-20
**Decision:** `CHOOSE_C_DEFER_CH369_AND_ACTIVATE_DAILY_PRODUCTION_UX_ROADMAP`

## Product Goal

Story Audio is a local daily-production application for turning approved book chapters into production audio. The product should be organized around operator intent, not backend entities.

An operator can:

- Add and manage reusable voices.
- Configure books, Character Bible records, aliases, narrator/default/fallback voices, and optional character overrides.
- Select one chapter or a chapter range.
- Follow a sequential guided production workflow.
- Resolve only actual exceptions.
- Approve voice routing.
- Prepare work without starting synthesis.
- Explicitly start and monitor rendering.
- Review completed audio.
- Play and download production outputs.

The UI must always make the next valid action clear.

## Canonical Task Projection

The Production workbench reads one read-only projection from
`GET /api/production/task-projection`. It is the application-layer source of
truth for the current task, affected chapter, ordered queue, blocker, range
gate, and one primary action. The projection is pure over a supplied snapshot,
with a SQLite adapter that only reads canonical readiness, speaker-review
rows, and exact-range Job identity.

The projection order is deterministic:

1. invalid or unapproved text;
2. missing speaker proposal;
3. unresolved speaker decisions;
4. Speaker Draft approval;
5. missing or invalid voice;
6. Casting Plan review;
7. eligible-range PREPARE;
8. exact-range START_RENDER;
9. exact-range monitoring or recovery;
10. pending Human QA;
11. complete.

The frontend stores the projection `task_key`. Polling refreshes business
state, but does not replace the current task DOM while that key is unchanged.
This preserves advanced disclosure, unsaved controls, focus, scroll, and audio
position in the daily workbench. PREPARE and START_RENDER remain separate
operator actions; this projection does not mutate, wake the worker, or call a
provider.

## Daily-Use V1 Operator Surface

Daily-Use V1 is implemented through five primary views:

- Production owns range readiness, blocker resolution, immutable approvals,
  PREPARE, and the separate START_RENDER boundary.
- Voice Assignment summarizes current role, voice, availability, affected
  chapter, and approval state, then returns to the contextual Production
  workspace for explicit draft/save/approve actions.
- Jobs shows pinned range/voice state, chapter and Segment progress, timestamps,
  recoverable versus permanent errors, and only backend-authorized actions.
- Audio Library provides playback, individual download, explicit Human QA with
  required rejection notes/history, and deterministic contiguous range ZIP.
- Storage provides report and dry-run by default. Confirmed cleanup is
  fail-closed and never treats canonical Artifact files as candidates.

The global status rail exposes runtime identity, schema readiness, PREPARE,
worker/render, authentication, kill-switch, and supervised restart state.
Durable restart preserves persisted production state and does not implicitly
prepare, start, retry, or render work.

## Production PREPARE Runtime

Batch PREPARE is a separate PREPARE-only operating mode. It consumes the current
read-only batch plan, requires exact range confirmation and operator
authentication, and creates only durable prepared jobs. It never offers
START_RENDER, starts the worker, wakes the worker, creates Segments/Artifacts,
or calls providers.

Production PREPARE code defaults disabled. The local production launcher may
enable it only from ignored operator configuration after schema 15, canonical
runtime identity, every positive feature gate, configured non-test
authentication, an open operator window, and an inactive kill switch all pass.
The mutation service is not constructed when any gate is closed.

START_RENDER has its own explicit render gate and remains unavailable inside
the PREPARE panel. When enabled, it transitions only the selected existing
prepared Job, then wakes the worker after the transition commits. Routine
startup does not auto-start or wake prepared work.

The production canaries are complete: a one-chapter corrected render proved
Artifact `90`, and the first normal-UI contiguous two-chapter pilot completed
Book `1`, Chapters `372-373`, on one PREPARE request and one Job `26`. Both new
outputs remain Human QA pending. Historical activation and rollback evidence is
defined in `docs/PREPARE_ACTIVATION_RUNBOOK.md`.

### Voice Eligibility Boundary

The effective voice catalog is the authoritative synthesis eligibility source
for preset voices and usable custom voice revisions. Voice identifiers are
normalized once and validated at every durable boundary:

- Voice assignment and Casting Plan approval.
- Range readiness and batch-plan fingerprinting.
- PREPARE before any Job or JobChapter transaction.
- Production PREPARE while authoritative snapshots are assembled.
- START_RENDER against the immutable prepared JobChapter voice snapshot.

A missing, malformed, unknown, inactive, or otherwise unavailable voice is a
blocking exception. The UI must preserve stale assignments for audit, identify
the affected voice, speaker/role, and chapter, require explicit replacement,
and offer only currently selectable catalog entries. It must never silently
substitute narrator or another fallback voice.

Catalog lookup failure is also blocking and retryable. PREPARE must create no
partial rows, and START_RENDER must not schedule or wake the worker, until a
fresh authoritative catalog confirms every effective pinned voice.

### Canonical Text Encoding Boundary

Every immutable Text Revision must pass the same validation before activation,
Casting Plan creation/approval, range readiness, PREPARE, START_RENDER, and
worker checkpoint reuse. Validation verifies the stored blob hash and character
count, UTF-8 round trip, permitted control characters, and strong
UTF-8-through-legacy-code-page mojibake evidence.

An invalid revision is `TEXT_BLOCKED`; it must not become eligible merely
because an older render or plan exists. Replacing rejected audio requires a new
immutable valid active revision and an approved Casting Plan bound to that exact
revision. PREPARE creates a new durable prepared Job pinned to those inputs,
while the rejected artifact and historical jobs remain unchanged. Rendering
still requires a separate explicit START_RENDER action.

## Operator Roles And Assumptions

- Primary operator: a local user producing chapters for one or more books.
- Human judgment remains final for text blockers, speaker ambiguity, voice routing, Human QA, and targeted remediation acceptance.
- Runtime is local; production data remains in the canonical Story Audio data root unless an isolated runtime is explicitly selected.
- Read-only inspection must not create provider cost, jobs, previews, artifacts, or audio.

## Information Architecture

### Home

Purpose:

- Show current production activity.
- Show resumable work.
- Show jobs requiring attention.
- Show recent completed audio.
- Provide one primary `Continue production` action.

Exclusions:

- Home must not expose all technical controls.
- Home must not become a database dashboard.

### Production

Purpose:

- Create audio through a sequential state-driven workflow.
- Support one chapter or a chapter range.
- Resume from the actual current state.
- Expose only the current valid production action.

The daily Production surface is a task-oriented workbench with five user
stages: `Chọn chương`, `Xác nhận nội dung và người nói`, `Gán và duyệt giọng`,
`Chuẩn bị và render`, and `Nghe và duyệt`. These stages are presentation only;
they do not merge or reorder backend transactions.

The workbench contains a compact range context, a chapter queue in canonical
order, one current task, and collapsed technical details. It automatically
focuses the first incomplete chapter after a read-only range check. Completing
an action refreshes authoritative state and reveals the next task, but never
performs that next mutation automatically.

Except for the two explicit Human QA verdicts, the current task exposes at
most one primary action. Voice draft save and voice approval are separate;
PREPARE and START_RENDER are separate; running work never offers another
start. Technical IDs, provenance, raw resolver values, history selection, and
regeneration controls stay under progressive disclosure.

Exclusions:

- Production must not show every technical panel at once.
- Production must not allow future steps to mutate state early.

### Voice Library

Purpose:

- Create logical custom voices.
- Upload reference audio and transcript.
- Manage immutable revisions.
- Listen to reference and preview audio.
- Select the preferred synthesis revision.
- Activate or deactivate voices.

Exclusions:

- Voice Library must not contain chapter rendering controls.
- Voice Library must not silently modify Casting Plans or jobs.

### Books And Characters

Purpose:

- Manage books.
- Manage narrator, male, female, and unknown-fallback policies.
- Manage Character Bible records and aliases.
- Assign optional character voice overrides.

Exclusions:

- Books And Characters must not contain job or render controls.
- Character work must not automatically approve Gemini assignments.

### Audio Library

Purpose:

- List completed or generated chapter audio.
- Filter by book, chapter, and QA state.
- Play audio.
- Inspect production details.
- Download the primary audio file.
- Optionally access timeline and manifest.
- Enter targeted QA/remediation when required.

Exclusions:

- Audio Library must not present the complete production wizard.
- Audio Library must not trigger new synthesis from passive browsing.

### Settings

Purpose:

- Provider configuration.
- Output paths.
- Runtime diagnostics.
- Encoder and synthesis settings.
- Technical maintenance.

Exclusions:

- Settings must not be part of the normal daily production path.
- Settings must not hide normal production progression.

## Sequential Production Steps

### Step 1 - Select Scope

- Select book.
- Select one chapter or a chapter range.
- Optionally skip already completed chapters.
- Primary action: `Check scope`.

### Step 2 - Readiness

- Perform read-only preflight.
- Show each chapter's readiness.
- Identify text, speaker, voice, casting, or existing-output conditions.
- Primary action: `Resolve required issues` or `Continue`.

Preflight must not create drafts, jobs, previews, or audio.

### Step 3 - Text Exceptions

Only when required:

- Resolve missing or unapproved text.
- Resolve structural text blockers.
- Confirm usable text.

Skip automatically when no text exception exists.

### Step 4 - Speaker Exceptions

Only show cases requiring operator judgment:

- Unknown speaker.
- New named character.
- Low confidence.
- Alias conflict.
- Ambiguous speaker.

Do not require review of narrator or safely resolved known-character rows.

### Step 5 - Voice Configuration

Only when required:

- Configure missing narrator/default/fallback voices.
- Assign a voice to an important character.
- Select an existing custom voice.
- Create a new custom voice through a contextual detour.
- Return to the exact production step afterward.

### Step 6 - Final Voice Map Review

- Summarize effective voice routing by chapter.
- Show meaningful exceptions.
- Approve Casting Plans separately.

Approval must not prepare work or start TTS.

### Step 7 - Prepare

- Show the exact selected chapters.
- Show completed chapters that will be skipped.
- Pin immutable text, casting, and voice provenance.
- Primary action: `Prepare queue`.

Prepare must not start synthesis.

### Step 8 - Start And Monitor

- Require explicit `Start render`.
- Show current chapter and segment progress.
- Show completed, waiting, paused, and failed chapters.
- Permit valid pause, resume, and stop operations.

Production configuration must not be editable inside an active render.

### Step 9 - QA And Completion

- Play chapter audio.
- Show objective QA and listening markers.
- Allow Human QA status.
- Open targeted segment regeneration when required.
- Accept or reject candidates.
- Complete the selected production scope.

## State-To-Next-Action Model

Implementation may map these conceptual states to existing database/API states without introducing unnecessary persistence.

```text
NO_SCOPE
-> SELECT_SCOPE

TEXT_BLOCKED
-> RESOLVE_TEXT

SPEAKER_EXCEPTIONS
-> REVIEW_SPEAKERS

VOICE_BLOCKED
-> CONFIGURE_VOICES

CASTING_REVIEW
-> REVIEW_FINAL_VOICE_MAP

READY_TO_PREPARE
-> PREPARE

PREPARED
-> START_RENDER

RENDERING_OR_PAUSED
-> MONITOR_OR_RESUME

RENDERED_NOT_QA
-> QA

COMPLETE
-> VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE
```

## Navigation Principles

- One primary action per screen.
- Only the current step is fully interactive.
- Future steps are locked or hidden.
- Completed steps are summarized, not expanded by default.
- The application resumes at the actual unfinished step.
- Users must not need to know Draft IDs, Plan IDs, or Job IDs.
- Backend entity structure must not dictate top-level navigation.
- Approval, preparation, and rendering remain separate actions.
- Read-only inspection must never create provider cost.
- Errors must explain what blocks progression and how to resolve it.
- `Production Flow` must not be only a heading above the old all-in-one dashboard.
- Multiple major workflow panels must not remain visible on one long screen.

## Contextual Detours

Some steps need temporary detours, such as adding a custom voice while resolving a voice blocker.

Detour requirements:

- Preserve the originating production scope and step.
- Make the detour purpose clear.
- Avoid unrelated production mutation.
- Return to the exact originating workflow state after completion or cancellation.
- Re-run only the minimal read-only readiness needed to refresh the current step.

## Current Versus Target Capabilities

| Area | Current capability | Target capability |
| --- | --- | --- |
| Backend/core production | Multi-voice pipeline, casting, prepare/start, jobs, artifacts, QA primitives exist | Preserve and reuse existing backend boundaries |
| Custom voices | Library and immutable revisions exist | Consistent custom voice assignment in all relevant operator selectors |
| Speaker/casting | Speaker review and Casting Plan primitives exist | Exception-only review inside a sequential Production workflow |
| Production UI | Current browser UI exposes too many technical areas together | Modular top-level app with Home, Production, Voice Library, Books And Characters, Audio Library, Settings |
| Range work | One chapter and some range primitives exist | Complete guided range readiness, exception queue, prepare, render, and QA closeout |
| Audio outputs | Audio artifacts and playback/download primitives exist | Dedicated Audio Library for filtering, playback, details, downloads, and remediation entry |

Target capabilities are not implemented until their roadmap milestone is completed.

## Roadmap Milestone Summary

1. `DAILY-PROD-1` - Modular Navigation And Sequential Production Shell.
2. `DAILY-PROD-2` - Custom Voice Assignment UI Closure.
3. `DAILY-PROD-3` - Audio Library And Output Retrieval.
4. `DAILY-PROD-4` - Range Readiness And Exception Queue.
5. `DAILY-PROD-5` - Batch Approval, Prepare, Render And QA Closeout.
6. `DAILY-PROD-6` - Multi-Chapter Production Acceptance.

## Anti-Drift Rules

Every future implementation task must answer:

1. Which `DAILY-PROD` milestone does this belong to?
2. Which operator pain does it remove?
3. Does it make the next valid action clearer?
4. Does it preserve approval, prepare, and start boundaries?
5. Is it reusable across daily chapter production?
6. Is the feature current behavior or target behavior?

Reject or defer work that:

- Solves only one chapter-specific editorial issue.
- Exposes another backend panel without improving operator flow.
- Adds automation before readiness and review boundaries exist.
- Introduces provider cost during read-only inspection.
- Implements a later milestone inside the active milestone.

## Daily-Production Definition Of Done

Daily production is accepted only when:

- Top-level functional areas are visibly separated.
- Production is not an all-in-one technical dashboard.
- The current production step is derived from real state.
- Only one primary action is presented.
- Future steps cannot be activated early.
- Completed steps are summarized.
- Reopening the application resumes at the correct step.
- Current backend APIs and persisted production state remain compatible.
- No provider or TTS call is needed for the shell acceptance smoke.
- Chapter 369 can be opened read-only and routes directly to its current Final Voice Map review state.
- No plan approval, job creation, or render occurs during that smoke.
