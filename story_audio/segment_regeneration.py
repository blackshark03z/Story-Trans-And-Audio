"""
Segment Regeneration — Allow users to regenerate verified segments with A/B comparison.

Provides isolated segment re-synthesis without re-running entire jobs:
- Generate candidate using immutable segment snapshot
- Listen to original (active) and candidate side-by-side
- Accept candidate (rebuilds chapter artifacts) or Reject (keeps original)

Preserves full attempt history for audit and rollback.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, utcnow
from .files import safe_slug, sha256_file, sha256_text, atomic_write_json
from .storage import ContentStore
from .synthesis_snapshot import load_segment_synthesis_input
from .tts import TtsService


class RegenerationError(RuntimeError):
    """Base error for segment regeneration failures."""


class RegenerationValidationError(RegenerationError):
    """Raised when regeneration preconditions are not met."""


class RegenerationRebuildError(RegenerationError):
    """Raised when chapter rebuild fails after candidate synthesis."""


def _ensure_job_idle(job_status: str) -> None:
    """Validate job is not actively running."""
    if job_status in ('running', 'repairing', 'synthesizing', 'assembling'):
        raise RegenerationValidationError(
            f"Cannot regenerate while job is {job_status}. Pause or wait for completion."
        )


def _get_next_attempt_number(db: Database, segment_id: int) -> int:
    """Allocate next attempt number transactionally."""
    row = db.fetch_one(
        "SELECT MAX(attempt_number) as max_attempt FROM segment_attempts WHERE segment_id=?",
        (segment_id,)
    )
    return int(row["max_attempt"] or 0) + 1


def regenerate_verified_segment(
    db: Database,
    store: ContentStore,
    tts: TtsService,
    config: Settings,
    segment_id: int,
) -> dict[str, Any]:
    """
    Generate a new candidate synthesis for a verified segment.
    
    Uses the segment's immutable snapshot (text, voice, revision, settings).
    Does not modify the active segment or chapter artifacts.
    
    On first regeneration, transactionally seeds the existing verified output
    as active Attempt 1, then creates candidate as Attempt 2.
    
    Args:
        db: Database connection
        store: Content store
        tts: TTS service
        config: Settings
        segment_id: Segment to regenerate
    
    Returns:
        Dict with attempt_id, attempt_number, duration_ms
    
    Raises:
        RegenerationValidationError: If segment cannot be regenerated
    """
    # 1. Validate segment exists and is verified
    segment = db.fetch_one(
        """SELECT s.*, jc.job_id, jc.chapter_id, j.status as job_status,
                  c.chapter_number, c.book_id, b.title as book_title
           FROM segments s
           JOIN job_chapters jc ON jc.id = s.job_chapter_id
           JOIN jobs j ON j.id = jc.job_id
           JOIN chapters c ON c.id = jc.chapter_id
           JOIN books b ON b.id = c.book_id
           WHERE s.id = ?""",
        (segment_id,)
    )
    
    if not segment:
        raise RegenerationValidationError(f"Segment {segment_id} not found")
    
    if segment["status"] != "verified":
        raise RegenerationValidationError(
            f"Segment {segment_id} has status '{segment['status']}'. "
            "Only verified segments can be regenerated. "
            "Use /api/segments/{id}/retry for failed segments."
        )
    
    _ensure_job_idle(segment["job_status"])
    
    # 2. Check for existing candidate
    existing_candidate = db.fetch_one(
        "SELECT id FROM segment_attempts WHERE segment_id=? AND status='candidate'",
        (segment_id,)
    )
    if existing_candidate:
        raise RegenerationValidationError(
            f"Segment {segment_id} already has a pending candidate. "
            "Accept or reject it before generating a new one."
        )
    
    # 3. On first regeneration, seed existing verified output as active Attempt 1
    now = utcnow()
    with db.transaction() as conn:
        existing_active = conn.execute(
            "SELECT id FROM segment_attempts WHERE segment_id=? AND status='active'",
            (segment_id,)
        ).fetchone()
        
        if not existing_active:
            # Seed current segment output as active attempt
            if not segment["wav_path"]:
                raise RegenerationValidationError(
                    f"Segment {segment_id} has no verified audio (wav_path is NULL)"
                )
            
            conn.execute(
                """INSERT INTO segment_attempts(
                    segment_id, attempt_number, status, wav_path, audio_sha256,
                    duration_ms, created_at, accepted_at
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    segment_id, 1, 'active', segment["wav_path"],
                    segment["audio_sha256"], segment["duration_ms"], now, now
                )
            )
        
        # 4. Allocate attempt number for candidate
        row = conn.execute(
            "SELECT MAX(attempt_number) as max_attempt FROM segment_attempts WHERE segment_id=?",
            (segment_id,)
        ).fetchone()
        candidate_attempt_number = int(row["max_attempt"] or 0) + 1
    
    # 5. Load immutable snapshot
    try:
        # Determine if final segment (needed for silence calculation)
        total_segments = int(db.fetch_one(
            "SELECT COUNT(*) as count FROM segments WHERE job_chapter_id=?",
            (segment["job_chapter_id"],)
        )["count"])
        is_final = (segment["segment_index"] == total_segments)
        
        synth_input = load_segment_synthesis_input(
            dict(segment),
            store,
            is_final_segment=is_final
        )
    except Exception as exc:
        raise RegenerationValidationError(
            f"Cannot load segment snapshot: {exc}"
        ) from exc
    
    # 6. Determine output path
    job_id = segment["job_id"]
    chapter_num = segment["chapter_number"]
    work_dir = config.work_dir / f"job_{job_id}" / f"chapter_{chapter_num:04d}" / "segments"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    candidate_path = work_dir / f"segment_{segment_id}_attempt_{candidate_attempt_number}.wav"
    
    # 7. Synthesize candidate
    try:
        duration_ms, _sample_rate = tts.synthesize(
            synth_input=synth_input,
            output_path=candidate_path
        )
        audio_hash = sha256_file(candidate_path)
    except Exception as exc:
        candidate_path.unlink(missing_ok=True)
        raise RegenerationError(f"Synthesis failed: {exc}") from exc
    
    # 8. Insert candidate attempt record
    with db.connect() as conn:
        cursor = conn.execute(
            """INSERT INTO segment_attempts(
                segment_id, attempt_number, status, wav_path, audio_sha256,
                duration_ms, created_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                segment_id, candidate_attempt_number, 'candidate', str(candidate_path),
                audio_hash, duration_ms, now
            )
        )
        attempt_id = cursor.lastrowid
    
    db.audit(
        "segment_candidate_generated",
        job_id=job_id,
        chapter_id=segment["chapter_id"],
        details={
            "segment_id": segment_id,
            "attempt_id": attempt_id,
            "attempt_number": candidate_attempt_number,
            "duration_ms": duration_ms,
            "active_seeded": not existing_active
        }
    )
    
    return {
        "segment_id": segment_id,
        "attempt_id": attempt_id,
        "attempt_number": candidate_attempt_number,
        "duration_ms": duration_ms
    }


def _ffprobe_duration_ms(path: Path) -> int:
    """Get audio duration in milliseconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    value = float(result.stdout.strip())
    if value <= 0:
        raise ValueError(f"Invalid duration: {path}")
    return int(round(value * 1000))


def _reassemble_chapter_with_candidate(
    db: Database,
    store: ContentStore,
    config: Settings,
    segment_id: int,
    candidate_path: Path,
    candidate_duration_ms: int
) -> dict[str, Any]:
    """
    Build temporary chapter artifacts with candidate segment.
    
    Returns paths to temporary artifacts without modifying database.
    Caller must validate success before promoting to active.
    """
    # Get segment context
    segment = db.fetch_one(
        """SELECT s.*, jc.job_id, jc.chapter_id, jc.text_revision_id,
                  c.chapter_number, c.book_id, b.title as book_title,
                  j.voice_name, j.settings_json, j.output_format
           FROM segments s
           JOIN job_chapters jc ON jc.id = s.job_chapter_id
           JOIN jobs j ON j.id = jc.job_id
           JOIN chapters c ON c.id = jc.chapter_id
           JOIN books b ON b.id = c.book_id
           WHERE s.id = ?""",
        (segment_id,)
    )
    
    job_id = segment["job_id"]
    job_chapter_id = segment["job_chapter_id"]
    chapter_id = segment["chapter_id"]
    chapter_num = segment["chapter_number"]
    book_id = segment["book_id"]
    book_title = segment["book_title"]
    
    # Get all segments with candidate override
    segments = db.fetch_all(
        """SELECT s.*, ch.display_name AS character_name
           FROM segments s
           LEFT JOIN characters ch ON ch.id = s.character_id
           WHERE s.job_chapter_id = ?
           ORDER BY s.segment_index""",
        (job_chapter_id,)
    )
    
    if not segments:
        raise RegenerationRebuildError("No segments found for chapter")
    
    # Build segment list with candidate override
    segment_wavs = []
    for seg in segments:
        if seg["id"] == segment_id:
            # Use candidate
            segment_wavs.append({
                "path": candidate_path,
                "duration_ms": candidate_duration_ms,
                "segment": seg
            })
        else:
            # Use active
            if seg["status"] != "verified" or not seg["wav_path"]:
                raise RegenerationRebuildError(
                    f"Segment {seg['id']} (index {seg['segment_index']}) not verified"
                )
            segment_wavs.append({
                "path": Path(seg["wav_path"]),
                "duration_ms": seg["duration_ms"],
                "segment": seg
            })
    
    # Create temporary output directory
    temp_dir = (
        config.work_dir / f"job_{job_id}" / f"chapter_{chapter_num:04d}" / 
        f"rebuild_candidate_{segment_id}"
    )
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Build concat file
    concat_path = temp_dir / "concat.txt"
    concat_lines = [
        f"file '{str(item['path'].resolve()).replace(chr(92), '/')}'"
        for item in segment_wavs
    ]
    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    
    # Concatenate to master WAV
    master_wav = temp_dir / "chapter_master.wav"
    master_partial = temp_dir / "chapter_master.partial.wav"
    
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat_path), "-c:a", "pcm_s16le", str(master_partial)
            ],
            check=True,
            capture_output=True,
            text=True
        )
        master_duration_ms = _ffprobe_duration_ms(master_partial)
        master_partial.replace(master_wav)
    except subprocess.CalledProcessError as exc:
        raise RegenerationRebuildError(f"FFmpeg concat failed: {exc.stderr}") from exc
    
    # Build timeline
    timeline_items = []
    cursor_ms = 0
    
    for item in segment_wavs:
        seg = item["segment"]
        duration = item["duration_ms"]
        
        timeline_items.append({
            "index": int(seg["segment_index"]),
            "text": store.read_text(seg["text_path"]),
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + duration,
            "duration_ms": duration,
            "segment_sha256": seg["audio_sha256"] if seg["id"] != segment_id else sha256_file(candidate_path),
            "utterance_sequence": seg["utterance_sequence"],
            "speaker_role": seg["speaker_role"] or "narrator",
            "character_id": seg["character_id"],
            "character_name": seg["character_name"],
            "voice_id": seg["resolved_voice_id"] or segment["voice_name"],
            "synthesis_hash": seg["synthesis_hash"]
        })
        cursor_ms += duration
    
    timeline_path = temp_dir / "segment_timeline.json"
    atomic_write_json(
        timeline_path,
        {
            "schema_version": 2,
            "chapter_id": chapter_id,
            "text_revision_id": segment["text_revision_id"],
            "sample_rate": config.tts_sample_rate,
            "duration_ms": master_duration_ms,
            "items": timeline_items
        }
    )
    
    # Encode final format if needed
    output_format = segment["output_format"]
    if output_format in ("m4a", "mp3"):
        final_path = temp_dir / f"chapter_final.{output_format}"
        final_partial = temp_dir / f"chapter_final.partial.{output_format}"
        
        if output_format == "m4a":
            codec_args = ["-c:a", "aac", "-b:a", "128k"]
        else:  # mp3
            codec_args = ["-c:a", "libmp3lame", "-b:a", "128k"]
        
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", str(master_wav),
                    *codec_args, str(final_partial)
                ],
                check=True,
                capture_output=True,
                text=True
            )
            final_partial.replace(final_path)
        except subprocess.CalledProcessError as exc:
            raise RegenerationRebuildError(f"FFmpeg encode failed: {exc.stderr}") from exc
    else:
        final_path = master_wav
    
    return {
        "master_wav": master_wav,
        "master_duration_ms": master_duration_ms,
        "timeline_json": timeline_path,
        "final_path": final_path,
        "temp_dir": temp_dir
    }


