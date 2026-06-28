"""
Smoke test for Custom Voice rendering.
Creates a minimal smoke chapter and renders it with Custom Voices.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.casting import approve_plan, create_casting_draft, create_character, split_utterances
from story_audio.config import settings
from story_audio.custom_voice import CustomVoiceRepository
from story_audio.db import Database, utcnow
from story_audio.files import sha256_text
from story_audio.pipeline import PipelineWorker, create_job
from story_audio.storage import ContentStore
from story_audio.tts import tts_service
from story_audio.voice_ref import CustomVoiceContext


SMOKE_TEXT = (
    "Trời vừa sáng, người dẫn chuyện bước vào căn phòng nhỏ. "
    '"Chào anh, tôi đã đợi từ sớm." '
    "An đặt chiếc túi xuống bàn rồi nhìn ra cửa sổ. "
    '"Tôi xin lỗi, đường hôm nay đông hơn mọi khi."'
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live-db", action="store_true", help="Opt-in to use the canonical live DB")
    parser.add_argument("--narrator-custom-voice-id", type=int, required=True, help="Custom voice ID for narrator")
    parser.add_argument("--dialogue-custom-voice-id", type=int, required=True, help="Custom voice ID for dialogue")
    args = parser.parse_args()

    if getattr(args, "allow_live_db", False):
        import os
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
    
    settings.ensure_dirs()
    db = Database(settings.db_path)
    store = ContentStore(settings)
    repo = CustomVoiceRepository(db, store)
    db.initialize()
    
    # Build custom voice context
    custom_context = CustomVoiceContext.from_repository(repo)
    
    # Verify custom voices exist and are active
    narrator_ref = f"custom:{args.narrator_custom_voice_id}"
    dialogue_ref = f"custom:{args.dialogue_custom_voice_id}"
    
    if not custom_context.is_available(narrator_ref):
        raise RuntimeError(f"Narrator custom voice {narrator_ref} is not available")
    if not custom_context.is_available(dialogue_ref):
        raise RuntimeError(f"Dialogue custom voice {dialogue_ref} is not available")
    
    print(f"Using Custom Voices:")
    print(f"  Narrator: {narrator_ref}")
    print(f"  Dialogue: {dialogue_ref}")
    
    # Create smoke book and chapter
    run_key = uuid.uuid4().hex[:10]
    now = utcnow()
    content_path, content_sha = store.put_text(SMOKE_TEXT)
    source_sha = sha256_text(f"custom-voice-smoke:{run_key}:{content_sha}")
    
    with db.transaction() as connection:
        book_id = int(connection.execute(
            "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (f"Custom Voice Smoke {run_key}", f"smoke://custom-voice/{run_key}", source_sha, 1, now, now),
        ).lastrowid)
        chapter_id = int(connection.execute(
            "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (book_id, 1, "Custom Voice Smoke Chapter", len(SMOKE_TEXT), now, now),
        ).lastrowid)
        revision_id = int(connection.execute(
            """INSERT INTO text_revisions(
                chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                processor_version,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (chapter_id, "reflowed", content_path, content_sha, "smoke", len(SMOKE_TEXT), "smoke-v1", "approved", now),
        ).lastrowid)
        connection.execute(
            "UPDATE chapters SET raw_text_revision_id=?,active_text_revision_id=? WHERE id=?",
            (revision_id, revision_id, chapter_id),
        )
    
    print(f"\nCreated smoke book {book_id}, chapter {chapter_id}, text revision {revision_id}")
    
    # Create character with custom voice
    character = create_character(db, book_id, "Smoke Character An", dialogue_ref)
    print(f"Created character {character['id']} with voice {dialogue_ref}")
    
    # Split into utterances
    utterances = split_utterances(SMOKE_TEXT, maximum=settings.tts_max_chars)
    print(f"\nSplit into {len(utterances)} utterances")
    
    # Assign voices: utterance 2 to character (dialogue), rest to narrator
    assignments = []
    for utterance in utterances:
        if utterance["sequence"] == 2:
            assignments.append({
                "utterance_id": utterance["utterance_id"],
                "role": "character",
                "character_id": character["id"]
            })
            print(f"  Utterance {utterance['sequence']}: character (Custom Voice {dialogue_ref})")
        else:
            assignments.append({
                "utterance_id": utterance["utterance_id"],
                "role": "narrator",
                "character_id": None
            })
            print(f"  Utterance {utterance['sequence']}: narrator (Custom Voice {narrator_ref})")
    
    # Create casting draft with custom voices
    voices = tts_service.voices()
    allowed_voice_ids = {v["id"] for v in voices}
    
    draft = create_casting_draft(
        db,
        store,
        chapter_id=chapter_id,
        text_revision_id=revision_id,
        narrator_voice_id=narrator_ref,
        assignments=assignments,
        allowed_voice_ids=allowed_voice_ids,
        custom_voice_context=custom_context,
        maximum=settings.tts_max_chars,
    )
    print(f"\nCreated casting draft {draft['id']}")
    
    # Approve casting plan
    plan = approve_plan(db, store, draft["id"])
    print(f"Approved casting plan {plan['id']}")
    
    # Create job
    job_result = create_job(
        db,
        settings,
        book_id=book_id,
        from_chapter=1,
        to_chapter=1,
        voice_name="custom_smoke",
        repair_mode="off",
        output_format="m4a",
        skip_completed=False,
        casting_plan_id=plan["id"],
        store=store,
    )
    job_id = job_result["job_id"]
    print(f"\nCreated job {job_id}")
    
    # Run the job
    job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
    worker = PipelineWorker(db, store, tts_service, settings)
    
    print("\nStarting VieNeu synthesis...")
    started = time.monotonic()
    worker._run_job(job)
    elapsed = round(time.monotonic() - started, 2)
    
    # Check result
    job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
    print(f"\nJob completed in {elapsed}s")
    print(f"Status: {job['status']}")
    
    if job["status"] != "completed":
        print(f"ERROR: {job['error_message']}")
        return 1
    
    # Get final artifacts
    job_chapter = dict(db.fetch_one("SELECT * FROM job_chapters WHERE job_id=?", (job_id,)))
    artifacts = [dict(row) for row in db.fetch_all(
        "SELECT * FROM artifacts WHERE job_chapter_id=? AND status='active' ORDER BY id",
        (job_chapter["id"],)
    )]
    
    if artifacts:
        final_artifact = artifacts[-1]
        print(f"\nFinal audio: {final_artifact['path']}")
        print(f"Format: {final_artifact['artifact_type']}")
        print(f"Duration: {final_artifact['duration_ms']}ms")
        print(f"Size: {final_artifact['size_bytes']} bytes")
    
    # Get segments
    segments = [dict(row) for row in db.fetch_all(
        "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index",
        (job_chapter["id"],)
    )]
    print(f"\nSegments: {len(segments)}")
    for seg in segments:
        print(f"  Segment {seg['segment_index']}: {seg['status']}, {seg['duration_ms']}ms")
    
    report = {
        "run_key": run_key,
        "book_id": book_id,
        "chapter_id": chapter_id,
        "text_revision_id": revision_id,
        "casting_plan_id": plan["id"],
        "job_id": job_id,
        "narrator_voice": narrator_ref,
        "dialogue_voice": dialogue_ref,
        "elapsed_seconds": elapsed,
        "segment_count": len(segments),
        "final_audio": final_artifact["path"] if artifacts else None,
    }
    
    report_path = settings.data_dir / "smoke_reports" / f"custom-voice-{run_key}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\nReport saved: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
