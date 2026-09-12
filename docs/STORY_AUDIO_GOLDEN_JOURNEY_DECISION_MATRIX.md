# Story Audio Golden Journey Decision Matrix

Status: `TRACEABILITY_AID_V1`

This is a compact execution aid for the active Story Audio Product Goal. It
does not create a Goal, change acceptance, update CADS, or override
`AGENTS.md`, `TASK.md`, `docs/OWNER_REAL_USE_ACCEPTANCE.md`,
`docs/DECISIONS.md`, or `docs/DAILY_PRODUCTION_WORKFLOW.md`.

Grounding snapshot: worktree
`D:\Youtube\_worktrees\story-audio-product-reconciliation`, HEAD
`4ee75e153911985f743c51625dbe22c07f1ea943`. Re-ground Git, runtime, authority,
and the active owner fixture before using this matrix after later changes.

## How to read it

- `[A]` — behavior already required by upstream authority.
- `[I]` — safest interpretation of existing invariants; not new acceptance.
- `[G]` — genuinely under-specified; obtain the smallest owner decision before
  implementation if two materially different user outcomes remain valid.
- `CHECKPOINT_OK` — code/focused-test evidence only.
- `PRODUCT_ACCEPTED` — only the owner can establish this through the supported
  uninterrupted journey.

The active CUJ remains:

```text
scope -> text/speakers -> characters/voices -> casting/settings review
-> PREPARE -> explicit START_RENDER -> monitor -> listen/repair
-> Human QA -> download -> close context -> next range
```

## Required fields for every consequential action

```text
ENTRY / OWNER_SEES / ACCEPT / CHANGE / DEFER / CANCEL_OR_BACK
MUTATES / INVALIDATES / PRESERVES / FAILURE_OR_UNKNOWN
NEXT_STATE / RETURN_SURFACE / PROHIBITED / EVIDENCE
```

If a field cannot be derived from upstream authority, mark it `[G]`; do not
silently decide it in UI code.

## Global behavior invariants

1. `[A]` Show success only after reconciling the authoritative postcondition.
2. `[A]` On timeout or lost response, read authoritative state or reuse the
   same idempotency identity before retry; never duplicate work.
3. `[A]` Polling and same-task refresh preserve scroll, focus, disclosure,
   playback position, and unsent choices while the authoritative task is
   unchanged.
4. `[A]` Back/navigation is not a mutation. Cancel/stop is a separate explicit
   action with visible scope and effect.
5. `[A]` Stale/concurrent writes fail closed and do not persist a partial batch
   or overwrite newer authority.
6. `[A]` Completing a step refreshes state and reveals the next action; it never
   performs that next mutation automatically.
7. `[A]` Text Revisions, Speaker Drafts, Casting Plans, Jobs/snapshots, QA, and
   Artifacts remain immutable history; corrections create supported new state.
8. `[A]` PREPARE and START_RENDER remain separate. Inspection, navigation,
   configuration, documentation, and polling call neither.
9. `[A]` Requested scope and effective included/excluded scope are distinct and
   visible. `skip_completed` cannot hide unresolved work in included chapters.
10. `[A]` Focused tests prove function/transition behavior only, not the whole
    owner journey.

## Invalidation and preservation

All invalidation below affects future eligibility. It never rewrites an already
pinned or completed historical object.

| Change | Re-evaluate or invalidate | Preserve |
| --- | --- | --- |
| Book/range or `skip_completed` | effective scope, readiness, projection, preflight acknowledgement/fingerprint | chapter data and all historical objects |
| Active Text Revision | speaker compatibility, casting eligibility, preflight acknowledgement | old revisions/drafts/plans/jobs/artifacts/QA |
| Speaker identity/mapping | affected voice map, casting eligibility, preflight acknowledgement | text, unrelated decisions, all historical objects |
| Alias/display metadata only | matching/display; casting only if effective identity changes | text, unaffected mapping, pinned snapshots |
| Character gender/voice override | affected voice resolution, casting eligibility, acknowledgement | identity, text, speaker decisions, history |
| Book default/fallback voice | every future inherited mapping, affected casting, acknowledgement | explicit overrides and pinned snapshots |
| Chapter/range voice override | affected chapter mappings/casting/acknowledgement | other chapters and history |
| Preferred custom-voice revision | catalog/future resolution before pinning | all immutable voice revisions and pinned snapshots |
| Casting approval | range readiness and preflight | text, speakers, prior plans/jobs/artifacts |
| Effective synthesis settings | acknowledgement and not-yet-prepared review | existing Job snapshots |
| QA needs-fixes | repair/replacement eligibility and current QA decision | current audio until a verified replacement activates; prior Job/text/casting/custom voice |
| Verified replacement activation | current output and QA return to pending | Job/text/casting/custom voice; superseded audio bundle and its QA decision are permanently removed |

