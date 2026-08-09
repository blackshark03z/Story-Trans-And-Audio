# Project Contract

Updated: 2026-08-09
Project ID: story-audio
Owner: Story Audio Owner
Project Status: ACTIVE

## Product Problem

Create trustworthy audiobook-style chapter audio from multiple EPUB books while
keeping book-specific character, casting, voice, production, repair, and
acceptance decisions under operator control.

## Target User

Local Story Audio operator producing chapter audio from EPUB books.

## Primary User Workflow

1. Import EPUB.
2. Choose book and manage that book's voices.
3. Select one or more chapters; detect characters and speakers.
4. Review, add, or adjust casting; resolve every required voice.
5. Confirm production settings and generate audio.
6. Listen, mark errors including timestamps, repair, accept, and download MP3/WAV.

## MVP Goal

The operator completes the frozen North Star journey from EPUB import through
accepted downloadable chapter audio, with explicit control over AI proposals.

## Success Criteria

### SC-001
- User: Local Story Audio operator producing chapter audio from EPUB books.
- Action: Complete the North Star journey for a representative EPUB chapter.
- Observable result: The operator can review and explicitly accept complete
  chapter audio, then download MP3; WAV is available when requested.
- Acceptance threshold: Intended content, acceptable character/speaker
  attribution and effective voices, intact beginning/end, no material
  unintended repetition or malformed/missing speech, operator-acceptable
  pacing, explicit human acceptance, and downloadable accepted audio.
- Demo method: Operator walkthrough using a representative EPUB book and chapter.

## In Scope

- Multiple EPUB books and book selection.
- Book-scoped voice libraries, including custom voice creation and management.
- Character/speaker detection, known-character reuse, Gemini proposals for
  unknown characters, and operator review/correction of all proposals.
- Book-context casting, visible production readiness, settings confirmation,
  explicit generation, listening, timestamp feedback, repair, acceptance, and
  MP3/WAV download.
- Batched analysis/rendering with independent per-chapter production, QA,
  acceptance, and download status.

## Out of Scope / Later

- Translation, rewriting, or editorial story-content changes.
- Video creation, thumbnails, YouTube metadata, or YouTube upload.
- General-purpose audio editing and multi-user SaaS behavior.
- Cross-book global voice sharing.

## Supported Cases

- A book owns character, casting, and voice decisions.
- Known characters reuse the book's established identity/casting; unknowns
  receive operator-reviewable Gemini proposals.
- Missing required voice/casting blocks readiness before paid rendering.
- Accepted chapter audio retains traceable historical provenance even when a
  voice is later removed from normal use.

## Explicitly Unsupported Cases

- Silent irreversible AI casting decisions.
- Rendering with unresolved required voice/casting.
- Making a custom voice from Book A automatically available to Book B.

## Current Milestone

- Milestone ID: PRODUCT-GOAL-001
- User outcome: Complete the frozen North Star journey.
- Success Criterion: SC-001
- Demonstrable outcome: Explicitly accepted, downloadable chapter audio.
- Time-to-first-demo expectation: smallest vertical slice first.
- Maximum consecutive non-shipping tasks: 3

## Product Principles

1. One task completes one operator-visible outcome.
2. AI reduces repetitive decisions but never silently makes uncertain casting irreversible.
3. Known character/casting knowledge accumulates within a book.
4. Missing required voice/casting blocks generation before paid rendering.
5. Human QA is final chapter-audio acceptance authority.
6. Repair feedback, including timestamps, survives the repair lifecycle.
7. Batch operation does not make good chapters wait for unrelated failures.
8. UI uses BOOK / CHARACTER / VOICE / CHAPTER / AUDIO unless implementation
   detail is necessary for error or recovery.
9. Future features must reduce operator effort/errors, improve audio quality,
   or reduce safe production time/cost; infrastructure alone is not an outcome.

## Technical Baseline

- Language/runtime: Python (`D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe`)
- Framework: FastAPI
- Database: SQLite; canonical `data/app.db`, schema 15
- Package manager: pip
- Entry point: `run_app.ps1`
- Run command: `run_app.ps1` (canonical runtime `http://127.0.0.1:8772`)
- Install command: `python -m pip install -e .`
- Test command: `python -m unittest discover -s tests -v`
- Lint command: PROJECT_SPECIFIC
- Typecheck command: PROJECT_SPECIFIC
- Build command: NONE_REQUIRED_OR_PROJECT_SPECIFIC
- CI quality command: PROJECT_SPECIFIC
- CI quality capabilities: test
- Important directories: `story_audio/`, `ui/`, `tests/`, `data/`

## Risk Surface Map

- R2 paths: `story_audio/**`, `ui/**`, `scripts/**`
- R3 paths: `data/**`, `backups/**`, `runs/**`, `experiment_b_transcript/**`
- Sensitive business terms: PREPARE, START_RENDER, Gemini, VieNeu, TTS,
  casting, artifact, Chapter 369, canonical DB

## Architecture Budget

- Default architecture: modular monolith
- New deployables without owner approval: 0
- New databases without owner approval: 0
- New framework requires owner approval: yes
- New production dependency requires justification: yes
- Abstraction requires real variation or tested boundary: yes

## Codebase Health Policy

- Health mode: RATCHET
- Architecture boundaries config: `config/codebase_health.json`
- Architecture decision: configure boundaries or record an explicit no-boundaries reason before protected CI
- Tracked build/cache artifacts: prohibited unless explicitly allowlisted
- Large new binary threshold: 5 MB
- New runtime dependency: structured capability / alternatives / removal-cost decision required
- Cleanup budget: bounded to touched area; broad rewrites require a separate Goal
- Refactor priority: change-frequency × rework/defect hotspot, not file size alone

## Quality Priorities

1. Functional acceptance.
2. Data/security safety.
3. Evidence appropriate to risk tier.
4. Maintainability sufficient for the next milestone.

## Owner Authorization Policy

### Pre-authorized

- Read-only inspection and local focused fixture tests.

### Explicit approval required

- Production mutation, provider/TTS cost, migration, delete/overwrite,
  secrets, deploy/publish, push/merge, or architecture change.

## Data and Artifact Policy

- Canonical data: `D:\Youtube\Story Trans And Audio\data\app.db`
- Test/clone data: fixtures/local clones only
- Default operation: READ_ONLY
- In-place mutation: explicit approval required
- Delete: explicit approval required
- Regeneration overwrite: prohibited unless explicitly authorized
- Backup/rollback: preserve immutable revisions/artifacts; back up before approved destructive operations

## Constraints

- Time: owner prioritizes safe operator-visible outcomes
- Financial: no unapproved paid provider escalation
- Privacy: no secrets in Git, logs, API responses, or state
- Platform: local Windows production runtime
- Licensing: owner-controlled local use
- External services: Gemini proposals and VieNeu/TTS only with explicit task authority

## Gap Inventory

See `docs/STORY_AUDIO_PRODUCT_GOAL_GAP_MAP.md`. This is an assessment, not
authorization to implement a gap.

## Historical Context

`.ai/PROJECT_PRE_V116.md`, `.ai/STATE_PRE_V116.md`, ROADMAP.md, NEXT_TASK.md,
and PROJECT_STATUS.md preserve pre-contract history. They do not redefine this
frozen Product Contract or authorize implementation.

## Scope Guard

Do not infer a task from historical roadmaps. Select and authorize one bounded
task against this Product Goal before changing application or production state.
