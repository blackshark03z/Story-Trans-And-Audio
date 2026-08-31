# V2D Daily Production Usability And Performance

## Outcome

Routine daily production remains the accepted V2C journey, while active
operator surfaces avoid unnecessary background work and preserve the exact
current scope and safety boundaries.

## Constraints

No provider, VieNeu, Gemini, canonical DB, PREPARE, START_RENDER, or Human QA
mutation is authorized. Use an isolated worktree and deterministic fixtures.
Keep protected data paths untouched and do not modify Build OS source.

## Friction audit

- **P1 — inactive Production refresh:** a Jobs refresh while the operator was
  on Assignment still requested both the Production task projection and
  preflight. The browser fixture recorded one request to each endpoint for one
  inactive refresh. **Fix:** refresh only the visible operator surface; load a
  fresh guarded projection when returning to Production.
- No P0 issue was observed in the fixture-backed V2C journey. No P2 finding
  was implemented.

## UX and safety contract

```text
PRIMARY_JOURNEY=Home -> choose/resume book range -> resolve the next required exception -> review readiness -> explicit PREPARE/START_RENDER boundaries -> monitor -> Human Audio QA -> resume Production.
SCOPE_MODEL=One selected book and one contiguous chapter range persist through relevant detours and refresh.
PRIMARY_CONTROLS=Choose scope, one canonical next action, and return to Production.
SAFETY=PREPARE and START_RENDER remain distinct; Human QA remains human authority.
```

## Verification

- V2C fixture browser journeys passed before the change: Home, scope,
  preflight, contextual return, range exceptions, and task workbench.
- The V2D browser workbench fixture verifies 1366×768 and 1920×1080 layouts,
  one primary action, scope-preserving flows, busy/error/retry behavior, QA
  entry, and no Production projection/preflight request during an inactive
  Assignment refresh.
- Focused offline task-projection, preflight, and production-command tests run
  against isolated data only.

## Next

Ready for Tech Lead review once final focused browser checks, scope guard, and
Git inspection pass. No provider, canonical DB, PREPARE, START_RENDER, or
Human QA action is authorized by this task.
