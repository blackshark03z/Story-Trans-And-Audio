# Worker Packet

Generated: 2026-08-09T08:27:54+00:00
Capsule Revision: 14

## Task

- ID: STORY_AUDIO_PRODUCT_GOAL_R3-BOOK_SCOPED_CUSTOM_VOICE/r001
- Status: ACTIVE
- Goal: STORY_AUDIO_PRODUCT_GOAL_R3 / node BOOK_SCOPED_CUSTOM_VOICE
- Milestone / criterion: M-001 / A normal user can add a sample-backed custom voice to one Book, it persists on reload, resolves in that Book runtime context, and cannot be seen or resolved by another Book.
- Risk / profile: R3 / DEEP
- Negative path required: yes
- Shipping breaker: INACTIVE (0/3 non-shipping)

## Outcome

ADD CUSTOM VOICE TO SELECTED BOOK

## Goal Context

Story Audio enables a local operator to create, review, repair, accept, and download trustworthy audiobook-style chapter audio from multiple EPUB books with book-scoped characters, casting, and voices.

## Scout Handoff

NONE

## Scope

- Modify: story_audio/custom_voice.py,story_audio/custom_voice_api.py,story_audio/api.py,story_audio/voice_eligibility.py,story_audio/voice_ref.py,story_audio/pipeline.py,story_audio/migrations/__init__.py,ui/index.html,ui/app.js,tests/**,story_audio/backup.py,story_audio/integrity.py,story_audio/batch_prepare_clone_api.py,story_audio/batch_prepare_isolated_adapter.py
- Create: story_audio/migrations/0016_book_scoped_custom_voices.sql,tests/test_book_scoped_custom_voices.py,scripts/browser_book_custom_voice_acceptance.mjs
- External calls: NONE
- Pre-existing dirty files: 0 (not part of task unless changed again)
- Current task delta: scripts/browser_book_custom_voice_acceptance.mjs, story_audio/api.py, story_audio/custom_voice.py, story_audio/custom_voice_api.py, story_audio/migrations/0016_book_scoped_custom_voices.sql, story_audio/migrations/__init__.py, story_audio/pipeline.py, story_audio/voice_ref.py, tests/test_backup_restore.py, tests/test_batch_prepare_clone_migration.py, tests/test_batch_prepare_clone_rehearsal.py, tests/test_batch_prepare_execution_attempt_migration.py, tests/test_batch_prepare_isolated_integration.py, tests/test_batch_prepare_job_link_migration.py, tests/test_batch_prepare_migration.py, tests/test_batch_prepare_persistence_contract.py, tests/test_batch_prepare_runtime_integration.py, tests/test_book_scoped_custom_voices.py, tests/test_custom_voice.py, tests/test_custom_voice_library_ui.py, tests/test_gemini_cache.py, tests/test_migrations.py, tests/test_prepare_production_activation.py, tests/test_range_input_api.py, tests/test_range_readiness_api.py, tests/test_speaker_assignment.py, tests/test_speaker_review_api.py, ui/app.js, ui/index.html

## Acceptance

- [ ] Browser Book A: add a named sample-backed voice, save, and see it after reload.
- [ ] Book B excludes the Book A voice in UI/API/runtime resolution while legacy NULL voices remain compatible.
- [ ] PipelineWorker cannot reuse Book A custom-voice context for Book B or reverse order.
- [ ] Browser acceptance fails closed before mutation for canonical runtime or missing isolation marker.
- [ ] No provider/render/QA action and canonical Jobs, JobChapters, Artifacts, casting, and Chapter 369 remain unchanged.

## Verify

1. Cheapest focused check.
2. Critical negative path.
3. Affected runtime/integration check.
4. Rollback rehearsal/proof that leaves final state intact.
- Acceptance contract: 51ceff3bb4cd32181c629ce84d4eb5d2eeeef5fb85dc3724962f2eda77493f3e (predeclared commands=1, locked probes=0)
- Review policy: required

## Stop

- Stop/change strategy after two failed attempts without new evidence.
- Amend scope instead of widening it silently.
- Final output and task delta must be inspected before acceptance.
- If shipping breaker is ACTIVE, do not start/continue non-shipping work without an explicit override.

## Shared/Operational Context

- Product goal: The operator completes the frozen North Star journey from EPUB import through accepted downloadable chapter audio, with explicit control over AI proposals.
- Data operation: CREATE_NEW_VERSION
- Artifact operation: CREATE_NEW_VERSION
- Rollback: revert task-scoped diff and remove new artifacts

## Relevant Decisions

- NONE_LISTED

## Critical Gates

- Owner authorization: APPROVED / OWNER AUTHORIZATION — RECOVER BUILD OS GOVERNANCE DEADLOCK AND COMPLETE BOOK-SCOPED VOICE, 2026-08-09
- Human review required: yes
- Full suite required: yes
- Specialist trigger: security/data/operations
