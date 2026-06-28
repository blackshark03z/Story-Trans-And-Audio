# Next Task

Current Sprint:
YouTube Auto Handoff V2

Current Task:
Chapter Output Package for YouTube Auto

Status:
Planned — Custom Voice workflow complete; output-contract audit pending

Previous Task Summary:
Custom Reference Voice Library UI completed with compact Preset Voice Preview restoration and UI usability consolidation. Test count: 584 tests passing (3 known false failures in minified JS assertions). No migration required.

Next Steps:
Implement Chapter Output Package for YouTube Auto with real chapter render validation:
- Segment-level timeline.json with speaker labels, timestamps derived from final assembled audio
- Subtitles.srt with relative timestamps
- Manifest.json with chapter metadata and artifact references
- Real handoff smoke test with full chapter render
- Relative paths for portable bundle structure

Deferred:
- Word-level forced alignment
- Karaoke-style caption rendering
- Lip sync metadata
- Generic production hardening
- Multi-worker load testing
