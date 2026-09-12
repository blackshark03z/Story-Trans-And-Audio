# DR-0001: One chapter repair request and one replacement revision

Status: Accepted
Date: 2026-09-12
Scope: UX

## Context

The machine audio shortlist exposed a separate create-repair action for every
finding. A chapter can contain several related pauses, pacing changes and audio
level problems, so this interaction required repeated decisions and implied one
replacement attempt per finding even though the Owner evaluates the chapter as
one listening task.

## Decision

The normal Owner path combines all selected findings for the exact current audio
artifact into one chapter-scoped Human QA repair request. The request leads to
one reviewed repair plan and one replacement revision. Finding rows support
listen and select/skip only; they do not each expose a primary create action.

Exact-segment candidate APIs may remain only to recover or resolve a candidate
that already exists. They are not a parallel primary workflow. Creating the
combined draft does not change current audio, call a provider, submit Human QA,
PREPARE, or START_RENDER; those existing authoritative steps remain separate.

## Why

This matches the Owner's chapter-level listening decision, removes repeated
primary actions, prevents avoidable replacement-version multiplication, and
reuses the existing Human QA and repair-plan authority instead of adding another
orchestration path.

## Consequences

- Findings are selected by default and may be skipped before review.
- One aggregate action shows the selected count and opens a review containing
  every selected timestamp.
- Current audio remains authoritative until the existing replacement workflow
  completes and the Owner makes the applicable Human QA decision.
- Per-finding repair creation must not return to the primary Audio surface.

## Revisit When

Revisit only if production evidence shows that some finding types must be
rendered or accepted independently and cannot safely coexist in one immutable
chapter repair plan. Visual preference alone is not sufficient to reopen the
decision.
