# DAILY-PROD Checkpoint State

Updated: 2026-07-21 20:50:39 +07:00

## Current Goal

Close out `DAILY-PROD-4A Phase 1` backend-only range readiness preflight and exception queue contract.

## Status

phase-1-backend-closeout-validated-pending-commit

## DAILY-PROD-4A Phase 1

Starting commit:
`98762152b9b98ff9dc4f53df769a6dde9bf5cb7e`

Branch:
`main`

Backend endpoint:
`GET /api/production/range-readiness`

Query contract:
- `book_id`
- `from_chapter`
- `to_chapter`

Implemented:
- Read-only helper `story_audio/range_readiness.py`.
- Read-only route in `story_audio/api.py`.
- Focused tests in `tests/test_range_readiness_api.py`.

Supported readiness states:
- `TEXT_BLOCKED` -> `RESOLVE_TEXT`.
- `SPEAKER_EXCEPTIONS` -> `REVIEW_SPEAKERS`.
- `VOICE_BLOCKED` -> `CONFIGURE_VOICES`.
- `CASTING_REVIEW` -> `REVIEW_FINAL_VOICE_MAP`.
- `READY_TO_PREPARE` -> `PREPARE`.
- `PREPARED` -> `START_RENDER`.
- `RENDERING_OR_PAUSED` -> `MONITOR_OR_RESUME`.
- `RENDERED_NOT_QA` -> `QA`.
- `COMPLETE` -> `VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE`.
- `STATE_UNRESOLVED` -> `RELOAD_READ_ONLY`.

Readiness semantics:
- One primary state and one next action per chapter.
- Active output is resolved from `chapters.active_audio_artifact_id`, not newest historical job.
- Runtime Human QA must be accepted for `COMPLETE`; pending output resolves to `RENDERED_NOT_QA`.
- Prepared/running/paused jobs take precedence over upstream reusable configuration.
- Exception queue is deterministic, chapter ordered, and excludes `COMPLETE` and `READY_TO_PREPARE`.
- Invalid active output binding fails closed and does not fall back to historical artifacts.
- Voice blocking checks missing narrator voice and empty per-utterance `resolved_voice_id` from the verified Casting Plan blob payload.

Canonical runtime:
- Restarted and verified on `http://127.0.0.1:8772`.
- Runtime root/data root matched this repository.
- `is_canonical_live_data_root`: `true`.
- `is_canonical_live_db`: `true`.
- Schema: `12`.
- Config: Gemini configured, TTS not loaded.
- Doctor: critical errors `0`; warning only for existing invalid historical speaker drafts.

Canonical smoke:
- Scope: Book `1`, chapters `364-369`.
- Chapter order: `364,365,366,367,368,369`.
- States: `364-367 RENDERED_NOT_QA`, `368 COMPLETE`, `369 CASTING_REVIEW`.
- Next actions: chapters `364-367` `QA`, chapter `368` `VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE`, chapter `369` `REVIEW_FINAL_VOICE_MAP`.
- Summary: total `6`, complete `1`, ready_to_prepare `0`, needs_attention `5`, rendered_not_qa `4`.
- Exception queue: chapters `364-367` `qa_required`, chapter `369` `casting_review`, no duplicates.
- Chapter `368` is not in the exception queue.
- Response does not expose absolute filesystem path markers.

Production mutation:
- None.
- Sensitive table counts before/after canonical smoke were unchanged for `speaker_assignment_drafts`, `casting_plans`, `jobs`, `job_chapters`, `segments`, and `artifacts`.
- Chapter `369` remained unmutated: active text revision `738`, Casting Plan `24` revision `1` draft, zero jobs.

Validation:
- `python -m py_compile story_audio\range_readiness.py story_audio\api.py`: PASS.
- `python -m unittest tests.test_range_readiness_api tests.test_active_output tests.test_human_approval_api tests.test_production_state_resolver tests.test_prepared_jobs -v`: PASS, `50` tests.
- `python -m unittest discover -s tests -v`: PASS, `1080` tests, `1` skipped.
- `git diff --check`: PASS before closeout doc updates; line-ending warnings only.

Safety:
- Backend/checkpoint only.
- No UI changes.
- No migration.
- No production database edits.
- No Speaker Draft, Casting Plan, Job, JobChapter, Segment, Artifact, Audio, QA, preview, provider, Gemini, or TTS mutation.
- No Chapter `369` production mutation.
- No push.

## Remaining

`DAILY-PROD-4A` UI integration has not started.

## Next Exact Action

1. Review the committed Phase 1 backend contract.
2. Open the existing Production range-selection UI.
3. Integrate the range-readiness response read-only.
4. Render range summary and deterministic exception queue.
5. Do not add prepare/render/batch mutation actions in the UI phase.
