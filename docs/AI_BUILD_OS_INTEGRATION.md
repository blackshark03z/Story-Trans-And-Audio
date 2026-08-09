# Senior AI Build OS integration

- Installed version: Senior AI Build OS Reusable v1.16 (`VERSION` = `1.16`).
- Kernel: `scripts/ai.py`, `scripts/ai_os.py`, supporting modules, `config/`,
  `templates/`, `prompts/`, `.ai/`, and `.github/workflows/ai-build-os.yml`.
- Reference documentation with package provenance: `docs/ai-build-os/package/`.
- Authority order: runtime/data > Git snapshot and task-start baseline >
  immutable Build OS evidence > `.ai/PROJECT.md` / `.ai/ACTIVE_TASK.md` /
  `.ai/STATE.md` > chat or external recovery summaries.
- Story Audio extends the kernel through `AGENTS.md`, which retains stricter
  canonical DB/runtime, immutable revision/artifact, PREPARE/START_RENDER,
  provider authorization, Chapter 369, single-writer, protected-root, and
  non-destructive Git rules.
- Current assurance: A1 (repo-local lifecycle/validator controls only).
- Validate with the authoritative Python interpreter: `python -m py_compile
  scripts/*.py`; `python scripts/validate_ai_os.py --template`; `python
  scripts/self_test_fast.py`; `python scripts/ai_os.py doctor`; `python
  scripts/ai_os.py assurance`; and `python scripts/ai.py --help`.
- Known Windows verifier exception: supplied `scripts/self_test_v116.py` passes
  a quoted multi-token interpreter command through argv-mode execution and
  raises `WinError 2`. The original is preserved unchanged. The project-local
  `tools/ai-build-os/windows_v116_acceptance.py` performs equivalent acceptance
  against the unmodified installed kernel with a single Windows executable
  proof command. This is the v1.16 verifier-infrastructure stop-loss method
  change, not a Story Audio product defect.
- Product Contract initialization is intentionally pending: the existing
  ROADMAP, NEXT_TASK, and historical `.ai` records are context only; they are
  not a new owner-approved Product Goal.
