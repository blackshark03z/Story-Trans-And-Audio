# Story Audio UI/UX Adapter

This file is a Story Audio-specific adapter for the canonical CADS product
skills. It is not a separate UI/UX standard and must not compete with or fork
CADS guidance.

## Canonical CADS routing

Use the CADS product skills conditionally:

1. `user-facing-workflow.md` when the user journey, navigation, discoverability,
   task order, or next-action placement is the real problem.
2. `frontend-design.md` when implementing or materially changing the rendered
   interface after the workflow is clear.
3. `ui-quality-review.md` before user-facing Product Acceptance, and whenever the
   Owner reports that the UI is difficult to find, understand, operate, recover,
   or trust.

A visible defect found during the active Goal still enters through CADS
Systematic Debugging, receives the smallest coherent repair, and returns to the
same Critical User Journey.

## Story Audio-specific checks

For Story Audio, add these checks to the applicable CADS skill:

- Canonical owner runtime: `http://127.0.0.1:8772`.
- Golden acceptance fixture: Book 1 `Quang Âm Chi Ngoại`, Chapters 2-8, unless
  `TASK.md` explicitly changes the active fixture.
- Treat the owner desktop workflow as primary; verify a representative 1280-1440
  px desktop width and a narrow width only when the changed surface is expected
  to reflow.
- Use representative long Vietnamese story text and realistic row/sample counts,
  not only short synthetic fixture strings.
- Verify both source and served assets when text/layout appears stale. CSS and JS
  cache identities must correspond to the changed surface.
- Vietnamese owner-facing text must remain valid UTF-8. If the legacy mixed
  frontend file makes literal editing risky, prefer the smallest stable Unicode
  escape or byte-level edit rather than rewriting unrelated content.
- PREPARE and START_RENDER remain explicit, separate owner actions. UI work must
  never bypass execution readiness or render guards.
- Rendered evidence and focused tests are supporting evidence only. Owner
  real-use of the same CUJ is the final Product Acceptance oracle.

## Exit

Do not open a design-system project from a local defect. Resolve only BLOCKER/HIGH
findings that materially affect the active CUJ, classify non-blocking visual
refinement as deferred polish, and resume the same Chapters 2-8 journey.
