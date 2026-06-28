# Next Task

Current Sprint:
Multi Custom Voice Ready for Personal Use

Current Task:
UI Integration — Load Custom Voices into Voice Selects

Status:
Backend complete; UI integration pending

## Implementation Phases

### Phase 1: UI Integration (Current)
**Goal**: Expose custom voices in Book Voice Profile, Character Override, and Manual Casting voice selects

**Scope**:
- JavaScript `loadCustomVoices()` function to call `/api/custom-voices`
- Merge custom voices into `castingVoiceOptions()` alongside presets
- Display format: `"<display_name> (Custom)"` to distinguish from presets
- Voice ID format: `custom:<id>` for backend resolution
- Update Book Voice Profile narrator/male/female dropdowns
- Update Character Override voice dropdown
- Update Manual Casting narrator/character dropdowns
- Preserve preset-only backward compatibility

**Acceptance Criteria**:
- User can select custom voice for Book Voice Profile narrator
- User can select custom voice for Character Override
- User can select custom voice in Manual Casting
- Preview effective voice resolution shows custom voices
- No breaking changes to preset-only workflows
- JavaScript syntax check passes
- Live DB remains unchanged

**Technical Notes**:
- `/api/voices` returns presets only (preserve this)
- `/api/custom-voices` returns active custom voices
- `castingVoiceOptions()` currently uses `state.voices` (presets)
- Need to merge `state.customVoices` into dropdown options
- Backend already validates `custom:<id>` in all voice resolution paths

### Phase 2: Short Smoke Test
**Goal**: 3-utterance mixed custom/preset render without full chapter complexity

**Scope**:
- Isolated test book with minimal chapter (3 utterances max)
- One custom voice + one preset voice
- Manual Casting Plan approval
- Full job/TTS/assemble/export cycle
- Verify mixed voice segments
- Verify timeline resolution metadata
- Doctor checks pass

**Acceptance Criteria**:
- Job completes with mixed custom/preset segments
- Timeline shows correct `custom_reference` kind for custom segments
- Audio artifact verified and playable
- Controlled retry reuses snapshot correctly
- No schema migration required

### Phase 3: Real Chapter Render
**Goal**: Full chapter with custom voices in narrator/male/female slots

**Scope**:
- Real chapter from `Quang Âm Chi Ngoại` (20–50 utterances)
- Book Voice Profile with custom narrator + preset male/female
- Speaker Review/Approval workflow
- Full render (VieNeu thật)
- Verify voice distribution across segments
- Verify audio quality and timeline accuracy

**Acceptance Criteria**:
- Chapter renders successfully with custom narrator
- Voice distribution matches Casting Plan snapshot
- Timeline resolution metadata correct for all segments
- Audio playable with no corruption
- Handoff export includes correct custom voice references

### Phase 4: Retry Validation
**Goal**: Verify custom voice snapshot preservation during retry

**Scope**:
- Force segment failure in Phase 3 chapter
- Retry failed segment
- Verify custom voice revision ID preserved
- Verify reference audio/transcript unchanged
- Verify peer segments not re-rendered

**Acceptance Criteria**:
- Retry uses exact snapshot (revision ID, audio SHA, transcript SHA)
- Verified segments retain original hash/mtime
- Final artifact incorporates retry segment correctly
- Doctor deep check passes

### Phase 5: Documentation Closeout
**Goal**: Update project documentation to reflect ready-for-personal-use status

**Scope**:
- Update `PROJECT_STATUS.md` with verified baseline
- Update `ROADMAP.md` to mark feature complete
- Update `CHANGELOG.md` with UI integration details
- Update `NEXT_TASK.md` for next priority
- Commit documentation with summary of validation results

**Acceptance Criteria**:
- Documentation reflects "Ready for Personal Use"
- Known limitations clearly documented
- Test counts accurate (current + new UI tests)
- Live DB SHA-256 verified unchanged
- Git status clean

## Previous Task Summary

Custom Reference Voice Library UI completed and merged via PR #2. Compact Preset Voice Preview restored, smoke/test books hidden by default with "Show test data" checkbox, Custom Voice forms use full-width vertical labels and responsive two-column upload layout. Custom Voice Library remains single custom-reference workflow. Test count: 613 tests passing (3 known pre-existing failures in brittle minified-JavaScript assertions unrelated to changes). Real manual smoke passed. Live DB unchanged. No migration required.

Custom Voice Backend Resolution & Snapshot Support completed (Phase 3A/3B). voice_ref.py `custom:<id>` parser, CustomVoiceContext catalog, resolver integration in casting/profile/pipeline, 14-field immutable snapshot, snapshot-based TTS synthesis, fail-closed legacy policy. Test count: 377 tests (92 new snapshot tests). Real VieNeu smoke: preset 1.04s + custom 4.31s. Migration 0007 applied. Live DB schema version 7, code supports schema version 7.

## Deferred Tasks

- Chapter Output Package for YouTube Auto (awaiting user approval after Multi Custom Voice complete)
- Make smoke-title filter more conservative
- Word-level forced alignment
- Production hardening (multi-worker, load testing, distributed locking)