Any dependency change after acknowledgement but before PREPARE requires fresh
review. An existing Job that pins the old dependency is never edited in place.

## Decision gates

### 1. Select scope

- **Entry/see `[A]`:** Book, requested range, `skip_completed`, included and
  excluded chapters with reasons, including an empty effective scope.
- **Accept `[A]`:** save only resumable working context, run read-only readiness,
  and reveal the first authoritative task.
- **Change/defer/cancel `[A]`:** change scope before consequential work, or leave
  without creating drafts/plans/Jobs/previews/audio; Back changes no production
  object.
- **Effects:** scope change invalidates old readiness/acknowledgement; durable
  input and operational records plus each chapter's current audio/QA remain.
  Deleted superseded audio is never restored by a scope change.
- **Failure/next `[A]`:** invalid or empty effective scope stays recoverable and
  offers scope change or existing outputs, never zero-chapter PREPARE.

### 2. Inspect or change text

- **Entry/see `[A]`:** exact chapter, active revision, validation blockers, and
  downstream future-work impact.
- **Accept `[A]`:** confirm usable current text without provider or Job work.
- **Change `[A]`:** create a new immutable Text Revision; never edit old text or
  a pinned Job snapshot in place.
- **Defer/cancel `[I]`:** remain text-blocked; preserve a local draft when safe,
  and require explicit discard when navigation would lose it.
- **Effects `[A]`:** invalidate speaker/casting compatibility and preflight
  acknowledgement; preserve immutable text revisions, plans, Jobs, each
  chapter's current audio/QA, and other chapters. Superseded audio/QA is not a
  retained history surface.
- **Failure/next `[A]`:** failed save keeps the prior active revision; timeout
  reloads active revision before retry; then return to speaker review or the
  first state proven compatible.

### 3. Review speaker identity

- **Entry/see `[A]`:** exact utterance/context, proposal, alternatives,
  reason/confidence, and chapter/range remaining counts.
- **Accept `[A]`:** persist the exact owner decision, refresh authoritative
  counts, and move to the next exception or gate.
- **Change `[A]`:** narrator, unknown, existing/new character, background group,
  aliases, uncertainty, or a traceable replacement of an approved decision.
- **Defer/cancel `[A]`:** keep the item pending/deferred; Back approves nothing
  and preserves scope plus unsent selection.
- **Effects `[A]`:** invalidate affected future voice map/casting/acknowledgement;
  preserve text, unrelated decisions, drafts/plans/Jobs, and each chapter's
  current audio/QA.
- **Failure/next `[A]`:** stale/concurrent mapping fails atomically; timeout
  reconciles row decision and remaining count. When current state is approved
  and `remaining_review_count=0`, open voice configuration even if historical
  `unresolved_count` is nonzero.
- **Prohibited `[A]`:** implicit Gemini retry/approval, voice assignment,
  PREPARE, START_RENDER, worker wake, or audio mutation.

### 4. Configure effective voices

- **Entry/see `[A]`:** speaker review current; show narrator and every effective
  speaking role in included scope, voice/source/chapters/dialogue count and
  availability. When an approved speaker decision carries an explicit Gemini
  voice proposal, show current versus proposed voice here, never in speaker
  identity review. Book-wide characters are a different concept.
- **Accept `[A]`:** apply all eligible or selected Gemini proposals atomically
  to the effective included chapters, keep a valid current voice explicitly,
  or save a supported Book, character, chapter, or range assignment.
- **Change `[A]`:** choose another usable voice or use the contextual Voice
  Library detour; detour return is unsaved until the normal Save action. A
  rejected Gemini proposal is durably marked `DISMISSED` and does not reappear
  as pending unless a newer proposal supersedes it.
- **Defer/cancel `[A]`:** optional work may remain; required missing/unavailable
  voice blocks. Cancel discards only unsaved choice and returns to exact scope.
- **Effects `[A]`:** invalidate affected future casting/acknowledgement; preserve
  text, speaker identity, unrelated overrides, custom voices, and each chapter's
  current audio/QA until a verified replacement becomes current.
- **Failure/next `[A]`:** missing/inactive voice, catalog failure, stale save, or
  conflicting proposals for one role fail closed and never substitute narrator.
  Batch scope excludes completed chapters when `skip_completed` is active;
  failure rolls back the submitted set. Then move to the next voice exception
  or Final Voice Map review.

