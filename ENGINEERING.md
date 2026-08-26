# Engineering Contract

## Code and dependency expectations

Story Audio is a modular FastAPI and SQLite application. Keep the existing local dependency footprint and preserve the boundary between Story Audio and YouTube Auto. Add a runtime dependency only when its concrete capability, alternatives, and removal cost are documented.

## Testing and executable quality gates

The policy's `offline-test-*` gates collectively run every `tests/test_*.py` module with the authoritative `D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`. The filename families are disjoint and complete; they are intentionally separate because RC6 limits each individual gate to 180 seconds. Run focused affected tests first, then the complete policy suite before acceptance. Offline validation must not call Gemini, VieNeu/TTS, or the canonical runtime.

## Safety boundaries

- **Production/runtime:** The canonical runtime is `http://127.0.0.1:8772`; keep it stopped unless a separately authorized operation requires it. Human Audio QA is the final authority.
- **Data:** `data/`, `backups/`, `experiment_b_transcript/`, and `runs/` are protected. Preserve immutable Text Revisions, Casting Plans, Jobs, snapshots, and verified Artifacts.
- **Production effects:** `PREPARE` and `START_RENDER` remain separate explicit operations. No provider, Gemini, VieNeu/TTS, render, or QA action is implied by development work.
- **Secrets/configuration:** Keep secrets outside source control, logs, and API responses.

## Definition of Done

Deliver the authorized observable outcome, run the relevant focused and policy validation, inspect the actual diff/output, preserve product and data safety, and leave the accepted worktree clean with evidence sufficient for the declared risk.

## Avoid

- Do not bypass configured quality gates or replace the complete test suite with a narrower acceptance claim.
- Do not infer a new product task from historical roadmap or status documentation.
