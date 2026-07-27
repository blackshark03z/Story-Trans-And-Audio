# Next Task

Task classification:
`PRODUCTION_OPERATION / TWO_CHAPTER_HUMAN_AUDIO_QA_REQUIRED`

Active milestone:
`DAILY-PROD-6 - Task Projection And Multi-Chapter Production Acceptance`

Exact next task:
`Human-listen to active Artifacts 93 and 96 for Book 1 Chapters 372-373, then record acceptance or one precise remediation target for each chapter.`

The projection-ordering correction is complete and does not authorize this
next Human Audio QA action automatically. Production must continue to use the
canonical `Việc tiếp theo` task; manual chapter inspection is read-only.

## Verified Outputs

- Production now uses a five-stage task workbench with an ordered chapter
  queue, one current task, one primary action, separate voice save/approval,
  separate PREPARE/START_RENDER, recoverable retry, and explicit QA verdicts.
  Browser journeys A-H passed without canonical mutation.
- The read-only backend task projection now owns canonical task ordering,
  range PREPARE/START_RENDER gates, exact Job monitoring/recovery, queue
  identity, and stable `task_key` polling behavior. Pure projection, affected
  API/UI, real-browser polling, the full `1734`-test offline suite, Doctor,
  canonical integrity, and supervised restart validation all pass.
- P0 frontend usability is real-browser accepted at `1366x768` and
  `1920x1080`: one Vietnamese navigation set, compact expandable diagnostics,
  direct Chapter `372`, range `372-373`, quick selection, title search, row
  selection, cross-book clearing, keyboard-only completion, refresh, and
  durable restart. The browser was returned to clean `NO_SCOPE`.
- Daily-Use V1 is real-browser accepted from a clean `NO_SCOPE` session. The
  operator can choose a canonical book and one chapter or contiguous range,
  confirm backend readiness, preserve the exact range across Voice Assignment
  and restart, and clear it without terminal or database access.
- Home, Production, Voice Assignment, Jobs, Audio Library, Storage report and
  dry-run were walked in the canonical browser. Artifact `93` playback and the
  Chapters `372-373` range ZIP download were observed; no QA or cleanup action
  was submitted.
- No Human QA choice was made for Artifacts `93/96` during UI acceptance.
  Their next decision remains intentionally human-only.
- Safe storage cleanup is complete: `103` proven-orphaned paths deleted,
  `8,068,537,580` bytes reclaimed, canonical output unchanged, two verified
  rollback backups retained, and runtime stopped with no WAL/SHM.
- Job `26`: `completed`; JobChapters `26/27`: `completed`.
- Chapter `372`: Text Revision `744`, Casting Plan `28` revision `2`,
  `53 / 53` verified Segments, retries `0`.
- Active Artifact `93`: SHA-256
  `daddd0f10a3593039a291ad929f9397083ca81e235141c0347943f224630eb31`,
  `437080 ms`, `7,079,956` bytes.
- Chapter `373`: Text Revision `746`, Casting Plan `30` revision `2`,
  `58 / 58` verified Segments, retries `0`.
- Active Artifact `96`: SHA-256
  `a72d193206eb017dc1b9ae24d39235f98e95c5cbef1483a39d009b7e6583fc2f`,
  `486790 ms`, `7,895,926` bytes.
- Both outputs passed complete decode, Audio Library playback/download/hash,
  runtime restart, persisted voice identity, and cached offline Vietnamese
  intelligibility screening.
- Human QA for Artifacts `93/96`: `pending`.

## Operator Step

- Open `Audio đã tạo` in the running application; Artifact `93` is Chapter
  `372` and Artifact `96` is Chapter `373`.
- Listen through Artifact `93`, including each `custom:25` dialogue transition.
- Listen through Artifact `96`, including preset `Ngọc Lan`, Hứa Thanh
  `custom:25`, unknown `custom:25`, and narrator `custom:26` transitions.
- Record `approved` only when the complete chapter is acceptable.
- Otherwise record `needs_fixes` with one precise audible defect and location.

## Excluded

- Do not start a larger batch before both Human QA decisions are recorded.
- Do not create another Job or rerender automatically.
- Do not modify Job `26`, Revisions `744/746`, Plans `28/30`, Chapter `369`,
  Jobs `23-25`, or Artifacts `87/90`.
