# V2C Daily Production Golden Journey

## Outcome

An operator can follow one clear, fixture-backed Story Audio production journey:
select or resume scope, resolve only required speaker or voice exceptions,
review readiness, reach the separate PREPARE and START_RENDER boundaries, monitor
work, enter Human Audio QA, and return to the same Production scope.

## Constraints

No provider, VieNeu, Gemini, canonical DB, PREPARE, START_RENDER, or Human QA
mutation is authorized. Use an isolated worktree and deterministic fixtures.
Keep protected data paths untouched and do not modify Build OS source.

## UX contract

```text
PRIMARY_USER=Local operator producing approved book chapters as audio.
PRIMARY_JOURNEY=Home -> choose/resume book range -> resolve the next required exception -> review readiness -> explicit PREPARE/START_RENDER boundaries -> monitor -> Human Audio QA -> resume Production.
PRIMARY_SURFACE=Production, reached from Home or a preserved contextual return.
INFORMATION_HIERARCHY=Active book/range and next action first; blockers and readiness next; technical details remain disclosed.
SCOPE_MODEL=One selected book and one contiguous chapter range persist through relevant detours and refresh.
PRIMARY_CONTROLS=Choose scope, one canonical next action, and return to Production.
ADVANCED_CONTROLS=Technical detail and diagnostics are collapsed unless requested.
STATES=No-book onboarding; loading/error retry; clear blocker remedy; explicit read-only or consequential effect.
DISCOVERABILITY=Home and Production expose the current scope and one next action without route knowledge.
ACCESSIBILITY=Native labeled controls, keyboard-reachable primary action, preserved focus, and status feedback.
OWNER_PREFERENCE=NONE.
```

## Initial findings

- V2A navigation and scope browser checks pass.
- V2B workbench checks pass.
- Repaired two V2C blockers: range-level actions no longer masquerade as a
  chapter detour, and compact desktop preflight keeps readiness information in
  the 1366×768 viewport.

## Next

Complete fixture-backed golden-journey and responsive browser acceptance, then
commit the bounded product and documentation changes.
