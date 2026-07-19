# Next Task

Current Status:
Task 18BC completed human row review and draft-only approval for Chapter `369` Speaker Assignment Draft `15`. Both target rows were reviewed as `unknown`, and Draft `15` is now approved without creating a Casting Plan or any downstream audio-production object.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are all documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15`, no Casting Plans, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, deterministic utterances `46`, speaker targets/review rows `2`; previous quote-boundary blocker is resolved.
- Draft `15`: status `approved`, `approved_at = 2026-07-19T14:14:46.641036+00:00`, row reviews `2`, unreviewed rows `0`, invalid rows `0`.
- New supported review workflow:
  - Save each row through `PUT /api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/reviews/{target_id}`.
  - Approve only the Speaker Draft through `POST /api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/approve-only`.
  - Create the Final Voice Map / Casting Plan as a separate downstream action after draft approval.
- Draft `15` review rows:
  - `u0003-b1d3d00d55ab` / seq `3`, human-reviewed as `unknown`.
  - `u0021-49989b447284` / seq `21`, human-reviewed as `unknown`; exact text `"Pháp lực màu đỏ! Nhanh phá huỷ trận pháp!"`.
- Task 18BC backup evidence: `D:\Youtube\Story Trans And Audio\backups\task18bc_pre_ch369_draft15_approve_20260719_211339`; backup DB SHA-256 `01a1875198270e8335ff422b7be9c599167dc6d1bc5d5852b0f8d8181cfd8965`; backup DB size `4009984` bytes.
- Chapter `370`: active Text Revision `740`, previously classified `BLOCKED_TEXT_REMEDIATION` for multiple split quote fragments including a punctuation-only quote segment; do not skip Chapter `369`.

Next Recommended Task:
Task 18BD - Create and Review Chapter 369 Final Voice Map Draft.

Important:
Task 18BD must create the Final Voice Map / Casting Plan as a separate downstream action from the already approved Speaker Draft. It must not start TTS or create a render job.
