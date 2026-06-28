# Next Task

Current Sprint:
YouTube Auto Handoff V2

Current Task:
Chapter Output Package for YouTube Auto (deferred until user approval)

Status:
Deferred — Custom Voice UI workflow complete and merged into main

Previous Task Summary:
Custom Reference Voice Library UI completed and merged via PR #2. Compact Preset Voice Preview restored, smoke/test books hidden by default with "Show test data" checkbox, Custom Voice forms use full-width vertical labels and responsive two-column upload layout. Custom Voice Library remains single custom-reference workflow. Test count: 613 tests passing (3 known pre-existing failures in brittle minified-JavaScript assertions unrelated to changes). Real manual smoke passed. Live DB unchanged. No migration required.

Next Steps (awaiting user approval):
Implement Chapter Output Package for YouTube Auto with real chapter render validation:
- Segment-level timeline.json with speaker labels, timestamps derived from final assembled audio
- Subtitles.srt with relative timestamps
- Manifest.json with chapter metadata and artifact references
- Real handoff smoke test with full chapter render
- Relative paths for portable bundle structure

Backlog:
- Make smoke-title filter more conservative so legitimate book titles containing the word "smoke" are not accidentally hidden

Deferred:
- Word-level forced alignment
- Karaoke-style caption rendering
- Lip sync metadata
- Generic production hardening
- Multi-worker load testing