### 5. Review and approve Final Voice Map

- **Entry/see `[A]`:** current text/speakers, usable voices, exact chapters and
  plan revisions, effective map/source/line counts, and replacement warnings.
- **Accept `[A]`:** explicitly approve only the displayed current plan set.
- **Change/defer/cancel `[A]`:** return to speaker/voice work or leave plans
  draft; Back approves and prepares nothing.
- **Effects `[A]`:** invalidate acknowledgement tied to an older plan; preserve
  text, speaker evidence, prior plans/Jobs, and each chapter's current audio/QA.
- **Failure/next `[A]`:** stale dependency, unavailable voice, set mismatch, or
  timeout fails atomically and reconciles before retry; success leads to
  read-only preflight, never implicit PREPARE.

### 6. Review preflight and PREPARE

- **Entry/see `[A]`:** fresh exact-scope preflight: included/excluded chapters,
  fingerprints, text/speaker/casting/voices/settings, auth/runtime/schema,
  kill-switch/conflicts, estimate, and PREPARE-only effect.
- **Accept `[A]`:** after explicit acknowledgement, create/reuse the exact
  eligible durable prepared Job atomically.
- **Change/defer/cancel `[A]`:** return to the owning input gate, leave PREPARE
  resumable, or close confirmation with no mutation.
- **Effects `[A]`:** PREPARE may create Job/JobChapter snapshots only; it
  preserves input and operational records plus current audio/QA, and creates no
  Segment/Artifact.
- **Failure/next `[A]`:** timeout reads exact-range Job/fingerprint before retry;
  failure creates no partial rows and never wakes the worker. Success shows the
  prepared Job and separate START_RENDER action.

### 7. Review prepared Job and START_RENDER

- **Entry/see `[A]`:** exact prepared Job, owning scope, pinned
  text/voices/settings, and separate Start versus guarded-cancel paths.
- **Accept `[A]`:** explicit START_RENDER transitions only that Job and wakes the
  worker only after the transition commits.
- **Change `[A]`:** cancel the prepared Job explicitly, then edit through the
  owning gate, review again, and PREPARE again; never edit the snapshot.
- **Defer/cancel `[A]`:** leaving keeps the Job prepared; declining Start or
  cancellation keeps it prepared and returns to the same review.
- **Effects `[A]`:** confirmed cancellation removes render eligibility but
  preserves the cancelled snapshot/audit and all other history.
- **Failure/next `[A]`:** reconcile Job state before repeating Start/cancel. A
  subset owned by a larger Job navigates to that scope and cannot start a new
  subset Job.

### 8. Monitor, pause, resume, stop, or request a future change

- **Entry/see `[A]`:** exact queued/running/paused/recoverable-failed Job,
  chapter/Segment progress, and only backend-authorized actions.
- **Accept/change `[A]`:** monitor or explicitly pause/resume/retry/stop. Active
  configuration is not editable; changed inputs enter a later replacement/new
  journey after an allowed terminal stop or completed render.
- **Defer/cancel `[A]`:** leaving the page is not stop; returning discovers
  authoritative state. Stop is separately confirmed.
- **Effects `[A]`:** preserve pinned snapshots, verified reusable checkpoints,
  attempts, Jobs, Artifacts, and audit according to existing recovery rules.
- **Failure/next `[A]`:** lost responses reconcile Job/checkpoint state; do not
  auto-retry/resume or revive a terminal cancelled Job. Continue monitor,
  authorized recovery, QA, or a new correction journey.
- **Choice `[I]`:** when the owner wants different input mid-render, expose both
  safe existing choices when supported—let current immutable Job finish, or
  explicitly stop it—without inventing in-place edit semantics.

### 9. Listen and make Human QA decision

- **Entry/see `[A]`:** exact current verified Artifact/Job/chapter, playable output,
  objective/listening evidence, current QA decision, and accept versus needs-fixes effect.
- **Accept `[A]`:** record Human QA acceptance for the exact observed Artifact
  and expose current-output/download actions.
- **Change `[A]`:** needs-fixes with evidence and a cause: text, speaker, voice,
  synthesis/pacing, target Segment, or whole chapter.
- **Defer/cancel `[A]`:** stay pending QA; leaving records no verdict and changes
  no active output.
- **Effects `[A]`:** replace only the current QA decision/status; preserve the
  current file, Job, plan, text, other chapters, and accepted outputs. Earlier
  QA decisions are not retained as product history.
