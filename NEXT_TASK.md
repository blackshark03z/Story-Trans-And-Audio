# Next Task

Current Status:
Task 18BB implemented the separated Speaker Draft review boundary. Row-level review decisions can now be saved independently, and Speaker Draft approval can now happen without creating a Casting Plan. Draft `15` for Chapter `369` remains generated, non-stale, unreviewed, and unchanged.

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
- New supported review workflow:
  - Save each row through `PUT /api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/reviews/{target_id}`.
  - Approve only the Speaker Draft through `POST /api/chapters/{chapter_id}/speaker-assignment/drafts/{draft_id}/approve-only`.
  - Create the Final Voice Map / Casting Plan as a separate downstream action after draft approval.
- Draft `15` review rows:
  - `u0003-b1d3d00d55ab` / seq `3`, suggested `unknown`.
  - `u0021-49989b447284` / seq `21`, suggested `unknown`; exact text `"Pháp lực màu đỏ! Nhanh phá huỷ trận pháp!"`.
- Chapter `370`: active Text Revision `740`, previously classified `BLOCKED_TEXT_REMEDIATION` for multiple split quote fragments including a punctuation-only quote segment; do not skip Chapter `369`.

Next Recommended Task:
Task 18BC - Human Review and Draft-Only Approval of Chapter 369 Speaker Draft 15.
