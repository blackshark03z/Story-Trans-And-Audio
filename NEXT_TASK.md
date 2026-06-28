# Next Task

Current Sprint:
Custom Reference Voice Usability Completion

Current Task:
Custom Reference Voice Library UI

Status:
Planned — API contract audit complete, implementation pending

Previous Task Summary:
Custom Voice Preview completed in commit 02a76135dad5b1b4fa6a42552791a2d9cd718049 with 450 offline tests. Immutable revision preview with reference audio/transcript integrity, content-addressed cache, backward-compatible API, and minimal UI panel.

Next Steps:
Implement Global Custom Reference Voice Library UI:
- Phase 5B1: Logical Voice Library UI (list, create, select, deactivate/reactivate, safe errors, API integration)
- Phase 5B2: Immutable Revision Upload and History (file picker, transcript input, multipart upload, no edit/overwrite)
- Phase 5B3: Preview Integration and Offline Tests (exact revision ID, UI contract tests, API regressions)
- Phase 5B4: Real Smoke and Closure (real VieNeu preview, immutability verification, full suite, Doctor)

Do Not Work On:
- Modifying an immutable revision or overwriting reference audio
- Hard delete of logical voices or revisions
- Automatic transcript generation or model training
- Voice cloning, emotion control, or importing voices from VieNeu presets
- Automatic casting changes or automatic character creation
- Job or chapter rendering (preview only)
- Arbitrary preview text (fixed preview text only)