- **Failure/next `[A]`:** stale Artifact/file or timeout requires reload; never
  apply a verdict to a different Artifact. Then download, remain pending, or
  enter repair.

### 10. Review, revise, and execute repair

- **Entry/see `[A]`:** exact needs-fixes Artifact and QA evidence, cause/scope,
  proposed repair, affected inputs/Segments, and earliest owning gate.
- **Accept `[A]`:** explicitly confirm repair plan/draft, resolve input blockers,
  PREPARE_REPLACEMENT, then separately START_RENDER replacement.
- **Change/defer/cancel `[A]`:** revise markers/note/scope or return to the
  owning text/speaker/voice gate; leaving starts no replacement/provider work.
- **Effects `[A]`:** create repair/input/Job/Artifact state only through existing
  commands and invalidate only future eligibility dependent on changed inputs.
  Until a replacement is verified, keep the current Artifact and its current QA
  decision unchanged. After verified activation, the replacement becomes the
  only current audio, its QA returns to pending, and the superseded audio bundle
  and QA history are permanently removed. Job, text, casting, and custom-voice
  records remain available for operations and reuse.
- **Failure/next `[A]`:** a failed/rejected candidate leaves the prior current
  output unchanged; reconcile the exact plan/Job/Segment/attempt/Artifact before
  retry. Then continue repair, compare a valid candidate, or return to QA.
- **Prohibited `[A]`:** silent reuse-to-regenerate fallback, auto-accept,
  restoring superseded audio, or implicit PREPARE/START_RENDER.
- **Machine-assisted technical candidate `[A]`:** a machine finding may create
  one offline candidate only when it is bound to the exact current Artifact and
  Segment and the remediation has a deterministic controllable effect. In v1,
  this is limited to excessive boundary silence and loudness mismatch. Candidate
  creation changes no current audio or Human QA. The owner listens A/B and
  explicitly uses or discards it; discard deletes the candidate, while use
  reassembles one new current bundle, returns Human QA to pending, re-runs the
  machine check, and removes superseded audio/attempt history.
- **Unsupported machine finding `[A]`:** pacing without a real rate control,
  clipping, spoken-content, voice-match, and naturalness may populate the
  existing Human QA repair evidence, but must not silently rerender the same
  snapshot or claim an improvement.

### 11. Download, close the cycle, and start the next range

- **Entry/see `[A]`:** exact accepted Artifact identities, per-chapter QA state,
  eligible contiguous ZIP scope, unresolved chapters, and context to be cleared.
- **Accept `[A]`:** download is read-only; close clears only ephemeral working
  context; next range opens editable scope selection with a suggestion only.
- **Change/defer/cancel `[A]`:** choose individual accepted output or eligible
  contiguous accepted range; leave accepted and unfinished resources intact;
  cancelling download/close changes no QA/output/Job.
- **Effects `[A]`:** preserve the current audio and its current QA decision,
  every durable text revision, casting plan, Job, reusable Book/character voice
  setting, custom voice, and unfinished task. Superseded audio/QA history is not
  retained.
- **Failure/next `[I]`:** missing file/hash, stale pointer, interrupted download,
  or ZIP failure remains read-only and does not revoke QA/COMPLETE; reload exact
  Artifact identity before retry.
- **Mixed range `[I]`:** accepted chapters remain individually available;
  pending/needs-fixes chapters retain their task. The UI must not call the whole
  requested range complete while an included chapter remains unresolved.
- **Prohibited `[A]`:** regeneration as download fallback, restoring superseded
  audio, unaccepted ZIP content, or leaking prior Job/repair/selection into the
  next cycle.

## Cross-case coverage that must not be omitted

