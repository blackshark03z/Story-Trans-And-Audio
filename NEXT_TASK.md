# Next Task

Task classification:
`PRODUCTION_OPERATION / HUMAN_AUDIO_QA_REQUIRED`

Active milestone:
`DAILY-PROD-5 - Batch Approval, Prepare, Render And QA Closeout`

Exact next task:
`Listen to active Artifact 90 for Book 8 Chapter 1 and record Human QA acceptance or one precise remediation target.`

## Verified Output

- Job/JobChapter `25 / 25`: `completed`.
- Revision/Plan/voice: `3985`, Plan `26` revision `3`, `Đức Trí`.
- Active Artifact: `90`, SHA-256
  `82f04cccb08d7f0d718038cabfe0516d2aa65f29093f8ae634630d8b64597e5d`,
  `24250 ms`, `419846` bytes.
- Segments: `8 / 8` verified, retries `0`.
- Technical/offline ASR conclusion:
  `TECHNICALLY_VALID_AND_INTELLIGIBILITY_SCREEN_PASS`.
- Audio Library, playback, download/hash, and restart persistence passed.
- Human QA for Artifact `90`: `pending`.

## Operator Step

- Open Artifact `90` from Audio Library and listen through the full 24.25-second
  output.
- Record `approved` only if the human listening result is acceptable.
- Otherwise record `needs_fixes` with one precise audible defect and location.

## Excluded

- Do not create another Job or rerender automatically.
- Do not change Revision `3985`, Plan `26`, Artifact `87`, Jobs `23`/`24`, or
  Chapter `369`.
- Do not advance to a multi-chapter render until Artifact `90` Human QA is
  recorded.
