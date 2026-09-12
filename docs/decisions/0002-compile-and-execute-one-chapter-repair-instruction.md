# DR-0002: Compile and execute one immutable chapter repair instruction

Status: Accepted
Date: 2026-09-12
Scope: Backend and execution

## Context

DR-0001 established one chapter-scoped repair request and one replacement
revision. The existing backend persists Human QA, repair plan and repair draft
evidence, and PREPARE pins a `repair_instruction`. However machine finding
identity is lost before that snapshot, the repair review UI clears positions,
and the worker does not consume the instruction. A replacement render can
therefore run without applying the requested corrections.

## Decision

Keep the existing Human QA -> repair plan -> repair draft -> PREPARE ->
START_RENDER authority path. Extend its marker contract with exact source
segment and repair bindings, compile those bindings at PREPARE, and execute the
compiled instruction in the existing Pipeline worker.

For supported post-processing repairs (leading silence, trailing silence and
loudness), the replacement Job reuses the exact verified source segments,
applies all compatible selected transforms offline, verifies the target metrics,
and assembles one replacement artifact. Unchanged segments are copied, not sent
to TTS. The existing artifact activation remains the single commit point.

The completion amendment also treats reviewed speed and semantic repairs as
part of the same compiled instruction. Global and local speed are deterministic
offline tempo transforms. Repeated words and findings that cannot be repaired
truthfully by a filter re-synthesize only their exact reviewed segments after
START_RENDER; unchanged segments remain reused. A manual timestamp is resolved
through the verified current timeline and frozen to a segment ID/SHA during
PREPARE. Missing locations or local pace values remain blockers.

An instruction containing a stale binding, an unknown repair, or requested
semantics without an implemented executor fails closed. It must not silently
fall back to a normal full-chapter render or claim a repair was applied.

## Why

This closes the backend gap without creating a second orchestration path or a
new persistence subsystem. It reuses proven offline repair algorithms, current
immutable evidence, the existing prepared Job snapshot and the existing atomic
artifact activation boundary. It also makes provider cost and unsupported
behavior explicit.

## Consequences

- Machine findings carry stable artifact/segment/hash/repair identity through
  Human QA and every repair evidence layer.
- One replacement Job may execute several compatible repairs across several
  segments and still creates one chapter revision.
- Fully supported technical repairs require no provider call.
- Unsupported or underspecified repair remains visible and blocks execution;
  supported semantic repair re-synthesizes only its exact reviewed segment and
  still returns the chapter to pending Human QA.
- Exact-segment candidate endpoints remain recovery-only and are not the normal
  owner workflow.
- A local pace is an explicit override for its segment; it does not multiply the
  global chapter tempo. Missing location/pace input stops at review or PREPARE.
- Hybrid execution records one TTS attempt only for each exact resynthesis
  segment and removes partial replacement files on failure.

## Revisit When

Revisit when a verified provider-side executor exists for repeated-word or
prosody remediation, or production evidence proves a supported transform cannot
safely share the chapter-level replacement path.
