# Next Task

Task classification:
`PRODUCTION_OPERATION / EXPLICIT_START_RENDER_AUTHORIZATION_REQUIRED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`Request explicit authorization to START_RENDER only prepared replacement Job 25 for Book 8 Chapter 1.`

## Verified Input

- Active approved Text Revision: `3985`, parent `3971`, `378` characters,
  SHA-256
  `ff9053993e437319dfd7b8b9159dbee4a2ac86be824fe9418765cc3664306f22`.
- Approved Casting Plan: `26`, revision `3`, eight utterances using `Đức Trí`.
- Prepared Job/JobChapter: `25 / 25`, pinned to Revision `3985` and Plan `26`.
- PREPARE request: `3`, durable `APPLIED`; restart status `APPLIED_REPLAYED`.
- Job `25` has zero Segments, attempts, Artifacts, output files, and audio.

## Required Authorization

- Confirm the operator intends to start only Job `25`.
- Revalidate Job `25` remains `prepared`, its immutable pins still resolve, and
  no conflicting live job exists.
- Use the supported explicit START_RENDER route once, then monitor the same Job.

## Excluded

- Do not start Job `25` without fresh explicit authorization.
- Do not retry Jobs `23` or `24`, replace Artifact `87`, create another
  replacement Job, or mutate Chapter `369`.
- Do not alter Revision `3971`, Revision `3985`, Plan `26`, or pinned voices.
