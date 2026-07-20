# Next Task

Current Status:
Task 18BD-S2 implemented the custom voice preview provenance guard. Legacy custom preview cache entries without immutable `custom_voice_id` provenance are quarantined and no longer served as valid listening evidence. Chapter `369` Casting Plan `24` remains draft/unapproved, and no jobs, artifacts, provider calls, TTS calls, or preview regenerations were created.

Current Baseline:
- Branch `main`
- Verify current `HEAD` with `git log -1` before starting the next task
- Canonical production runtime: `http://127.0.0.1:8772` -> `D:\Youtube\Story Trans And Audio\data`
- YouTube Auto must remain untouched on `http://127.0.0.1:8765`
- Protected untracked paths must remain untouched:
  - `experiment_b_transcript/`
  - `runs/`
- Completed chapters: `364` artifact `69`, `365` artifact `72`, `366` artifact `78`, `367` artifact `75`, and `368` artifact `84` are all documented as `HUMAN_QA_PASS`.
- Chapter `369`: active Text Revision `738`, Speaker Assignment Draft `15`, Casting Plan `24` revision `1` draft/unapproved, no Jobs, no JobChapters, no production segments, no production attempts, no artifacts, no active audio, deterministic utterances `46`, speaker targets/review rows `2`; previous quote-boundary blocker is resolved.
- Draft `15`: status `approved`, `approved_at = 2026-07-19T14:14:46.641036+00:00`, row reviews `2`, unreviewed rows `0`, invalid rows `0`.
- Casting Plan `24`: the only Chapter `369` plan, `status = draft`, `approved_at = null`, narrator `custom:26`; two unknown Hải Thi Tộc leader rows still require a trustworthy non-narrator synthesis voice before plan mutation.
- Preview provenance guard:
  - Custom preview identity/manifests must include `custom_voice_id`, custom voice revision ID, reference asset SHA, preview text identity, and synthesis settings identity.
  - Legacy custom previews without `custom_voice_id` are treated as incomplete provenance and return `404` from the preview file route.
  - custom:25 legacy preview `98716703b9e713e6801611868cdcf57fd1ce1892c2a7edfcb425fc06bb937b33` is quarantined; its reference audio remains available at `/api/custom-voice-revisions/1/audio`.
  - custom:27 legacy preview `1a1bdb6a57565d3e5141609eeedca9855d308b8d3935de8737145595fd5542b1` is also quarantined; its reference audio remains available at `/api/custom-voice-revisions/5/audio`.
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
Task 18BD-S4 - Repair preview provenance and obtain a trustworthy voice candidate before modifying Casting Plan 24.

Important:
Task 18BD-S4 must not mutate Casting Plan `24` until a trustworthy candidate voice is available. Do not treat the quarantined custom:25/custom:27 legacy previews as valid listening evidence; use reference audio or newly authorized bounded previews only through supported workflow.
