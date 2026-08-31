# Historical Next Task

> This is a preserved 2026-08-25 Build OS compatibility snapshot, not current
> worker instruction. The active Story Audio product context is `TASK.md`.
> Use the Thin OS operating map in `AGENTS.md`; do not execute the legacy
> lifecycle/adoption work described below.

## Archived snapshot

Task classification:
`SYSTEM_ROADMAP / BUILD_OS_V125_ADOPTION_COMPATIBILITY_DECISION`

Active milestone:
`STORY_AUDIO_BASELINE_RECONCILIATION_V125_REPAIR`

Exact next task:
`Evaluate the official Build OS v1.25 RC4 additive-adoption boundary against the live v1.16 lifecycle state and proceed only with positive compatibility proof.`

## Verified Baseline

- The offline suite passes all `1,970` tests with one expected Windows skip.
- The machine-readable Project CI contract passes the same test contract.
- The canonical runtime is stopped; port `8772` has no listener.
- The canonical database is schema `16`, `quick_check = ok`, with zero
  foreign-key violations and unchanged SHA-256
  `4f816add7efea7cd32e5177f10fba03c998362b0d24f6d4fa224ff8873369b55`.
- Artifact `93` is stale historical `needs_fixes` evidence and is not a current
  listening or QA target.
- Chapter `372` is bound to active Artifact `99`, which is Human-QA approved.
- Chapter `373` is bound to active Artifact `96`, whose Human QA remains
  pending.
- Chapter `1` is bound to active Artifact `120`; its older `needs_fixes` record
  belongs to stale Artifact `117`, so Artifact `120` is not accepted.

## Decision Gate

Use only the official v1.25 adoption and migration contracts. Preserve v1.16
history as immutable provenance. Do not archive, remove, or replace the live
v1.16 executor/state surface unless the official mechanism proves how the
current Goal reaches a truthful terminal state across that transition.

If that proof is absent, stop with a documented adoption blocker and preserve
the repaired baseline. Do not improvise a direct cross-version migration.

## Excluded

- No production PREPARE or START_RENDER.
- No provider, Gemini, VieNeu, or TTS call.
- No render, repair, retry, or Human QA decision.
- No canonical DB or protected Artifact mutation.
- No secret change, push, merge, or deploy.
