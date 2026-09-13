# Story Audio — Owner Real-Use Acceptance Contract

Status: ACTIVE PRODUCT DEFINITION OF DONE

This contract is the product acceptance authority for Story Audio. Automated tests and feature reachability are necessary engineering evidence, but they do not replace owner real-use acceptance.

## Core rule

A feature is accepted only when it appears at the correct point in one uninterrupted owner journey. A capability that exists in another screen but is not discoverable when the owner needs it is not accepted.

## UAT-01 — Select production scope

- Owner can choose a book and either one chapter or a contiguous chapter range.
- The exact book/range remains visible throughout the journey.
- Leaving for a contextual edit and returning must preserve the same production scope.

## UAT-02 — Review and correct text

- Owner can inspect the active text used for production.
- A correction creates a new immutable Text Revision and preserves prior evidence.
- Text correction itself does not call TTS or another provider unnecessarily.

## UAT-03 — Review characters

- From the active production scope, owner can reach Character management without knowing an internal route.
- Owner can inspect/add/edit character metadata and aliases and safely stop using a character when appropriate.
- Returning restores the same production scope.

## UAT-04 — Configure voices before PREPARE

Before PREPARE is offered as the consequential next action, the production journey must visibly expose a pre-render configuration review that:

- shows the effective voice map for the selected range;
- provides an obvious path to assign/reassign narrator and character voices;
- provides an obvious path to the single existing Voice Library to create/edit custom voices and revisions;
- provides an obvious path to Character management;
- reuses Book Voice Profile, Book Voice Registry, range/chapter overrides, CastingPlan and the existing contextual Voice Library detour;
- returns to the exact production scope after edits.

No second Voice Library, assignment model, casting model, or production workflow may be added.

## UAT-05 — Show effective synthesis settings

Before PREPARE, owner can see the exact effective TTS settings that will be pinned: temperature, top_k, max_chars and silence_seconds.

Current product constraint: these values come from runtime Settings and are read-only. The UI must call them fixed/effective settings, not imply that they are editable. Editable synthesis settings are not accepted until there is real persistence and authority; no fake UI-only editor is allowed.

## UAT-06 — Explicit pre-render review acknowledgement

- PREPARE cannot be triggered through the normal production UI until owner explicitly confirms that the effective voices and synthesis settings were reviewed for the current scope/input fingerprint.
- The acknowledgement is invalidated when the effective voice map, synthesis settings, or scope changes.
- Acknowledgement itself has no provider effect and does not mutate production data.

## UAT-07 — PREPARE boundary

- PREPARE creates/pins an immutable prepared Job snapshot.
- PREPARE does not invoke TTS and does not start render.
- UI shows the prepared Job identity and scope clearly.
- If the selected scope is a strict subset of an existing prepared or active Job, the UI must not offer START_RENDER for the subset and must not invent an upstream blocker. It must show the immutable owning Job scope and provide one navigation-only action to open that scope.
- Opening the owning Job scope must not wake the worker, call TTS, or start rendering; START_RENDER remains a separate explicit owner action on the exact Job scope.

## UAT-08 — Safe edit after PREPARE

If a prepared Job exists and owner wants to change voices/configuration:

- UI explains that the existing prepared snapshot is immutable;
- owner must explicitly confirm cancellation of that prepared Job before editing;
- cancellation reuses the existing guarded job cancel capability; no direct DB delete/update shortcut is allowed;
- after editing, owner must review again and PREPARE again;
- a cancelled/stale prepared snapshot must never be silently rendered.

## UAT-09 — START_RENDER boundary

- START_RENDER is a separate explicit owner action after a valid prepared snapshot.
- Only START_RENDER may wake production execution/TTS for that prepared Job.

## UAT-10 — Monitor, listen, repair, QA and download

Owner can follow a real Job through progress, listen to real output, mark needs-fixes, use the existing repair/targeted-regeneration flow, perform Human QA, and download the accepted artifact.

## UAT-11 — Journey continuity

The owner can complete the full journey without knowing internal routes, hidden technical screens, database concepts, or implementation subsystem names. Contextual detours must provide an obvious return to the active production scope.

## UAT-12 — Product completion gate

`STORY_AUDIO_PRODUCT_COMPLETE` requires all of the following on the same candidate:

1. Code/tests pass.
2. One authoritative product head exists.
3. Real runtime serves that candidate.
4. Owner can reach every required step at the correct time.
5. Owner completes at least one real chapter/range end-to-end: scope → text → characters/voices → final voice review → PREPARE → START_RENDER → listen → repair if needed → Human QA → download.

Until UAT-12 passes, the verdict remains owner-acceptance pending/blocked rather than PRODUCT_COMPLETE.

## UAT-13 — One current audio per chapter

- Each chapter has at most one current audio bundle in `Duyệt audio`.
- A newly verified render replaces the current bundle, clears the previous QA
  decision and appears as `Chờ Human QA`; it never inherits approval from an
  older output.
- After the current pointer changes, the superseded final audio, master WAV,
  timeline and segment WAV files are deleted. There is no QA-history or restore
  action for old audio.
- `Xóa mục đã chọn` and `Xóa tất cả đang hiển thị` permanently delete the exact
  selected current audio bundles after scope preview and explicit confirmation.
- Deleting or replacing audio does not delete the Book, current text, Casting
  Plan, Job record, or custom voice/revisions. It never invokes PREPARE,
  START_RENDER, TTS, Gemini, repair, or regeneration.

## Non-goals for the current blocker fix

- No new backend subsystem.
- No parallel production workflow.
- No new Voice Library or casting implementation.
- No provider-backed render during implementation verification.
- No new persistence subsystem solely to make the currently fixed TTS knobs editable.
- No cleanup/refactor unrelated to an observed owner-journey blocker.