def accept_segment_candidate(
    db: Database,
    store: ContentStore,
    config: Settings,
    segment_id: int,
    attempt_id: int
) -> dict[str, Any]:
    """
    Accept candidate and promote to active.
    
    Rebuilds chapter artifacts with candidate, then atomically:
    - Marks old active as 'superseded'
    - Marks candidate as 'active'
    - Updates segment active pointers
    - Updates chapter artifact pointer
    
    If rebuild fails, leaves everything unchanged and candidate available for retry.
    
    Args:
        db: Database
        store: Content store
        config: Settings
        segment_id: Segment ID
        attempt_id: Candidate attempt ID
    
    Returns:
        Dict with segment_id, attempt_id, new_artifact_id, chapter_duration_ms
    
    Raises:
        RegenerationValidationError: Validation failed
        RegenerationRebuildError: Rebuild failed (candidate still available)
    """
    # 1. Validate
    segment = db.fetch_one(
        """SELECT s.*, jc.job_id, jc.chapter_id, j.status as job_status
           FROM segments s
           JOIN job_chapters jc ON jc.id = s.job_chapter_id
           JOIN jobs j ON j.id = jc.job_id
           WHERE s.id = ?""",
        (segment_id,)
    )
    
    if not segment:
        raise RegenerationValidationError(f"Segment {segment_id} not found")
    
    _ensure_job_idle(segment["job_status"])
    
    attempt = db.fetch_one(
        "SELECT * FROM segment_attempts WHERE id=? AND segment_id=?",
        (attempt_id, segment_id)
    )
    
    if not attempt:
        raise RegenerationValidationError(
            f"Attempt {attempt_id} not found for segment {segment_id}"
        )
    
    if attempt["status"] != "candidate":
        raise RegenerationValidationError(
            f"Attempt {attempt_id} has status '{attempt['status']}', expected 'candidate'"
        )
    
    candidate_path = Path(attempt["wav_path"])
    if not candidate_path.exists():
        raise RegenerationValidationError(
            f"Candidate WAV not found: {candidate_path}"
        )
    
    # 2. Rebuild chapter with candidate (failure-safe)
    try:
        rebuild_result = _reassemble_chapter_with_candidate(
            db, store, config, segment_id, candidate_path, attempt["duration_ms"]
        )
    except Exception as exc:
        # Rebuild failed - candidate remains available
        raise RegenerationRebuildError(
            f"Chapter rebuild failed: {exc}. Candidate preserved for retry."
        ) from exc
    
    # 3. Create permanent artifacts and promote atomically
    chapter = db.fetch_one("SELECT * FROM chapters WHERE id=?", (segment["chapter_id"],))
    job_chapter = db.fetch_one("SELECT * FROM job_chapters WHERE id=?", (segment["job_chapter_id"],))
    book = db.fetch_one("SELECT * FROM books WHERE id=?", (chapter["book_id"],))
    
    job_id = segment["job_id"]
    chapter_num = chapter["chapter_number"]
    
    # Create permanent output directory
    output_dir = (
        config.output_dir /
        f"{book['id']}-{safe_slug(book['title'], 'book')}" /
        f"chapter_{chapter_num:04d}" /
        f"job_{job_id}"
    )
    
    # Count previous renders
    previous_renders = int(db.fetch_one(
        "SELECT COUNT(*) as count FROM artifacts WHERE job_chapter_id=? AND artifact_type='chapter_master_wav'",
        (job_chapter["id"],)
    )["count"])
    
    render_dir = output_dir / f"render_{previous_renders + 1:04d}"
    render_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy artifacts to permanent location
    import shutil
    master_final = render_dir / "chapter_master.wav"
    timeline_final = render_dir / "segment_timeline.json"
    
    shutil.copy2(rebuild_result["master_wav"], master_final)
    shutil.copy2(rebuild_result["timeline_json"], timeline_final)
    
    # Copy final format if different
    if rebuild_result["final_path"] != rebuild_result["master_wav"]:
        final_format_path = render_dir / rebuild_result["final_path"].name
        shutil.copy2(rebuild_result["final_path"], final_format_path)
    else:
        final_format_path = master_final
    
    # Build synthesis hash
    settings = json.loads(db.fetch_one("SELECT settings_json FROM jobs WHERE id=?", (job_id,))["settings_json"])
    synthesis_hash = sha256_text(json.dumps({
        "text_revision_id": job_chapter["text_revision_id"],
        "voice": db.fetch_one("SELECT voice_name FROM jobs WHERE id=?", (job_id,))["voice_name"],
        "settings": settings
    }, sort_keys=True, ensure_ascii=False))
    
    # Single transaction: promote candidate, create artifacts, update pointers
    now = utcnow()
    with db.transaction() as conn:
        # Mark old active as superseded
        conn.execute(
            """UPDATE segment_attempts
               SET status='superseded', superseded_at=?
               WHERE segment_id=? AND status='active'""",
            (now, segment_id)
        )
        
        # Promote candidate to active
        conn.execute(
            """UPDATE segment_attempts
               SET status='active', accepted_at=?
               WHERE id=?""",
            (now, attempt_id)
        )
        
        # Update segment active pointers
        conn.execute(
            """UPDATE segments
               SET wav_path=?, audio_sha256=?, duration_ms=?
               WHERE id=?""",
            (str(candidate_path), attempt["audio_sha256"], attempt["duration_ms"], segment_id)
        )
        
        # Insert master WAV artifact
        cursor = conn.execute(
            """INSERT INTO artifacts(
                chapter_id, job_chapter_id, text_revision_id, artifact_type,
                synthesis_hash, path, sha256, size_bytes, duration_ms,
                status, created_at, verified_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chapter["id"], job_chapter["id"], job_chapter["text_revision_id"],
                "chapter_master_wav", synthesis_hash, str(master_final),
                sha256_file(master_final), master_final.stat().st_size,
                rebuild_result["master_duration_ms"], "verified", now, now
            )
        )
        master_artifact_id = cursor.lastrowid
        
        # Insert timeline artifact
        conn.execute(
            """INSERT INTO artifacts(
                chapter_id, job_chapter_id, text_revision_id, artifact_type,
                synthesis_hash, path, sha256, size_bytes, duration_ms,
                status, created_at, verified_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chapter["id"], job_chapter["id"], job_chapter["text_revision_id"],
                "segment_timeline_json", synthesis_hash, str(timeline_final),
                sha256_file(timeline_final), timeline_final.stat().st_size,
                rebuild_result["master_duration_ms"], "verified", now, now
            )
        )
        
        # Insert final format artifact
        output_format = db.fetch_one("SELECT output_format FROM jobs WHERE id=?", (job_id,))["output_format"]
        export_hash = sha256_text(json.dumps({
            "source_artifact_id": master_artifact_id,
            "format": output_format
        }, sort_keys=True))
        
        cursor = conn.execute(
            """INSERT INTO artifacts(
                chapter_id, job_chapter_id, text_revision_id, artifact_type,
                synthesis_hash, export_hash, path, sha256, size_bytes, duration_ms,
                status, created_at, verified_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chapter["id"], job_chapter["id"], job_chapter["text_revision_id"],
                f"chapter_final_{output_format}", synthesis_hash, export_hash,
                str(final_format_path), sha256_file(final_format_path),
                final_format_path.stat().st_size, rebuild_result["master_duration_ms"],
                "active", now, now
            )
        )
        final_artifact_id = cursor.lastrowid
        
        # Update chapter active artifact pointer
        conn.execute(
            """UPDATE chapters
               SET active_audio_artifact_id=?, audio_status='completed', updated_at=?
               WHERE id=?""",
            (final_artifact_id, now, chapter["id"])
        )
    
    # Clean up temp directory
    import shutil
    shutil.rmtree(rebuild_result["temp_dir"], ignore_errors=True)
    
    db.audit(
        "segment_candidate_accepted",
        job_id=job_id,
        chapter_id=chapter["id"],
        details={
            "segment_id": segment_id,
            "attempt_id": attempt_id,
            "new_artifact_id": final_artifact_id,
            "duration_ms": rebuild_result["master_duration_ms"]
        }
    )
    
    return {
        "segment_id": segment_id,
        "attempt_id": attempt_id,
        "new_artifact_id": final_artifact_id,
        "chapter_duration_ms": rebuild_result["master_duration_ms"]
    }


def reject_segment_candidate(
    db: Database,
    segment_id: int,
    attempt_id: int
) -> dict[str, Any]:
    """
    Reject candidate and keep active segment unchanged.
    
    Marks candidate as 'rejected' and retains WAV for audit.
    Does not modify active segment or chapter artifacts.
    
    Args:
        db: Database
        segment_id: Segment ID
        attempt_id: Candidate attempt ID
    
    Returns:
        Dict with segment_id, attempt_id, status='rejected'
    
    Raises:
        RegenerationValidationError: Validation failed
    """
    # Validate
    attempt = db.fetch_one(
        "SELECT * FROM segment_attempts WHERE id=? AND segment_id=?",
        (attempt_id, segment_id)
    )
    
    if not attempt:
        raise RegenerationValidationError(
            f"Attempt {attempt_id} not found for segment {segment_id}"
        )
    
    if attempt["status"] != "candidate":
        raise RegenerationValidationError(
            f"Attempt {attempt_id} has status '{attempt['status']}', expected 'candidate'"
        )
    
    # Mark as rejected (keep WAV for audit)
    now = utcnow()
    with db.connect() as conn:
        conn.execute(
            """UPDATE segment_attempts
               SET status='rejected', rejected_at=?
               WHERE id=?""",
            (now, attempt_id)
        )
    
    segment = db.fetch_one(
        """SELECT jc.job_id, jc.chapter_id
           FROM segments s
           JOIN job_chapters jc ON jc.id = s.job_chapter_id
           WHERE s.id = ?""",
        (segment_id,)
    )
    
    db.audit(
        "segment_candidate_rejected",
        job_id=segment["job_id"],
        chapter_id=segment["chapter_id"],
        details={"segment_id": segment_id, "attempt_id": attempt_id}
    )
    
    return {
        "segment_id": segment_id,
        "attempt_id": attempt_id,
        "status": "rejected"
    }


def list_segment_attempts(db: Database, segment_id: int) -> dict[str, Any]:
    """
    List all attempts for a segment.
    
    Returns active, candidate, and history (rejected/superseded) attempts.
    Always exposes current segment as active/original even before first regeneration.
    
    Includes legacy state repair: if a verified segment has candidate as Attempt 1
    but no active attempt, seeds active Attempt 1 and renumbers candidate to Attempt 2.
    """
    segment = db.fetch_one("SELECT * FROM segments WHERE id=?", (segment_id,))
    if not segment:
        raise RegenerationValidationError(f"Segment {segment_id} not found")
    
    attempts = db.fetch_all(
        """SELECT * FROM segment_attempts
           WHERE segment_id=?
           ORDER BY attempt_number DESC""",
        (segment_id,)
    )
    
    active = None
    candidate = None
    history = []
    
    for attempt in attempts:
        if attempt["status"] == "active":
            active = attempt
        elif attempt["status"] == "candidate":
            candidate = attempt
        else:
            history.append(attempt)
    
    # Legacy state repair: verified segment + candidate as Attempt 1 + no active
    # This handles segments where candidate was created before the seeding fix
    if (not active and 
        candidate and 
        candidate["attempt_number"] == 1 and
        segment["status"] == "verified" and 
        segment["wav_path"]):
        
        # Transactionally: seed active Attempt 1, renumber candidate to Attempt 2
        now = utcnow()
        with db.transaction() as conn:
            # Double-check active still doesn't exist (race condition guard)
            check_active = conn.execute(
                "SELECT id FROM segment_attempts WHERE segment_id=? AND status='active'",
                (segment_id,)
            ).fetchone()
            
            if not check_active:
                # CRITICAL: Renumber candidate from 1 to 2 FIRST to avoid UNIQUE constraint
                conn.execute(
                    "UPDATE segment_attempts SET attempt_number=2 WHERE id=?",
                    (candidate["id"],)
                )
                
                # Now seed current segment as active Attempt 1
                conn.execute(
                    """INSERT INTO segment_attempts(
                        segment_id, attempt_number, status, wav_path, audio_sha256,
                        duration_ms, created_at, accepted_at
                    ) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        segment_id, 1, 'active', segment["wav_path"],
                        segment["audio_sha256"], segment["duration_ms"],
                        segment["verified_at"] or now, segment["verified_at"] or now
                    )
                )
                active_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                
                # Update local references
                active = dict(segment_id=segment_id, id=active_id, attempt_number=1,
                             status='active', wav_path=segment["wav_path"],
                             audio_sha256=segment["audio_sha256"],
                             duration_ms=segment["duration_ms"],
                             created_at=segment["verified_at"] or now,
                             accepted_at=segment["verified_at"] or now,
                             rejected_at=None, superseded_at=None)
                candidate = dict(candidate)
                candidate["attempt_number"] = 2
        
        # Re-fetch to get consistent state after repair
        attempts = db.fetch_all(
            """SELECT * FROM segment_attempts
               WHERE segment_id=?
               ORDER BY attempt_number DESC""",
            (segment_id,)
        )
        active = None
        candidate = None
        history = []
        for attempt in attempts:
            if attempt["status"] == "active":
                active = attempt
            elif attempt["status"] == "candidate":
                candidate = attempt
            else:
                history.append(attempt)
    
    # Build response dictionaries
    active_dict = None
    if active:
        active_dict = {
            "attempt_id": active["id"],
            "attempt_number": active["attempt_number"],
            "status": active["status"],
            "duration_ms": active["duration_ms"],
            "created_at": active["created_at"],
            "accepted_at": active["accepted_at"],
            "rejected_at": active["rejected_at"],
            "superseded_at": active["superseded_at"]
        }
    elif segment["wav_path"]:
        # Virtual attempt 0 for segments with no attempts table rows yet
        active_dict = {
            "attempt_id": None,
            "attempt_number": 0,
            "status": "active",
            "duration_ms": segment["duration_ms"],
            "created_at": segment["verified_at"] or segment["created_at"],
            "accepted_at": segment["verified_at"],
            "rejected_at": None,
            "superseded_at": None
        }
    
    candidate_dict = None
    if candidate:
        candidate_dict = {
            "attempt_id": candidate["id"],
            "attempt_number": candidate["attempt_number"],
            "status": candidate["status"],
            "duration_ms": candidate["duration_ms"],
            "created_at": candidate["created_at"],
            "accepted_at": candidate["accepted_at"],
            "rejected_at": candidate["rejected_at"],
            "superseded_at": candidate["superseded_at"]
        }
    
    history_list = []
    for h in history:
        history_list.append({
            "attempt_id": h["id"],
            "attempt_number": h["attempt_number"],
            "status": h["status"],
            "duration_ms": h["duration_ms"],
            "created_at": h["created_at"],
            "accepted_at": h["accepted_at"],
            "rejected_at": h["rejected_at"],
            "superseded_at": h["superseded_at"]
        })
    
    return {
        "segment_id": segment_id,
        "active_attempt": active_dict,
        "candidate": candidate_dict,
        "history": history_list
    }

