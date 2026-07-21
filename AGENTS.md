# HÆ°á»›ng dáº«n lÃ m viá»‡c vá»›i repository

File nÃ y dÃ nh cho ká»¹ sÆ° vÃ  cÃ¡c phiÃªn Codex tiáº¿p theo. Má»¥c tiÃªu lÃ  giáº£m thá»i gian khÃ¡m phÃ¡ láº¡i dá»± Ã¡n, trÃ¡nh sá»­a sai invariant vÃ  khÃ´ng tiÃªu tá»‘n API ngoÃ i Ã½ muá»‘n.

## Thá»© tá»± Ä‘á»c

1. Verify Git/runtime state directly before trusting summaries.
2. `.ai/PROJECT.md` - compact stable project context.
3. `.ai/STATE.md` - compact current handoff state.
4. `.ai/DECISIONS.md` - continuity decisions for takeover.
5. `ROADMAP.md` - strategic direction and active milestone.
6. `PROJECT_STATUS.md` - concise last verified product/runtime state.
7. `NEXT_TASK.md` - one authorized next task.
8. Read relevant canonical docs such as `DOCUMENTATION_SOURCES.md`, `docs/DAILY_PRODUCTION_WORKFLOW.md`, `docs/DECISIONS.md`, `docs/DATA_MODEL.md`, `docs/RUNBOOK.md`, and `docs/TESTING.md`.
9. Read external ACTIVE_TASK capsule only after repository docs and real state have been checked.

## Báº£n Ä‘á»“ mÃ£ nguá»“n

```text
story_audio/api.py       HTTP API vÃ  lifecycle á»©ng dá»¥ng
story_audio/pipeline.py  Job orchestration, checkpoint, assemble/export
story_audio/epub.py      EPUB parser vÃ  import revision
story_audio/text.py      Reflow, QA, lexical validation, chunking
story_audio/gemini.py    Gemini punctuation repair contract
story_audio/gemini_cache.py Shared repair cache, integrity vÃ  manifest cleanup
story_audio/speaker_assignment.py Gemini speaker draft selection, validation, cache vÃ  persistence
story_audio/speaker_review.py Draft review detail, stale detection, immutable approval vÃ  idempotency
story_audio/youtube_handoff.py Immutable one-chapter handoff exporter/verifier for YouTube Auto
story_audio/tts.py       VieNeu adapter
story_audio/db.py        SQLite schema vÃ  connection policy
story_audio/storage.py   Content-addressed text blobs
story_audio/casting.py   Character, immutable casting plan vÃ  deterministic utterance
story_audio/voice_profile.py Book Voice Profile, override validation vÃ  deterministic resolver
story_audio/text_diff.py Read-only TextRevision block/token diff engine
story_audio/migrations/  Forward-only SQL migrations
story_audio/backup.py    Backup/verify/restore core
story_audio/integrity.py Shared integrity diagnostics
ui/                      UI HTML/CSS/JavaScript
tests/                   Offline unit tests
```

## Invariant báº¯t buá»™c

- KhÃ´ng lÆ°u full chapter text trong SQLite. Text náº±m trong `data/blobs/text/<prefix>/<sha>.txt`.
- Text revision vÃ  artifact Ä‘Ã£ verify lÃ  báº¥t biáº¿n; thay Ä‘á»•i táº¡o revision má»›i.
- Job pin text/config/voice snapshot; khÃ´ng Ä‘á»•i Ã¢m tháº§m giá»¯a lÃºc cháº¡y.
- Schema v5 cÃ³ Character Bible vÃ  immutable Speaker Assignment Draft; `default_voice_id` váº«n Ä‘Æ°á»£c giá»¯ lÃ m legacy compatibility field.
- Long-Chapter End-to-End Validation and Hardening Ä‘Ã£ hoÃ n táº¥t. Migration káº¿ tiáº¿p náº¿u tháº­t sá»± cáº§n pháº£i láº¥y sá»‘ sau migration cao nháº¥t hiá»‡n cÃ³ trong `story_audio/migrations/`; khÃ´ng sá»­a migration Ä‘Ã£ phÃ¡t hÃ nh.
- Character identity tÃ¡ch khá»i voice identity; khÃ´ng thiáº¿t káº¿ Character Bible theo giáº£ Ä‘á»‹nh má»—i nhÃ¢n váº­t cáº§n voice riÃªng.
- á»¨ng dá»¥ng sá»Ÿ há»¯u TTS segment, tá»‘i Ä‘a 256 kÃ½ tá»± vá»›i VieNeu v3 Turbo hiá»‡n táº¡i.
- Gemini chá»‰ sá»­a punctuation/whitespace. Sau sá»­a, token nguá»“n pháº£i Ä‘Æ°á»£c khÃ´i phá»¥c vÃ  lexical validator pháº£i Ä‘áº¡t.
- KhÃ´ng Ä‘Ã¡nh dáº¥u artifact hoÃ n táº¥t trÆ°á»›c khi file tá»“n táº¡i, hash Ä‘Æ°á»£c tÃ­nh vÃ  FFprobe verify.
- Retry pháº£i reuse Ä‘Æ¡n vá»‹ Ä‘Ã£ verify; khÃ´ng render láº¡i toÃ n chÆ°Æ¡ng náº¿u chá»‰ má»™t segment lá»—i.
- KhÃ´ng log, commit, tráº£ qua API hoáº·c lÆ°u DB API key.
- KhÃ´ng Ä‘á»ƒ test máº·c Ä‘á»‹nh gá»i Gemini, VieNeu inference hoáº·c dá»‹ch vá»¥ cÃ³ phÃ­.
- KhÃ´ng xÃ³a dá»¯ liá»‡u ngÆ°á»i dÃ¹ng, artifact hoáº·c revision khi chÆ°a cÃ³ yÃªu cáº§u rÃµ rÃ ng.

