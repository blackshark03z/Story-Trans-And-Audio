from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from story_audio.casting import approve_plan, create_casting_draft, create_character, split_utterances, update_character  # noqa: E402
from story_audio.config import settings  # noqa: E402
from story_audio.db import Database, utcnow  # noqa: E402
from story_audio.diagnostics import retry_segment  # noqa: E402
from story_audio.files import atomic_write_json, sha256_file, sha256_text  # noqa: E402
from story_audio.pipeline import PipelineWorker, create_job  # noqa: E402
from story_audio.storage import ContentStore  # noqa: E402
from story_audio.tts import tts_service  # noqa: E402


SMOKE_TEXT = (
    "Trời vừa sáng, người dẫn chuyện bước vào căn phòng nhỏ. "
    '"Chào anh, tôi đã đợi từ sớm." '
    "An đặt chiếc túi xuống bàn rồi nhìn ra cửa sổ. "
    '"Tôi xin lỗi, đường hôm nay đông hơn mọi khi." '
    "Bình rót trà, cả căn phòng bỗng yên tĩnh. "
    '"Chúng ta bắt đầu nhé, thời gian không còn nhiều." '
    '"Được, tôi đã chuẩn bị xong mọi thứ." '
    "Người dẫn chuyện khép lại cuộc gặp bằng một cái gật đầu bình thản."
)
TOLERANCE_MS = 1_000


def ffprobe_ms(path: Path) -> int:
    import subprocess

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(round(float(result.stdout.strip()) * 1000))


def artifact_rows(db: Database, job_chapter_id: int) -> list[dict]:
    return [dict(row) for row in db.fetch_all(
        "SELECT * FROM artifacts WHERE job_chapter_id=? ORDER BY id", (job_chapter_id,)
    )]


