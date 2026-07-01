"""
Setup isolated runtime for Task 6 with dedicated disposable fixtures.

Creates completely independent jobs/chapters/segments that will not be
affected by cleanup_expired_segments() or interfere with production data.
"""
import json
import os
import shutil
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

# SET ENVIRONMENT BEFORE ANY story_audio IMPORTS
repo_root = Path("D:/Youtube/Story Trans And Audio")
runtime_root = repo_root / "runs" / "task6_isolated_runtime"
os.environ["STORY_AUDIO_DATA_DIR"] = str(runtime_root)
os.environ["STORY_AUDIO_TESTING"] = "1"

sys.path.insert(0, str(repo_root))

from story_audio.config import canonical_production_db_path
from story_audio.db import Database, utcnow
from story_audio.files import sha256_file, sha256_text
from story_audio.storage import ContentStore


def create_test_wav(path: Path, duration_ms: int = 1000) -> tuple[str, int]:
    """Create a minimal valid WAV file and return (sha256, actual_duration_ms)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 48000
    samples = (duration_ms * sample_rate) // 1000

    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b'\x00\x00' * samples)
    
    # Calculate actual duration from file
    with wave.open(str(path), 'rb') as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        actual_duration_ms = int((frames / rate) * 1000)
    
    return sha256_file(path), actual_duration_ms


def main():
    print(f"=== TASK 6: DEDICATED DISPOSABLE FIXTURES ===")
    print(f"Runtime root: {runtime_root}\n")
    
    # Clean and create fresh runtime
    if runtime_root.exists():
        print(f"Removing existing runtime...")
        shutil.rmtree(runtime_root)
    
    runtime_root.mkdir(parents=True)
    
    # Copy live database as baseline
    print("Copying live database...")
    shutil.copy2(canonical_production_db_path(), runtime_root / "app.db")
    
    # Copy blobs for text storage
    print("Copying content blobs...")
    live_blobs = repo_root / "data" / "blobs"
    if live_blobs.exists():
        shutil.copytree(live_blobs, runtime_root / "blobs")
    
    # Create directories
    (runtime_root / "output").mkdir()
    (runtime_root / "work").mkdir()
    (runtime_root / "cache" / "previews").mkdir(parents=True)
    (runtime_root / "cache" / "gemini_repairs").mkdir(parents=True)
    (runtime_root / "exports" / "youtube_auto").mkdir(parents=True)
    
    # Initialize database
    from story_audio.config import Settings
    config = Settings()
    db = Database(config.db_path)
    db.initialize()
    store = ContentStore(config)
    
    now = utcnow()
    
    # Find a book to attach fixtures to
    book = db.fetch_one("SELECT id, title FROM books LIMIT 1")
    if not book:
        print("ERROR: No books found in database")
        return 1
    
    book_id = book["id"]
    print(f"Using Book {book_id}: {book['title']}\n")
    
    fixtures = []
    
    for idx, fixture_type in enumerate(["ACCEPT", "REJECT"]):
        print(f"[{fixture_type} FIXTURE]")
        
        chapter_num = 9998 + idx  # 9998 for ACCEPT, 9999 for REJECT
        
        # 1. Create dedicated disposable job
        settings = {
            "tts_mode": "v3turbo",
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "target_chars": 230,
            "silence_seconds": 0.15,
            "gemini_model": "gemini-2.5-flash",
            "gemini_prompt_version": "punctuation-v1"
        }
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO jobs(
                    book_id, from_chapter, to_chapter, voice_name, repair_mode, 
                    output_format, settings_json, skip_completed, status, 
                    total_chapters, scheduled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (book_id, chapter_num, chapter_num, "preset_voice", "none", "m4a", 
                 json.dumps(settings), 1, "scheduled", 1, now, now, now)
            )
            job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"  Created Job {job_id}")
        
        # 2. Create dedicated disposable chapter
        chapter_title = f"Task 6 {fixture_type} Test Fixture"
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO chapters(
                    book_id, chapter_number, title, char_count, audio_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (book_id, chapter_num, chapter_title, 100, "pending", now, now)
            )
            chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"  Created Chapter {chapter_id}: {chapter_title}")
        
        # 3. Create text revision
        text_content = f"This is the Task 6 {fixture_type} test fixture for manual UI validation."
        text_path, text_sha = store.put_text(text_content)
        
        # Calculate lexical SHA (just the text without whitespace/punctuation changes)
        from story_audio.text import lexical_sha256
        text_lexical_sha = lexical_sha256(text_content)
        
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO text_revisions(
                    chapter_id, kind, content_path, content_sha256,
                    lexical_sha256, char_count, processor_version, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (chapter_id, "import", text_path, text_sha, text_lexical_sha,
                 len(text_content), "manual_v1", "approved", now)
            )
            text_revision_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"  Created Text Revision {text_revision_id}")
        
        # 4. Create job_chapter (NOT finished, so cleanup won't touch it)
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO job_chapters(
                    job_id, chapter_id, text_revision_id, sequence, status
                ) VALUES (?, ?, ?, ?, ?)""",
                (job_id, chapter_id, text_revision_id, 1, "completed")
            )
            job_chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"  Created Job Chapter {job_chapter_id} (status=completed, finished_at=NULL)")
        
        # 5. Create work directory
        work_dir = config.work_dir / f"job_{job_id}" / "chapter_9999" / "segments"
        work_dir.mkdir(parents=True, exist_ok=True)
        
        # 6. Create single verified segment with Active and Candidate
        segment_text = f"Task 6 {fixture_type} fixture segment."
        segment_text_path, segment_text_sha = store.put_text(segment_text)
        
        synthesis_settings = {
            "temperature": 0.8,
            "top_k": 25,
            "max_chars": 256,
            "silence_seconds": 0.15,
            "engine_version": "vieneu:v3turbo"
        }
        synthesis_json = json.dumps(synthesis_settings, sort_keys=True)
        synthesis_hash = sha256_text(synthesis_json + segment_text + "preset_voice")
        
        # Insert segment first to get ID
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO segments(
                    job_chapter_id, segment_index, text_path, text_sha256, status,
                    wav_path, audio_sha256, duration_ms, verified_at, created_at,
                    voice_snapshot_version, voice_source_type, voice_provider, voice_model,
                    logical_voice_ref, effective_voice_ref, synthesis_settings_json,
                    voice_resolution_reason, synthesis_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_chapter_id, 1, segment_text_path, segment_text_sha, "verified",
                    None, None, None, now, now,
                    1, "preset", "vieneu", "v3turbo",
                    "narrator", "preset_voice", synthesis_json,
                    "direct", synthesis_hash
                )
            )
            segment_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"  Created Segment {segment_id}")
        
        # Create Active Attempt 1 WAV
        active_wav_path = work_dir / f"segment_{segment_id}_attempt_1.wav"
        active_hash, active_duration = create_test_wav(active_wav_path, 2000)
        
        # Create Candidate Attempt 2 WAV
        candidate_wav_path = work_dir / f"segment_{segment_id}_attempt_2.wav"
        candidate_hash, candidate_duration = create_test_wav(candidate_wav_path, 2200)
        
        print(f"  Created WAV files:")
        print(f"    Active: {active_wav_path.name} ({active_duration}ms)")
        print(f"    Candidate: {candidate_wav_path.name} ({candidate_duration}ms)")
        
        # Update segment with Active metadata
        with db.connect() as conn:
            conn.execute(
                """UPDATE segments 
                   SET wav_path=?, audio_sha256=?, duration_ms=?
                   WHERE id=?""",
                (str(active_wav_path), active_hash, active_duration, segment_id)
            )
        
        # Insert segment attempts
        with db.connect() as conn:
            # Active Attempt 1
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id, attempt_number, status, wav_path, audio_sha256, duration_ms,
                    created_at, accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (segment_id, 1, "active", str(active_wav_path), active_hash, active_duration, now, now)
            )
            active_attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Candidate Attempt 2
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id, attempt_number, status, wav_path, audio_sha256, duration_ms,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (segment_id, 2, "candidate", str(candidate_wav_path), candidate_hash, candidate_duration, now)
            )
            candidate_attempt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        print(f"  Created Attempts: Active={active_attempt_id}, Candidate={candidate_attempt_id}")
        
        fixtures.append({
            "type": fixture_type,
            "job_id": job_id,
            "chapter_id": chapter_id,
            "job_chapter_id": job_chapter_id,
            "segment_id": segment_id,
            "active_attempt_id": active_attempt_id,
            "candidate_attempt_id": candidate_attempt_id,
        })
        print()
    
    # WAL checkpoint
    print("[WAL CHECKPOINT]")
    with db.connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print("  Completed\n")
    
    print("=== SETUP COMPLETE ===\n")
    print("Fixtures created:")
    for fix in fixtures:
        print(f"{fix['type']} Fixture:")
        print(f"  Job: {fix['job_id']}")
        print(f"  Chapter: {fix['chapter_id']}")
        print(f"  Segment: {fix['segment_id']}")
        print(f"  Active Attempt: {fix['active_attempt_id']}")
        print(f"  Candidate Attempt: {fix['candidate_attempt_id']}")
        print()
    
    print(f"Start server:")
    print(f"  $env:STORY_AUDIO_DATA_DIR='{runtime_root}'; $env:STORY_AUDIO_ALLOW_LIVE_DB='1'; .\\run_app.ps1 --port 8767 --no-browser\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
