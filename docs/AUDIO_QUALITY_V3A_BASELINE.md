# Story Audio V3A Audio Quality Baseline

## Verdict

`READY_FOR_TECH_LEAD_REVIEW`

This baseline is evidence-backed, but it does not claim a new Human Audio QA verdict. Existing Human QA records remain the authority for naturalness, pronunciation, intelligibility, acting, and speaker correctness.

## Baseline And Safety

| Item | Value |
| --- | --- |
| Accepted source | `47f8f48d218f23d7c457ea1421de2c61d10aa795` |
| Accepted tree | `66ea70e0f6cf9ff7a3ad9e7f7f4115d559c38cdc` |
| Worktree | `D:\Youtube\_worktrees\story-audio-v3a-audio-quality-baseline` |
| Canonical DB mutated | No |
| Gemini called | No |
| VieNeu inference called | No |
| PREPARE / START_RENDER issued | No / No |
| Human QA changed | No |
| Historical artifact overwritten | No |

The canonical DB was opened read-only. Source audio was copied byte-for-byte to `C:\Users\ADMIN\AppData\Local\Temp\story_audio_v3a_audio_samples_v3` before inspection; no sample was modified. That directory is a disposable local listening/report package, not canonical production evidence.

## Representative Sample Set

| Role | Canonical provenance | Copied final SHA-256 | Why selected |
| --- | --- | --- | --- |
| Historical needs-fixes | Chapter 1, Job 33, JobChapter 34, Artifact 117 | `f72fc70e61b0f7c4ee23560efa8e31b1b73edfda11bed1d2542e4cd00bd88aa6` | Human QA recorded repeated words, distorted loudness, and unintelligible speech. |
| Human-approved narrator/dialogue | Chapter 367, Job 20, JobChapter 20, Artifact 75 | `376afa0250cc14ce368e36ff3f9842b8c33139d3ab0250b55f3e6ce92938d808` | Two resolved voices and a same-job targeted recovery. |
| Human-approved targeted reassembly | Chapter 368, Job 22, JobChapter 22, Artifact 84 | `6d4f27143aa99112cfbee706a6bdbf45f0adfdb0ff29be42477093bb5b43b90f` | Accepted two-segment overlay and reassembled result. |

All three copied finals decode as mono 48 kHz AAC. Their verified container durations are 334.080 s, 418.180 s, and 485.050 s. The copied master WAV and timeline hashes match their canonical artifacts. Newer completed jobs have intentionally cleaned their segment WAVs, so historic per-segment signal analysis is unavailable after cleanup; that is a retention limitation, not an audio failure.

For the reported Chapter 1 window, timeline sequence 29 covers 189.800--198.750 s and is text `Phốc!`; its exact copied WAV hash is `cbb2c487f4c83db1574debc366d380764359299c0deaffa93d9dc23f32962089`. It decodes as 8.950 s mono 48 kHz PCM without clipping, but has 2.890 s of internal silence (longest 546 ms). This is an automated risk signal, not proof of the reported pronunciation/intelligibility defect.

## Quality Baseline

| Family | Evidence and layer | Classification | Action |
| --- | --- | --- | --- |
| Unintelligible/repeated speech and distorted loudness | Chapter 1 Artifact 117 has a durable Human `needs_fixes` record, while the underlying selected segment is valid PCM without clipping. The report is not explained by assembly/container corruption. | P1, `HUMAN_JUDGMENT_REQUIRED`; likely source synthesis, but insufficient controlled replay evidence to call it model-intrinsic. | Do not tune or rerender without separate authorization. |
| Excessive silence from synthesis | Historical Chapter 367 Segment 573 failed after three attempts with 83% silence (16.1 s of 19.4 s); the bounded same-job retry produced the accepted 1.350 s result, with verified peers reused. | P1, `OBJECTIVE_DEFECT`; source synthesis/TTS invocation. | Already corrected through existing segment retry semantics; no new change justified. |
| Accepted repair-block QA rejection | Chapter 368 accepted repair block 1 replaces segments 665--666 with one immutable candidate. Its timeline has 48 items for 49 original segment rows by design. Existing QA incorrectly required a one-to-one row count/hash/text match. | P1, `OBJECTIVE_DEFECT`; QA/provenance interpretation, not audible assembly damage. | Fixed in this delta. |
| Decode, duration, clipping, channel/sample-rate | Existing QA and copied artifacts verify decode integrity, hashes, duration, mono 48 kHz, silence and clipping metrics. | Covered automatically. | No change. |
| Naturalness, pronunciation, cadence, correct speaker by ear | Existing QA explicitly does not make these claims; a valid waveform cannot establish them. | `HUMAN_JUDGMENT_REQUIRED`. | Preserve Human QA authority and use the deterministic listening/report package. |

## Existing QA Coverage

`story_audio.audio_qa` already provides deterministic checks for manifest and artifact hashes, decode integrity, sample rate/channels, duration consistency, hard/near clipping, silence spans, loudness/rate outliers, missing segment files, and voice/segment metadata. `story_audio.listening_checklist` preserves the separate local Human QA path and does not write a verdict back automatically.

It does not detect semantic repetition, pronunciation, naturalness, acting, or speaker correctness. Those require Human Audio QA. It also cannot recover per-segment signal inspection after the deliberate WAV cleanup; master/final artifact inspection remains available.

## Root Cause And Fix

### Accepted multi-segment repair block

**Before:** Audio QA rejected an accepted repair-block render because it treated one overlay timeline item as one original segment. The accepted overlay correctly contains its own source-text hash and candidate-audio hash, and covers two immutable original segment IDs.

**Root cause:** the QA reader knew only the generic `segments` rows. It did not read the accepted `audio_repair_blocks` provenance contract used by the existing assembler.

**Change:** QA now reads accepted repair blocks read-only and validates the overlay's block ID, ordered covered IDs, first/last sequence, source-text hash, candidate-audio hash, and candidate WAV. Timeline coverage must still account for every original segment exactly once. The result is marked `repair_block_aggregates_multiple_segments`.

**After:** a direct offline regression fixture creates a valid two-segment accepted repair block and confirms the QA report succeeds without mutating its source rows or candidate state.

## Deferred

- P2: punctuation/cadence refinement, join polish, and any loudness policy change require a new measured sample and product decision.
- TTS-model experimentation is deferred. The current evidence is `INSUFFICIENT_EVIDENCE`: a source-synthesis problem is proven in history, but no authorized controlled render comparison distinguishes model behavior from particular voice-reference/input conditions.
- No VieNeu upgrade, provider/model swap, or parameter sweep was performed.

## Verification

```powershell
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest tests.test_audio_repair_blocks tests.test_audio_qa -v
```

The focused/affected run passed offline. It uses generated fixture WAVs only; it makes no provider call.

## Next Product Decision

Authorize one tiny, disposable, bounded VieNeu comparison only if the Tech Lead needs to separate custom-reference/input-specific source-synthesis failures from a model-intrinsic issue. The proposed sample is the already-proven Chapter 1 window, with exact text/voice/settings recorded above; do not start that experiment under V3A without explicit authority.