def verify(db: Database, store: ContentStore, job: dict, job_chapter: dict) -> dict:
    segments = [dict(row) for row in db.fetch_all(
        "SELECT * FROM segments WHERE job_chapter_id=? ORDER BY segment_index", (job_chapter["id"],)
    )]
    artifacts = artifact_rows(db, job_chapter["id"])
    active = [row for row in artifacts if row["status"] == "active"]
    master = next(row for row in reversed(artifacts) if row["artifact_type"] == "chapter_master_wav")
    timeline = next(row for row in reversed(artifacts) if row["artifact_type"] == "segment_timeline_json")
    export = active[-1]
    master_path, timeline_path, export_path = Path(master["path"]), Path(timeline["path"]), Path(export["path"])
    for path in (master_path, timeline_path, export_path):
        if not path.is_file():
            raise RuntimeError(f"Missing artifact: {path}")
    master_ms, export_ms = ffprobe_ms(master_path), ffprobe_ms(export_path)
    payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    items = payload["items"]
    if len(items) != len(segments):
        raise RuntimeError("Timeline/segment count mismatch")
    if any(not item.get("speaker_role") or not item.get("voice_id") for item in items):
        raise RuntimeError("Timeline item lacks speaker/voice metadata")
    if any(item["speaker_role"] == "character" and (not item.get("character_id") or not item.get("character_name")) for item in items):
        raise RuntimeError("Character timeline item lacks character metadata")
    if [item["utterance_sequence"] for item in items] != sorted(item["utterance_sequence"] for item in items):
        raise RuntimeError("Segment order does not follow utterance order")
    speakers: dict[int, set[tuple]] = {}
    for item in items:
        speakers.setdefault(item["utterance_sequence"], set()).add(
            (item["speaker_role"], item.get("character_id"), item["voice_id"])
        )
    if any(len(values) != 1 for values in speakers.values()):
        raise RuntimeError("An utterance contains mixed speaker metadata")
    for segment in segments:
        wav = Path(segment["wav_path"])
        if not wav.is_file() or sha256_file(wav) != segment["audio_sha256"]:
            raise RuntimeError(f"Segment hash mismatch: {segment['id']}")
    timeline_ms = items[-1]["end_ms"] if items else 0
    if abs(timeline_ms - export_ms) > TOLERANCE_MS or abs(master_ms - export_ms) > TOLERANCE_MS:
        raise RuntimeError("Timeline/master/export duration mismatch")
    snapshot = json.loads(job["casting_snapshot_json"])
    plan_voices = {item["resolved_voice_id"] for item in snapshot["utterances"]}
    return {
        "segment_count": len(segments),
        "utterance_count": len(speakers),
        "voices": sorted(plan_voices),
        "master_path": str(master_path),
        "export_path": str(export_path),
        "timeline_path": str(timeline_path),
        "master_duration_ms": master_ms,
        "export_duration_ms": export_ms,
        "timeline_duration_ms": timeline_ms,
        "segments": segments,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live-db", action="store_true", help="Opt-in to use the canonical live DB")
    parser.add_argument("--skip-retry", action="store_true")
    args = parser.parse_args()

    if getattr(args, "allow_live_db", False):
        import os
        os.environ["STORY_AUDIO_ALLOW_LIVE_DB"] = "1"
    settings.ensure_dirs()
    db, store = Database(settings.db_path), ContentStore(settings)
    db.initialize()
    voices = tts_service.voices()
    if len(voices) < 4:
        raise RuntimeError("Smoke test requires at least four preset voices")
    selected = voices[:4]
    run_key = uuid.uuid4().hex[:10]
    now = utcnow()
    content_path, content_sha = store.put_text(SMOKE_TEXT)
    source_sha = sha256_text(f"multivoice-smoke:{run_key}:{content_sha}")
    with db.transaction() as connection:
        book_id = int(connection.execute(
            "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (f"Smoke Multi-Voice {run_key}", f"smoke://multivoice/{run_key}", source_sha, 1, now, now),
        ).lastrowid)
        chapter_id = int(connection.execute(
            "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (book_id, 1, "Smoke Chapter", len(SMOKE_TEXT), now, now),
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
    character_a = create_character(db, book_id, "Smoke An", selected[1]["id"])
    character_b = create_character(db, book_id, "Smoke Bình", selected[2]["id"])
    utterances = split_utterances(SMOKE_TEXT, maximum=settings.tts_max_chars)
    if not 6 <= len(utterances) <= 15:
        raise RuntimeError(f"Unexpected smoke utterance count: {len(utterances)}")
    assignments = []
    for utterance in utterances:
        sequence = utterance["sequence"]
        if sequence in {2, 6}:
            assignments.append({"utterance_id": utterance["utterance_id"], "role": "character", "character_id": character_a["id"]})
        elif sequence in {4, 7}:
            assignments.append({"utterance_id": utterance["utterance_id"], "role": "character", "character_id": character_b["id"]})
        else:
            assignments.append({"utterance_id": utterance["utterance_id"], "role": "narrator", "character_id": None})
    draft = create_casting_draft(
        db,
        store,
        chapter_id=chapter_id,
        text_revision_id=revision_id,
        narrator_voice_id=selected[0]["id"],
        assignments=assignments,
        allowed_voice_ids={item["id"] for item in voices},
        maximum=settings.tts_max_chars,
    )
    plan = approve_plan(db, store, draft["id"])
    plan_blob_before = store.absolute(plan["content_path"]).read_bytes()
    job_result = create_job(
        db,
        settings,
        book_id=book_id,
        from_chapter=1,
        to_chapter=1,
        voice_name=selected[0]["id"],
        repair_mode="off",
        output_format="m4a",
        skip_completed=False,
        casting_plan_id=plan["id"],
        store=store,
    )
    job_id = job_result["job_id"]
    job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
    snapshot_before = job["casting_snapshot_json"]
    worker = PipelineWorker(db, store, tts_service, settings)
    started = time.monotonic()
    worker._run_job(job)
    first_render_seconds = round(time.monotonic() - started, 2)
    job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
    if job["status"] != "completed":
        raise RuntimeError(f"Real TTS job failed: {job['status']} {job['error_message']}")
    job_chapter = dict(db.fetch_one("SELECT * FROM job_chapters WHERE job_id=?", (job_id,)))
    first = verify(db, store, job, job_chapter)
    final_verification = first
    if store.absolute(plan["content_path"]).read_bytes() != plan_blob_before:
        raise RuntimeError("Approved casting plan blob changed")

    retry_report = None
    if not args.skip_retry:
        untouched_before = {
            row["id"]: (sha256_file(Path(row["wav_path"])), Path(row["wav_path"]).stat().st_mtime_ns)
            for row in first["segments"]
        }
        target = next(row for row in first["segments"] if row["speaker_role"] == "character")
        target_path = Path(target["wav_path"])
        safety_copy = settings.work_dir / f"job_{job_id}" / "smoke_backup" / target_path.name
        safety_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, safety_copy)
        old_artifacts = {row["id"]: (row["path"], row["sha256"]) for row in first["artifacts"]}
        update_character(db, character_a["id"], voice_id=selected[3]["id"])
        if db.fetch_one("SELECT casting_snapshot_json FROM jobs WHERE id=?", (job_id,))["casting_snapshot_json"] != snapshot_before:
            raise RuntimeError("Character default voice mutation changed job snapshot")
        target_path.unlink()
        with db.connect() as connection:
            connection.execute("UPDATE segments SET status='failed',error_message='controlled smoke corruption' WHERE id=?", (target["id"],))
        retry_segment(db, target["id"])
        retry_job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
        retry_started = time.monotonic()
        worker._run_job(retry_job)
        retry_seconds = round(time.monotonic() - retry_started, 2)
        retry_job = dict(db.fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
        retry_chapter = dict(db.fetch_one("SELECT * FROM job_chapters WHERE job_id=?", (job_id,)))
        second = verify(db, store, retry_job, retry_chapter)
        final_verification = second
        untouched_after = {
            row["id"]: (sha256_file(Path(row["wav_path"])), Path(row["wav_path"]).stat().st_mtime_ns)
            for row in second["segments"] if row["id"] != target["id"]
        }
        changed_untouched = [segment_id for segment_id, value in untouched_after.items() if untouched_before[segment_id] != value]
        if changed_untouched:
            raise RuntimeError(f"Verified segments were modified during retry: {changed_untouched}")
        if Path(target["wav_path"]).stat().st_mtime_ns == untouched_before[target["id"]][1]:
            raise RuntimeError("Controlled failed segment was not re-rendered")
        artifact_immutability_errors = []
        for artifact_id, (path, expected_hash) in old_artifacts.items():
            if Path(path).is_file() and sha256_file(Path(path)) != expected_hash:
                artifact_immutability_errors.append(artifact_id)
        if artifact_immutability_errors:
            raise RuntimeError(f"Retry overwrote immutable artifact files: {artifact_immutability_errors}")
        retry_report = {
            "target_segment_id": target["id"],
            "target_voice_id": target["resolved_voice_id"],
            "retry_seconds": retry_seconds,
            "untouched_segments_reused": len(untouched_after),
            "safety_copy": str(safety_copy),
            "second_export_path": second["export_path"],
        }

    report = {
        "run_key": run_key,
        "book_id": book_id,
        "book_title": f"Smoke Multi-Voice {run_key}",
        "chapter_id": chapter_id,
        "chapter_number": 1,
        "text_revision_id": revision_id,
        "casting_plan_id": plan["id"],
        "casting_plan_sha256": plan["plan_sha256"],
        "job_id": job_id,
        "first_render_seconds": first_render_seconds,
        "speaker_voices": {
            "narrator": selected[0],
            "Smoke An": selected[1],
            "Smoke Bình": selected[2],
        },
        "verification": {
            key: value for key, value in final_verification.items() if key not in {"segments", "artifacts"}
        },
        "retry": retry_report,
        "duration_tolerance_ms": TOLERANCE_MS,
    }
    report_dir = settings.data_dir / "smoke_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"multivoice-{run_key}.json"
    atomic_write_json(report_path, report)
    print(json.dumps({**report, "report_path": str(report_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
