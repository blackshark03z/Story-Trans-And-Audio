# Next Task

Current Status:
Task 18AH inspected the next sequential production candidates and selected Chapter `368` as the first eligible chapter for a new canonical production workflow. The task was inspection-only and made zero production mutations.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters that must not be mutated by the next draft task:
  - Chapter `364`: `HUMAN_QA_PASS`, active artifact `69`
  - Chapter `365`: `HUMAN_QA_PASS`, active artifact `72`
  - Chapter `366`: `HUMAN_QA_PASS`, active artifact `78`
  - Chapter `367`: `HUMAN_QA_PASS`, active artifact `75`
- Selected chapter: Chapter `368`, ID `368`, title `Chương 368`
- Chapter `368` active approved Text Revision: `736`, parent/source Revision `735`, `kind = reflowed`, processor `lossless-reflow-v1`, content SHA-256 `c1e5c935f2df6e411086f87a6ff6c3b03795fe2005382a13cdde1c3376421564`, lexical SHA-256 `f5942c8d31af105fc39c7f0d03c9839d3f534559ee3cd6de56275fb90d230514`, char count `7831`
- Chapter `368` text readiness: content exists and hash-matches; deterministic utterances `49`; sequence range `1-49`; quote spans `0`; speaker targets `0`; empty utterances `0`; punctuation-only utterances `0`; malformed quote targets `0`; offset gaps `0`; offset overlaps `0`; duplicate sequence count `0`; duplicate stable utterance ID count `0`
- Chapter `368` existing workflow state: speaker drafts `0`, Casting Plans `0`, jobs `0`, JobChapters `0`, segments `0`, artifacts `0`, active audio `none`, audio status `not_created`
- Voice strategy remains narrator `custom:26`, male dialogue `custom:25`, female dialogue `custom:26`, unknown fallback narrator/custom `custom:26`; custom voices `25` and `26` remain active and structurally usable
- Inspected later chapters: Chapter `369` and Chapter `370` have future text-remediation blockers; Chapter `371` and Chapter `372` also looked eligible, but the sequential selection rule chooses Chapter `368` first

Next Recommended Task:
Task 18AI - Generate One Speaker-Assignment Draft for Chapter 368.

Why:
- Chapter `368` is the first sequential chapter after completed Chapters `364-367` that is clean, unstarted, and eligible for the supported production workflow.
- There is no existing Chapter `368` speaker draft, Casting Plan, job, segment, artifact, or active audio to resume.
- The correct next mutation is exactly one speaker-assignment draft, not a Casting Plan, job preparation, render, or text correction.

Scope:
1. Re-verify canonical runtime and repository baseline.
2. Re-verify Chapter `368` still has active approved Text Revision `736` and no existing workflow state.
3. Generate exactly one speaker-assignment draft for Chapter `368` through the supported route.
4. Stop after the draft is created and documented.

Prerequisites For Any Next Task:
- Verify `GET /api/runtime` points to canonical production before any mutation.
- Use the authoritative VieNeu interpreter: `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`.
- Keep `STORY_AUDIO_ALLOW_LIVE_DB=1` process-local only.
- Do not touch port `8765`.
- Do not mutate `experiment_b_transcript/` or `runs/`.
- Do not modify Chapters `364`, `365`, `366`, or `367`.
- Do not skip Chapter `368` in favor of later eligible chapters.
- Do not create a Casting Plan, approve a plan, prepare/start a job, preview TTS, synthesize, render, or edit audio during Task `18AI`.
- Re-verify Git baseline before implementation.