| Case | Required outcome | Source status |
| --- | --- | --- |
| Unsaved edit + Back/refresh/poll | preserve or explicitly discard; no silent loss | `[A]` |
| Contextual detour complete/cancel | return to exact scope/step; no unrelated mutation | `[A]` |
| Timeout after Save/PREPARE/Start/QA | reconcile postcondition; no duplicate dispatch | `[A]` |
| Two tabs or concurrent writer | stale command fails closed; local choice is not auto-merged | `[A]` |
| Restart while prepared/running/paused | discover persisted state; no implicit work | `[A]` |
| Empty effective scope | outputs or scope change; no PREPARE | `[I]` |
| Narrator-only/zero speaker targets | `NO_REVIEW_REQUIRED`; no fabricated count | `[I]`, backed by state model |
| Book character with no line in scope | not counted as an effective speaking role | `[I]`; speaker-coverage oracle deferred |
| Voice disappears after selection | block at fresh boundary; preserve stale assignment; replace explicitly | `[A]` |
| Mixed chapter states | show requested/effective scope and one canonical task; no false range-ready/complete claim | `[A]` plus `[I]` for close wording |
| Wants edit during render | no in-place edit; finish or explicit supported stop, then new journey | `[A]` plus `[I]` for presenting both choices |
| Failed/cancelled Job | only authorized resume/retry; terminal cancel not silently revived | `[A]` |
| Reject repair candidate | keep current active audio unchanged; explicit next repair decision | `[A]` |
| Create offline machine repair candidate | exact Artifact/Segment identity; current audio and Human QA unchanged; before/after evidence shown | `[A]` |
| Reload with unresolved machine candidate | restore the exact A/B candidate; do not create a duplicate or lose the decision point | `[A]` |
| Machine finding has no controllable repair | disclose unsupported; route to Human QA evidence; no candidate/provider call | `[A]` |
| Accept offline machine repair candidate | change only the bound Segment, rebuild one current bundle, reset Human QA, rescore, remove superseded candidate/audio history | `[A]` |
| Activate a verified replacement | replace the current audio, return QA to pending, and permanently remove the superseded audio bundle | `[A]` UAT-13 |
| Download/ZIP failure | local read-only failure; QA and production state unchanged | `[I]` |
| Close/start next cycle | clear ephemeral context only; no Job/range leakage | `[A]` |

## Evidence map and known gap

| Surface | Existing evidence | Verdict |
| --- | --- | --- |
| Scope/projection/next action | resolver, projection, scope/workflow browser tests | `CHECKPOINT_OK`; canonical connected replay still required |
| Text invalidation | revision/readiness/prepared-job tests | `IMPLEMENTED_NOT_JOURNEY_PROVEN` |
| Speaker review | domain/API/browser suites; completed-review regression | focused `CHECKPOINT_OK`; semantic speaker-coverage oracle deferred |
| Voice/detour/casting | catalog, override, detour, casting suites | `IMPLEMENTED_NOT_JOURNEY_PROVEN` |
| PREPARE/START separation | preflight, prepared-job, command, activation suites | functionally covered; owner journey still required |
| Monitor/recovery | Job/chapter/Segment recovery suites | functionally covered; change-intent composition needs journey evidence |
| QA/repair/restore | approval, repair, restore API/browser suites | focused coverage; connected replacement loop still required |
| Download/next cycle | Audio Library and prior browser evidence | checkpoint evidence; replay after future fixes |
| Full uninterrupted CUJ | active `TASK.md` fixture | `UNVERIFIED` until owner completion on current candidate |

The known speaker-coverage gap is intentionally recorded, not fixed here: the
golden fixture still needs a human-authored oracle proving every dialogue span
survives analysis, review, voice configuration, casting, and preflight. This
does not authorize provider calls or production-data mutation.

## CADS loop for subsequent defects

1. Re-ground authority, Git/runtime identity, fixture, and dirty work.
2. Bind the observed defect to one gate and its expected/preserved state.
3. If `[A]` is clear, classify `DEFINED_BUT_VIOLATED` and debug the first real
   CUJ blocker only.
4. If a material product choice remains `[G]`, present its concrete owner
   consequences and obtain the smallest decision; do not invent acceptance.
5. Implement the smallest coherent `REUSE -> WIRE -> FIX ->
   REPLACE_AND_DELETE -> ADD` change in one writer worktree.
6. Run focused transition checks and inspect the rendered surface when visible.
7. Immediately resume the same CUJ/fixture. Never compose subsystem PASS into
   Journey PASS or call it `PRODUCT_ACCEPTED` without the owner.

## V1 completion

- [x] Existing Goal/CUJ and authority remain unchanged.
- [x] Every consequential gate includes agree, change, defer, cancel/back,
  failure/unknown, invalidation, preservation, and next-state behavior.
- [x] Unsaved, stale/concurrent, timeout/idempotency, restart, partial/mixed,
  empty, narrator-only, unavailable-resource, prepared/running, repair, restore,
  download, close, and next-cycle cases are represented.
- [x] Authority, inference, implementation evidence, and owner acceptance are
  kept distinct.
- [x] No provider, PREPARE, START_RENDER, Human QA, production mutation, CADS
  update, or acceptance change is authorized by this document.

V1 is complete as a compact traceability aid. Any future `[I]` that becomes a
material product choice must be promoted to `[G]` and resolved through existing
Goal/decision authority before implementation.