## Lá»‡nh chuáº©n

```powershell
# Unit tests offline
$env:PYTHONUTF8='1'
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' -m unittest discover -s tests -v

# Cháº©n Ä‘oÃ¡n read-only
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\doctor.py

# Backup / verify / restore
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\backup.py backups\my-backup
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup --verify-only
& 'D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe' scripts\restore.py backups\my-backup D:\restore\data

# Cháº¡y á»©ng dá»¥ng
.\run_app.ps1
```

## TrÆ°á»›c khi sá»­a schema

- Äá»c má»¥c P0 trong `PROJECT_STATUS.md`.
- KhÃ´ng chá»‰ sá»­a `SCHEMA` rá»“i giáº£ Ä‘á»‹nh DB cÅ© tá»± cáº­p nháº­t.
- Pháº£i thÃªm migration cÃ³ version vÃ  test upgrade tá»« DB fixture trÆ°á»›c Ä‘Ã³.
- Cáº­p nháº­t `docs/DATA_MODEL.md` vÃ  `CHANGELOG.md`.


## Live DB Protection (Post-Incident R1)

**Canonical production database:** `D:\Youtube\Story Trans And Audio\data\app.db`

**Fail-closed guard:** Bất kỳ test, script hoặc import sai cấu hình nào cũng không được phép initialize/migrate canonical live DB trừ khi production launcher đã opt-in rõ ràng.

### Guard rules

1. **Test mode** (`STORY_AUDIO_TESTING=1`): Luôn block canonical production DB path, ngay cả khi có `STORY_AUDIO_ALLOW_LIVE_DB=1`.
2. **Non-test mode + canonical path**: Chỉ cho phép initialize khi `STORY_AUDIO_ALLOW_LIVE_DB=1`.
3. **Temporary/non-production paths**: Hoạt động bình thường mà không cần allow-live flag.
4. **Guard timing**: Chạy trước mọi connection/migration/write operation.

### Test infrastructure

- `tests/base.py` cung cấp `IsolatedTestCase` với temp directory tự động và `STORY_AUDIO_TESTING=1`.
- Mọi test sử dụng `Database` phải:
  - Dùng temporary paths hoặc kế thừa `IsolatedTestCase`.
  - Set `STORY_AUDIO_TESTING=1` trong `setUp()`.
  - Restore environment trong `tearDown()`.
- Tuyệt đối không được chạm `data/app.db` trong test.

### Production launcher

`run_app.ps1` set `STORY_AUDIO_ALLOW_LIVE_DB=1` cho child process production app.

Không persist biến môi trường này ở user/machine scope.

### Khi thêm test mới

```python
import os
import tempfile
from pathlib import Path
from story_audio.db import Database

# Option 1: Inherit IsolatedTestCase
from tests.base import IsolatedTestCase

class MyTests(IsolatedTestCase):
    def test_something(self):
        db = Database(self.config.db_path)  # Auto-isolated
        db.initialize()

# Option 2: Manual setup
class MyTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._original_testing = os.environ.get("STORY_AUDIO_TESTING")
        os.environ["STORY_AUDIO_TESTING"] = "1"
        self.temp = tempfile.TemporaryDirectory()
        # Use temp paths...
    
    def tearDown(self):
        if self._original_testing is None:
            os.environ.pop("STORY_AUDIO_TESTING", None)
        else:
            os.environ["STORY_AUDIO_TESTING"] = self._original_testing
        self.temp.cleanup()
        super().tearDown()
```


## Definition of Done

- Unit tests offline Ä‘áº¡t.
- KhÃ´ng cÃ³ secret má»›i trong status/diff/log.
- Resume/retry khÃ´ng lÃ m máº¥t checkpoint.
- File má»›i cÃ³ owner rÃµ rÃ ng trong báº£n Ä‘á»“ mÃ£ nguá»“n hoáº·c tÃ i liá»‡u.
- `PROJECT_STATUS.md`, `CHANGELOG.md` vÃ  quyáº¿t Ä‘á»‹nh kiáº¿n trÃºc Ä‘Æ°á»£c cáº­p nháº­t náº¿u thay Ä‘á»•i hÃ nh vi.
- Smoke test cÃ³ phÃ­ chá»‰ cháº¡y khi ngÆ°á»i dÃ¹ng yÃªu cáº§u hoáº·c thay Ä‘á»•i trá»±c tiáº¿p Gemini/VieNeu pipeline.

