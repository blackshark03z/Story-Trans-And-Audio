# Tráº¡ng thÃ¡i dá»± Ã¡n

**Cáº­p nháº­t:** 2026-06-27T13:39 (Asia/Saigon)
**Milestone:** Controlled Maintenance Sprint
**Tráº¡ng thÃ¡i:** In Progress; cháº¡y `.\run_app.ps1` Ä‘á»ƒ má»Ÿ láº¡i `http://127.0.0.1:8766`

ÄÃ¢y lÃ  nguá»“n sá»± tháº­t ngáº¯n gá»n vá» tiáº¿n Ä‘á»™. Sau má»—i thay Ä‘á»•i Ä‘Ã¡ng ká»ƒ, cáº­p nháº­t file nÃ y thay vÃ¬ buá»™c ngÆ°á»i tiáº¿p theo Ä‘á»c lá»‹ch sá»­ chat hoáº·c toÃ n bá»™ kiáº¿n trÃºc.

## Baseline Ä‘Ã£ xÃ¡c minh

- EPUB: `Quang_Am_Chi_Ngoai.epub`.
- Import: 1 sÃ¡ch, 1.980 chÆ°Æ¡ng, khoáº£ng 12,6 triá»‡u kÃ½ tá»±.
- Storage: text blobs theo SHA-256; SQLite chá»‰ giá»¯ metadata/path.
- QA import: 600 issue Ä‘Æ°á»£c ghi Ä‘á»ƒ review.
- Gemini key: Ä‘Æ°á»£c nháº­n diá»‡n; khÃ´ng lÆ°u trong DB/log.
- VieNeu: v3 Turbo CPU/ONNX, 10 preset voice.
- FFmpeg/FFprobe: hoáº¡t Ä‘á»™ng.
- Schema migration: version 5 (`0005_speaker_assignment_drafts`), checksum-locked.
- Offline tests: 119 test Ä‘áº¡t.
- End-to-end smoke: chÆ°Æ¡ng 858, giá»ng Ngá»c Lan, Gemini `all_selected`.
- Káº¿t quáº£ smoke: 10/10 segment, M4A dÃ i 118.710 ms, artifact active.
- Multi-voice real-TTS smoke: isolated book 3 / chapter 1982, casting plan 2, job 3.
- Káº¿t quáº£ multi-voice: Ngá»c Lan + Gia Báº£o + ThÃ¡i SÆ¡n; 8 utterance/8 segment; M4A sau retry 22.810 ms.
- Controlled retry: render láº¡i Ä‘Ãºng segment 20 trong 2,47 giÃ¢y; 7 segment cÃ²n láº¡i giá»¯ nguyÃªn hash/mtime.
- Audio signal check: khÃ´ng cÃ³ silence trÃªn 0,8 giÃ¢y á»Ÿ -45 dB; mean volume ba voice lá»‡ch tá»‘i Ä‘a 3,2 dB.
- Backup smoke: 3.989 file, 60.216.155 byte, manifest/hash/SQLite verify Ä‘áº¡t.
- Restore smoke: sang data root má»›i, 13 Ä‘Æ°á»ng dáº«n Ä‘Æ°á»£c remap, deep integrity Ä‘áº¡t.
- Shared Gemini cache benchmark local: chapter 858/784/363 (1.958/6.198/18.641 kÃ½ tá»±) hit + hash + lexical validation láº§n lÆ°á»£t khoáº£ng 22/44/121 ms; khÃ´ng gá»i máº¡ng.
- Fake pipeline má»™t block: miss + lÆ°u revision khoáº£ng 66 ms; job/chapter thá»© hai shared-cache hit khoáº£ng 54 ms; fake Gemini chá»‰ Ä‘Æ°á»£c gá»i má»™t láº§n.
- Three-Voice UI smoke: isolated book 4/chapter 1983, jobs 4â€“5, 8 utterance; profile v1â†’v2 vÃ  controlled retry giá»¯ snapshot cÅ©.
- Preview tháº­t: Ngá»c Lan 14,16s, Gia Báº£o 14,48s, Má»¹ DuyÃªn 15,12s; fallback reuse Ngá»c Lan cache.
- Three-Voice real-TTS: job 4 dÃ i 24.650 ms, job 5 dÃ i 26.090 ms; narrator/male/female/unknown/override vÃ  timeline resolution metadata Ä‘á»u Ä‘áº¡t.
- Character Bible Import Core: JSON V1 dry-run/apply CLI + backend API, schema v4, alias/external-key/role/metadata/provenance storage, idempotent re-import.
- Character Bible smoke: isolated book 5, dry-run create 3, first apply create 3 + 2 aliases, second apply match 3/no writes; API read and voice resolution verified.
- Character Bible UI + Handoff Integration: UI JSON dry-run/apply, metadata editor/aliases/provenance display, and YouTube Auto `character_seed.json` exports canonical metadata/aliases/notes.
- Gemini Speaker Assignment Draft Core: deterministic target/context, Character Bible candidates, structured V1 response, strict validation, Shared Gemini Cache, immutable schema-v5 draft persistence vÃ  API/CLI.
- Real Gemini speaker smoke: chapter 1982, one target, draft #1 valid 1/1 vá»›i `needs_review=true`; láº§n hai cache hit/reuse cÃ¹ng fingerprint/content.
- Speaker Review real smoke: isolated book 7/chapter 1985, 15 utterance; Draft #3 valid 15/15 vá»›i 7 high, 8 medium vÃ  alternatives cho cÃ¡c dÃ²ng há»™i thoáº¡i.
- Review smoke Ä‘Ã£ chá»n suggestion, Gemini alternative, manual character vÃ  unknown correction; partial approval táº¡o plan #5, final approval táº¡o plan #6, exact repeat reuse plan #6.
- Approval khÃ´ng táº¡o job/audio; jobs #1â€“#5, Book Voice Profile, Character Bible vÃ  immutable draft hash giá»¯ nguyÃªn.
- Handoff regression tháº­t: bundle má»›i export hai láº§n cÃ¹ng reuse identity `3255141aa34f`; bundle cÅ© `93ff2e0a367a` vÃ  bundle metadata má»›i Ä‘á»u verify/import láº¡i trong YouTube Auto vá»›i `Reused: True`.
- Long-Chapter Validation Phase 1: chá»n `Quang Ã‚m Chi Ngoáº¡i` chapter 56, TextRevision #112, 210 utterance, 101 speaker-review targets.
- Preflight Phase 1 thÃªm Character Bible tá»‘i thiá»ƒu cho Äá»— NhÆ°á»£c (#21) vÃ  Cáº£nh Minh (#22), Book Voice Profile v1 Ngá»c Lan/Äá»©c TrÃ­/Má»¹ DuyÃªn; hai character import lá»—i mÃ£ hÃ³a (#19/#20) Ä‘Ã£ bá»‹ deactivate vÃ  khÃ´ng tham gia candidate.
- Gemini draft #4 dÃ¹ng `gemini-2.5-flash`, prompt `speaker-assignment-v2`, 6 batch, 101/101 valid, 0 invalid, content hash `ed43ff4e...`, input fingerprint `df56fd73...`.
- Review UI tháº­t: partial approval táº¡o plan #7 vá»›i 15 decision; final approval táº¡o plan #8 vá»›i 86 decision cÃ²n láº¡i, 0 remaining; exact repeat reuse plan #8.
- Accuracy smoke Phase 1: 40/40 máº«u thá»§ cÃ´ng Ä‘Ãºng, gá»“m 29 dialogue/target vÃ  11 narrator/background; TextRevision hash, Character Bible fingerprint, draft hash giá»¯ nguyÃªn; job/segment/artifact váº«n 5/42/24, khÃ´ng render audio.
- Long-Chapter Validation Phase 2: táº¡o job #6 thá»§ cÃ´ng tá»« Casting Plan #8, render VieNeu tháº­t chapter 56 vá»›i 210/210 segment verified, final M4A render_0002 dÃ i 752.310 s.
- Phase 2 voice distribution Ä‘Ãºng snapshot: Ngá»c Lan 110 segment, Äá»©c TrÃ­ 56 segment, Má»¹ DuyÃªn 44 segment; sequence 1-210 liÃªn tá»¥c, khÃ´ng thiáº¿u/duplicate.
- Phase 2 controlled retry dÃ¹ng `retry_segment` cho segment #247; 4 segment Ä‘á»‘i chá»©ng giá»¯ nguyÃªn hash/mtime, segment retry Ä‘á»•i hash/mtime, render_0001 váº«n cÃ²n vÃ  final cÅ© chuyá»ƒn `stale`, render_0002 lÃ  `active`.
- Phase 2 validation: TextRevision #112 hash match, Casting Plan #8 hash match, speaker draft/casting plan khÃ´ng tÄƒng, Doctor `critical_errors=0`, 119 offline tests vÃ  JS syntax check Ä‘áº¡t.
- Doctor deep after schema v5: SQLite quick check OK, draft/cache/blob integrity OK, `critical_errors=0`; Character/Casting/Job/Segment/Artifact/TextRevision rows giá»‘ng backup v4 trÆ°á»›c migration.

## Shared Gemini cache contract

- Key pin source SHA-256, model, prompt version, punctuation-only contract, block splitter, lexical validator vÃ  generation settings.
- Thá»© tá»± reuse: approved repaired TextRevision â†’ job repair-block checkpoint â†’ shared cache â†’ Gemini API.
- Cache hit luÃ´n verify manifest/key/blob/hash/count vÃ  lexical tokens; entry há»ng/máº¥t lÃ  safe miss.
- Manifest náº±m trong `data/cache/gemini_repairs/`; repaired payload dÃ¹ng text blob báº¥t biáº¿n. Cleanup TTL/quota chá»‰ xÃ³a manifest vÃ  máº·c Ä‘á»‹nh dry-run.

## Quyáº¿t Ä‘á»‹nh voice casting Personal Edition

Audio casting máº·c Ä‘á»‹nh dÃ¹ng ba nhÃ³m voice cáº¥p book: narrator, male dialogue vÃ  female dialogue; unknown fallback máº·c Ä‘á»‹nh vá» narrator. Character identity tÃ¡ch khá»i voice identity vÃ  chá»‰ nhÃ¢n váº­t quan trá»ng má»›i cÃ³ optional voice override. Resolver deterministic vÃ  snapshot profile/version/source vÃ o casting/job má»›i; plan/job cÅ© khÃ´ng bá»‹ resolve láº¡i. Custom voice Ä‘Æ°á»£c quáº£n lÃ½ á»Ÿ cáº¥p Global Library, lÆ°u trá»¯ nguyÃªn báº£n audio vÃ  transcript Ä‘á»ƒ clone voice qua VieNeu reference-audio engine.

## Chá»©c nÄƒng Ä‘Ã£ hoÃ n thÃ nh

- [x] Import EPUB vÃ  SHA deduplication.
- [x] Sá»­a sá»‘ chÆ°Æ¡ng sai dá»±a trÃªn spine/href.
- [x] Raw/reflowed/repaired TextRevision.
- [x] Lossless hard-wrap reflow vÃ  QA issue.
- [x] Gemini punctuation repair theo block.
- [x] KhÃ´i phá»¥c exact token spelling/casing tá»« nguá»“n.
- [x] Lexical integrity validation.
- [x] Chá»n má»™t chÆ°Æ¡ng hoáº·c khoáº£ng tá»«â€“Ä‘áº¿n.
- [x] Chá»n preset voice, Gemini mode vÃ  M4A/MP3.
- [x] Cá»­a sá»• undo 10 giÃ¢y.
- [x] Checkpoint Gemini block vÃ  TTS segment.
- [x] Pause, resume, cancel vÃ  retry.
- [x] Master WAV, audio export vÃ  segment timeline.
- [x] Artifact/revision vÃ  dependency cÆ¡ báº£n.
- [x] Audio player trong chapter dialog.
- [x] Cleanup segment sau retention 24 giá».
- [x] Schema version vÃ  migration runner tá»± Ä‘á»™ng khi startup.
- [x] Fail-safe khi DB má»›i hÆ¡n code hoáº·c checksum migration bá»‹ Ä‘á»•i.
- [x] Backup/verify/restore cÃ³ manifest vÃ  SQLite snapshot nháº¥t quÃ¡n.
- [x] Recovery tests offline cho restart, retry, cancel vÃ  artifact corruption.
- [x] Diagnostic UI ba cáº¥p cho job, chapter vÃ  segment; retry riÃªng pháº§n lá»—i.
- [x] Voice preview preset 10â€“20 giÃ¢y vá»›i file cache Ä‘á»™c láº­p, khÃ´ng táº¡o job/artifact.
- [x] Character Voice MVP: character manager, manual casting revision vÃ  multi-voice render.
- [x] Real VieNeu multi-voice smoke vÃ  controlled retry/reuse verification.
- [x] Text Revision Diff raw/reflowed/repaired vá»›i Inline vÃ  Side-by-side UI.
- [x] Shared Gemini repair cache theo source/model/prompt/repair contract, cÃ³ lexical revalidation vÃ  cleanup dry-run.
- [x] Story Audio â†’ YouTube Auto Handoff V1 má»™t chÆ°Æ¡ng, manifest SHA-256, speech timing vÃ  character seed.
- [x] Three-Voice Profile Core: book profile, optional character override, gender-aware resolver vÃ  immutable job snapshot.
- [x] Three-Voice Profile UI and Casting Integration: profile/preview, default/custom character voice vÃ  effective resolution trong Manual Casting.
- [x] Book-level Character Bible Import Core: JSON schema V1, dry-run/apply, deterministic matching/conflict detection, idempotency, CLI/API and Doctor checks.
- [x] Gemini Speaker Assignment Draft Core: immutable draft, cache, strict candidates/confidence/alternatives vÃ  no auto-apply.
- [x] Speaker Assignment Review and Approval UI: filter/bulk review, alternatives/manual correction, effective voice preview, partial immutable approval, stale protection vÃ  idempotency.
- [x] Custom Reference Voice Storage & API: Schema v6, Global custom_voices, immutable revisions, content-addressed audio blob storage, and isolated offline API tests.

## Háº¡n cháº¿ hiá»‡n táº¡i

- Gemini vÃ  TTS cháº¡y tuáº§n tá»± trong má»™t orchestration worker; chÆ°a prefetch 2â€“5 chÆ°Æ¡ng.
- Shared Gemini cache váº«n cháº¡y tuáº§n tá»±; hai process cÃ³ thá»ƒ cÃ¹ng gá»i Gemini trÆ°á»›c khi atomic write cÃ¹ng má»™t key (káº¿t quáº£ cuá»‘i váº«n há»£p lá»‡).
- Cleanup cache hiá»‡n cÃ³ CLI dry-run/apply nhÆ°ng chÆ°a cÃ³ quota/dashboard UI; text blob khÃ´ng bá»‹ xÃ³a theo cache manifest.
- Text diff giá»›i háº¡n 500.000 kÃ½ tá»± káº¿t há»£p; payload trÃªn 50.000 kÃ½ tá»± cÃ³ warning vÃ  collapse máº·c Ä‘á»‹nh.
- Cleanup chÆ°a cÃ³ dry-run/quota dashboard trÃªn UI.
- Review/Approval chÆ°a cÃ³ undo cho Casting Plan Ä‘Ã£ approve; sá»­a quyáº¿t Ä‘á»‹nh báº±ng má»™t revision má»›i. Draft stale váº«n xem Ä‘Æ°á»£c Ä‘á»ƒ audit nhÆ°ng khÃ´ng approve Ä‘Æ°á»£c.
- Gender váº«n lÃ  dá»¯ liá»‡u manual; Gemini speaker draft khÃ´ng tá»± táº¡o/sá»­a character hoáº·c gender.
- Loudness giá»¯a preset cÃ³ chÃªnh nháº¹ (smoke Ä‘o tá»‘i Ä‘a 3,2 dB mean); chÆ°a normalization theo Ä‘Ãºng pháº¡m vi.
- Backup lÃ  full snapshot, chÆ°a incremental/compress vÃ  cÃ³ thá»ƒ lá»›n khi thÆ° viá»‡n tÄƒng.
- Restore remap artifact/work paths trong data root nhÆ°ng khÃ´ng Ä‘Ã³ng gÃ³i EPUB nguá»“n náº±m ngoÃ i `data/`.
- Recovery test dÃ¹ng fake TTS vÃ  startup state transition; chÆ°a cÃ³ OS-level kill-process harness.
- Story Audio khÃ´ng tá»± xÃ¢y image/video/metadata/thumbnail; cÃ¡c bÆ°á»›c nÃ y thuá»™c YouTube Auto qua handoff bundle.
- Handoff V1 chá»‰ há»— trá»£ má»™t chapter vÃ  segment-level timing; chÆ°a cÃ³ forced word alignment.
- Worker lÃ  má»™t thread trong API process; chÆ°a tÃ¡ch service/process riÃªng.

## Æ¯u tiÃªn tiáº¿p theo

### P0 â€” TrÆ°á»›c khi thÃªm tÃ­nh nÄƒng lá»›n

- [x] ThÃªm database schema version vÃ  migration runner.
- [x] ThÃªm backup/restore cÃ³ manifest vÃ  integrity verification.
- [x] ThÃªm integration tests cho restart, retry, cancel vÃ  artifact corruption.
- [x] ThÃªm job/chapter/segment diagnostic UI Ä‘á»ƒ ngÆ°á»i dÃ¹ng tháº¥y lá»—i cá»¥ thá»ƒ vÃ  retry an toÃ n.

### P1 â€” HoÃ n thiá»‡n Audio MVP

- [x] Voice preview 10â€“20 giÃ¢y.
- [x] Text diff raw â†’ reflowed â†’ repaired.
- [x] Gemini cache dÃ¹ng chung theo source hash + model + prompt version.

CÃ¡c háº¡ng má»¥c váº­n hÃ nh/quota vÃ  alignment khÃ´ng cáº¥p thiáº¿t Ä‘Æ°á»£c táº­p trung trong `ROADMAP.md` thay vÃ¬ láº·p backlog táº¡i Ä‘Ã¢y.

### P2 â€” Personal Edition voice

- [x] YouTube Auto Handoff V1.
- [x] Three-Voice Profile Core.
- [x] Three-Voice Profile UI and Casting Integration.
- [x] Book-level Character Bible Import.
- [x] Character Bible UI and Handoff Integration.
- [x] Gemini Speaker Assignment Draft Core.
- [x] Speaker Assignment Review and Approval UI.
- [x] Long-Chapter End-to-End Validation and Hardening.
  - [x] Phase 1: preflight, real long-chapter Gemini draft, review, partial/final approval.
  - [x] Phase 2: VieNeu render, recovery/retry, audio QA.
  - [x] Phase 3: Handoff export/import and downstream compatibility smoke.
- [x] Phase 2B2B: Custom Reference Voice Resolution and Assignment Validation (commit 64c7ea4949b4c5c37b01cc05bb2eddd686691066).
- [x] Phase 3A: Job/Casting Snapshot Pinning (Migration 0007).

## Quy táº¯c cáº­p nháº­t tiáº¿n Ä‘á»™

- Chá»‰ Ä‘Ã¡nh dáº¥u `[x]` sau khi cÃ³ test hoáº·c artifact xÃ¡c minh.
- Viá»‡c chÆ°a rÃµ pháº¡m vi Ä‘Æ°a vÃ o `ROADMAP.md`, khÃ´ng nhÃ©t vÃ o P0.
- Bug Ä‘ang áº£nh hÆ°á»Ÿng dá»¯ liá»‡u hoáº·c resume pháº£i náº±m trong Háº¡n cháº¿ hiá»‡n táº¡i.
- Quyáº¿t Ä‘á»‹nh thay Ä‘á»•i invariant pháº£i ghi thÃªm vÃ o `docs/DECISIONS.md`.
- Thay Ä‘á»•i phÃ¡t hÃ nh hoáº·c hÃ nh vi ngÆ°á»i dÃ¹ng pháº£i thÃªm vÃ o `CHANGELOG.md`.

## Nháº­t kÃ½ milestone

| NgÃ y | Milestone | Báº±ng chá»©ng |
|---|---|---|
| 2026-06-23 | Audio MVP Ä‘áº§u tiÃªn | Import 1.980 chÆ°Æ¡ng; job #1 completed |
| 2026-06-23 | Gemini contract smoke | Sá»­a punctuation, token nguá»“n Ä‘Æ°á»£c báº£o toÃ n |
| 2026-06-23 | Resume theo segment | Reuse 9/10 segment vÃ  chá»‰ táº¡o láº¡i segment lá»—i |
| 2026-06-23 | P0 hardening | Schema v1; backup/restore tháº­t vÃ  18 test offline Ä‘áº¡t |
| 2026-06-23 | M2 Diagnostic UI | Job/chapter/segment diagnostics; retry giá»¯ nguyÃªn verified segment; 23 test offline Ä‘áº¡t |
| 2026-06-23 | M2 Voice Preview | Preset preview cache theo voice/text/settings/engine; fake TTS; 28 test offline Ä‘áº¡t |
| 2026-06-23 | M2 Character Voice MVP | Schema v2; manual casting; multi-voice snapshot/segments/timeline; 38 test offline Ä‘áº¡t |
| 2026-06-23 | Three-Voice Profile Core | Schema v3; profile/override/resolver/snapshot; 73 test offline vÃ  Doctor deep Ä‘áº¡t |
| 2026-06-23 | Three-Voice UI + Casting | Profile/preview/default-custom/effective voice; jobs 4â€“5 real TTS; 78 test offline Ä‘áº¡t |
| 2026-06-23 | Multi-voice real-TTS smoke | Job 3; 3 voices; 8/8 segment; retry 1 segment vÃ  reuse 7; M4A 22.810 ms |
| 2026-06-23 | Text Revision Diff | Structured read-only API; Inline/Side-by-side; 50 tests; chapter 18.649 chars â‰ˆ330 ms live API |
| 2026-06-23 | Shared Gemini repair cache | Filesystem manifest + text blob; lexical revalidation; corrupt-as-miss; cleanup/doctor; 60 tests |
| 2026-06-23 | YouTube Auto Handoff V1 | Job 3/chapter 1982; 22.810s M4A; 8 timing items; 2 character seeds; imported/composed final 22.826s |
| 2026-06-24 | Character Bible Import Core | Schema v4; 92 offline tests; smoke book 5 dry-run/apply/apply-láº¡i; Doctor deep critical_errors=0 |
| 2026-06-24 | Character Bible UI + Handoff Integration | UI dry-run/apply + metadata editor; Handoff seed exports canonical metadata; 94 offline tests + JS syntax check |
| 2026-06-24 | Gemini Speaker Assignment Draft Core | Schema v5; 101 offline tests; real Gemini draft #1 + cache hit/reuse; Doctor deep critical_errors=0 |
| 2026-06-24 | Speaker Assignment Review and Approval UI | 119 offline tests; Draft #3, 15 utterance; partial plans #5â€“#6; exact approval repeat reused #6; no job/audio mutation |
| 2026-06-25 | Long-Chapter Validation Phase 1 | Chapter 56; Draft #4 101/101 valid; UI plans #7â€“#8; idempotent repeat reused #8; 40/40 accuracy smoke; no job/audio mutation |
| 2026-06-25 | Long-Chapter Validation Phase 2 | Job #6 from plan #8; 210/210 real VieNeu segments; M4A render_0002 752.310 s; retry segment #247 reused verified peers; Doctor/tests pass |
| 2026-06-25 | Long-Chapter Validation Phase 3 | Bundle identity `050ac2f2a73bda7b84beb7c1e9bd5b06d9fd3a00773214fa91616c451e8f9280`; export #2 reused identity; 752310 ms / 210 utterances / 2 characters; legacy bundles verify/import; Story Audio 119 tests / Doctor pass; YouTube Auto 96 tests pass |
| 2026-06-26 | Custom Voice Backend Core | Schema v6; global library, immutable revisions, content-addressed storage, FastAPI routes, and 28 isolated API tests |

| 2026-06-27 | Custom Reference Voice Resolution | voice_ref.py + CustomVoiceContext; casting/profile integration; 290 offline tests pass |
