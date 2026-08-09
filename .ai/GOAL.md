# Active Goal

Goal ID: STORY_AUDIO_PRODUCT_GOAL_R3
Goal Status: ACTIVE
Goal Type: product
Risk Ceiling: R3
Updated: 2026-08-09T08:14:22+00:00

## Outcome

Story Audio enables a local operator to create, review, repair, accept, and download trustworthy audiobook-style chapter audio from multiple EPUB books with book-scoped characters, casting, and voices.

## Acceptance

- [ ] A representative EPUB chapter can follow the frozen North Star journey from import through explicit human acceptance and downloadable MP3, with WAV available when requested.
- [ ] Known book characters reuse established identity and casting; uncertain unknown-character proposals remain operator-reviewable and editable.
- [ ] Missing required voice or casting clearly blocks production readiness before paid rendering.
- [ ] Multi-chapter analysis or rendering preserves independent chapter production, QA, acceptance, and download status.

## Acceptance Quality

- Falsifiability heuristic: no high-confidence warnings

## Goal Acceptance Contract

- Status: FROZEN c47f0646951a
- Criterion mappings: 4/4

## Non-Goals

- Translation, rewriting, or editorial story-content changes.
- Video creation, thumbnails, YouTube metadata, or YouTube upload.
- General-purpose audio editing or multi-user SaaS behavior.

## Budget

- Maximum tasks: 8
- Maximum parallel writers: 1
- Maximum consecutive non-shipping tasks: 2
- Maximum revisions per task before stop-loss: 2
- Scope growth limit: 60%
- Scout input budget: 24000 tokens
- Scout wall budget: 5.0 minutes
- Scout provider-cost budget: 0.0 (0 = unbounded/unavailable)

## Task Graph

| Node | Status | Agent | Risk | Delivery Delta | Depends On | Outcome |
|---|---|---|---|---|---|---|
| BOOK_SCOPED_CUSTOM_VOICE | ACTIVE | WORKER | R3 | USER_VISIBLE_BEHAVIOR | - | ADD CUSTOM VOICE TO SELECTED BOOK |

## Human Interrupt Policy

Only interrupt the owner for a genuine product decision, risk above ceiling/authorization, destructive/production authority, unresolved blocker, or final Goal acceptance. Worker reports are machine-to-machine state, not owner handoffs.
