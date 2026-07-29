from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import threading
import time
import wave
from dataclasses import replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(r"C:\StoryAudio_GoldenJourney_Test")
MARKER_TEXT = "muc tieu cua lao la tran phap truyen tong o ben trong."


def _reserve_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    if port == 8772:
        return _reserve_port()
    return port


def _write_tone(path: Path, *, frequency: float, duration_ms: int = 360, rate: int = 48_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(rate * duration_ms / 1000))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        for index in range(frames):
            value = int(9500 * math.sin(2 * math.pi * frequency * index / rate))
            handle.writeframesraw(value.to_bytes(2, "little", signed=True))


class FakeTtsService:
    status = "ready"
    error = None

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._marker_seen = False

    def voices(self) -> list[dict[str, str]]:
        return [
            {"id": "fixture_narrator", "label": "Fixture Narrator"},
            {"id": "fixture_character", "label": "Fixture Commander"},
            {"id": "fixture_unknown", "label": "Fixture Unknown"},
            {"id": "fixture_female", "label": "Fixture Female"},
        ]

    def synthesize(self, *, synth_input=None, output_path: Path, **_kwargs):
        text = str(getattr(synth_input, "text", "") or "")
        voice = str(getattr(synth_input, "preset_voice_id", "") or "")
        normalized = (
            text.lower()
            .replace("á", "a")
            .replace("à", "a")
            .replace("ả", "a")
            .replace("ã", "a")
            .replace("ạ", "a")
            .replace("ă", "a")
            .replace("â", "a")
            .replace("đ", "d")
            .replace("é", "e")
            .replace("è", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("ơ", "o")
            .replace("ú", "u")
            .replace("ư", "u")
            .replace("ý", "y")
        )
        job_id = None
        for part in output_path.parts:
            if part.startswith("job_"):
                try:
                    job_id = int(part.removeprefix("job_"))
                except ValueError:
                    pass
        marker = "truyen tong" in normalized
        defective = bool(marker and not self._marker_seen)
        if marker:
            self._marker_seen = True
        frequency = 333.0 if defective else 520.0 + (len(self.calls) % 5) * 65.0
        _write_tone(output_path, frequency=frequency)
        self.calls.append(
            {
                "job_id": job_id,
                "voice": voice,
                "text": text,
                "marker": marker,
                "defective_fixture": defective,
                "path": str(output_path),
            }
        )
        return 360, 48_000


class CountingWorker:
    def __init__(self, worker):
        self._worker = worker
        self.wake_count = 0

    def __getattr__(self, name):
        return getattr(self._worker, name)

    def wake(self) -> None:
        self.wake_count += 1
        self._worker.wake()


class FakePrepareResult:
    def __init__(self, payload: dict[str, Any], http_status: int = 200) -> None:
        self.payload = payload
        self.http_status = http_status


class FakeBatchPrepareService:
    def __init__(self, api_module) -> None:
        self.api = api_module

    def prepare(self, request: dict[str, Any], *, authorization_header: str | None = None, credential_in_url: bool = False):
        del authorization_header, credential_in_url
        book_id = int(request["book_id"])
        from_chapter = int(request["from_chapter"])
        to_chapter = int(request["to_chapter"])
        if from_chapter != to_chapter:
            return FakePrepareResult({"message": "fixture supports one chapter"}, 409)
        plan = self.api.db.fetch_one(
            """SELECT cp.id
               FROM casting_plans cp
               JOIN chapters c ON c.id=cp.chapter_id
               WHERE c.book_id=? AND c.chapter_number=? AND cp.status='approved'
               ORDER BY cp.id DESC LIMIT 1""",
            (book_id, from_chapter),
        )
        if not plan:
            return FakePrepareResult({"message": "no approved plan"}, 409)
        from story_audio.pipeline import prepare_job

        result = prepare_job(
            self.api.db,
            self.api.settings,
            book_id=book_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            voice_name="fixture_narrator",
            repair_mode="off",
            output_format="m4a",
            skip_completed=False,
            casting_plan_id=int(plan["id"]),
            store=self.api.store,
            voice_catalog=self.api._load_voice_catalog(),
        )
        payload = {
            "status": "APPLIED",
            "state": result["status"],
            "job_id": result["job_id"],
            "result": result,
        }
        return FakePrepareResult(payload)


def _runtime_ready(_descriptor) -> dict[str, Any]:
    return {
        "status": "ISOLATED_GOLDEN_JOURNEY_READY",
        "runtime_mode": "PRODUCTION",
        "canonical_backed": False,
        "schema_version": 15,
        "required_schema_version": 15,
        "feature_available": True,
        "mutation_enabled": True,
        "operator_window_open": True,
        "kill_switch_active": False,
        "authentication_state": "AUTH_CONFIGURED",
        "mutation_service_constructed": True,
        "mutation_route_registered": True,
        "read_only_planning_available": True,
        "mutation_authorized": True,
        "execution_endpoint_available": True,
        "real_job_execution": False,
        "prepare_starts_render": False,
        "start_render_available": True,
        "startup_migration_enabled": False,
        "reasons": ["ISOLATED_GOLDEN_JOURNEY"],
    }


def configure_isolated_api(run_root: Path):
    os.environ["STORY_AUDIO_DATA_DIR"] = str(run_root / "data")
    os.environ["STORY_AUDIO_TESTING"] = "1"
    os.environ["TEMP"] = str(run_root / "temp")
    os.environ["TMP"] = str(run_root / "temp")
    (run_root / "temp").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    import story_audio.api as api
    from story_audio.config import Settings
    from story_audio.custom_voice import CustomVoiceRepository
    from story_audio.db import Database
    from story_audio.pipeline import PipelineWorker
    from story_audio.storage import ContentStore
    from story_audio.voice_preview import VoicePreviewService

    api.settings = replace(
        api.settings,
        data_dir=run_root / "data",
        db_path=run_root / "data" / "app.db",
        blobs_dir=run_root / "data" / "blobs",
        output_dir=run_root / "data" / "output",
        work_dir=run_root / "data" / "work",
        log_dir=run_root / "logs",
        undo_seconds=0,
        worker_poll_seconds=0.05,
        minimum_free_gb=0,
        successful_segment_retention_hours=24 * 365,
    )
    api.settings.ensure_dirs()
    api.db = Database(api.settings.db_path)
    api.db.initialize()
    api.store = ContentStore(api.settings)
    api.custom_voice_repo = CustomVoiceRepository(api.db, api.store)
    api.tts_service = FakeTtsService()
    api.worker = CountingWorker(PipelineWorker(api.db, api.store, api.tts_service, api.settings))
    api.voice_previews = VoicePreviewService(api.tts_service, api.settings, custom_voice_repo=api.custom_voice_repo, store=api.store)
    api.batch_prepare_api_service = FakeBatchPrepareService(api)
    api.public_runtime_readiness = _runtime_ready
    return api


def seed_fixture(api) -> dict[str, Any]:
    from story_audio.casting import approve_plan, create_casting_draft, create_character, split_utterances
    from story_audio.db import utcnow
    from story_audio.files import sha256_file
    from story_audio.voice_profile import set_book_voice_profile

    now = utcnow()
    text = (
        'Nguoi ke chuyen mo dau. "Menh lenh thu nhat." '
        'Hua Thanh dap lai. "Ta da hieu." Mot nguoi chua ro noi: "Di ngay." '
        'muc tieu cua lao la tran phap truyen tong o ben trong. Ket thuc.'
    )
    with api.db.transaction() as connection:
        book_id = int(
            connection.execute(
                "INSERT INTO books(title,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("Golden Fixture Book", "golden.epub", "fixture-book-sha", 373, now, now),
            ).lastrowid
        )
        chapter_372 = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at,audio_status) VALUES(?,?,?,?,?,?,?)",
                (book_id, 372, "Golden Chapter 372", len(text), now, now, "not_created"),
            ).lastrowid
        )
        chapter_373 = int(
            connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,char_count,created_at,updated_at,audio_status) VALUES(?,?,?,?,?,?,?)",
                (book_id, 373, "Golden Completed Neighbor", 24, now, now, "completed"),
            ).lastrowid
        )
        path, digest = api.store.put_text(text)
        revision_372 = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_372, "reflowed", path, digest, "lexical-372", len(text), "fixture", "approved", now),
            ).lastrowid
        )
        path_373, digest_373 = api.store.put_text("Neighbor chapter audio fixture.")
        revision_373 = int(
            connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,
                    processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (chapter_373, "reflowed", path_373, digest_373, "lexical-373", 31, "fixture", "approved", now),
            ).lastrowid
        )
        connection.execute("UPDATE chapters SET active_text_revision_id=? WHERE id=?", (revision_372, chapter_372))
        connection.execute("UPDATE chapters SET active_text_revision_id=? WHERE id=?", (revision_373, chapter_373))

    set_book_voice_profile(
        api.db,
        book_id,
        narrator_voice_id="fixture_narrator",
        male_dialogue_voice_id="fixture_character",
        female_dialogue_voice_id="fixture_female",
        unknown_fallback="explicit_voice",
        unknown_voice_id="fixture_unknown",
        allowed_voice_ids={"fixture_narrator", "fixture_character", "fixture_female", "fixture_unknown", "fixture_missing"},
    )
    character = create_character(api.db, book_id, "Fixture Commander", "fixture_missing", gender="male")

    utterances = split_utterances(text)
    assignments = []
    for utterance in utterances:
        role = "narrator"
        character_id = None
        if utterance["sequence"] == 2:
            role = "character"
            character_id = int(character["id"])
        elif utterance["sequence"] == 5:
            role = "unknown"
        assignments.append({"utterance_id": utterance["utterance_id"], "role": role, "character_id": character_id})
    initial = create_casting_draft(
        api.db,
        api.store,
        chapter_id=chapter_372,
        text_revision_id=revision_372,
        narrator_voice_id="fixture_narrator",
        assignments=assignments,
        allowed_voice_ids={"fixture_narrator", "fixture_character", "fixture_female", "fixture_unknown", "fixture_missing"},
    )
    approved = approve_plan(api.db, api.store, initial["id"])
    from story_audio.speaker_assignment import build_speaker_assignment_request

    request_meta = build_speaker_assignment_request(
        api.db,
        api.store,
        api.settings,
        chapter_id=chapter_372,
        mode="unassigned_only",
    )
    draft_payload = {
        "schema": "fixture-speaker-draft/v1",
        "text_revision_sha256": request_meta["text_revision_sha256"],
        "targets": request_meta["targets"],
        "review_rows": [],
        "characters": request_meta["candidate_characters"],
    }
    draft_path, draft_sha = api.store.put_json(draft_payload, namespace="speaker_assignment")
    with api.db.transaction() as connection:
        connection.execute(
            """INSERT INTO speaker_assignment_drafts(
                book_id,chapter_id,text_revision_id,input_fingerprint,character_bible_fingerprint,
                model_id,prompt_version,response_schema,mode,status,content_path,content_sha256,
                target_count,valid_count,invalid_count,created_at,approved_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                book_id,
                chapter_372,
                revision_372,
                request_meta["input_fingerprint"],
                request_meta["character_bible_fingerprint"],
                api.settings.gemini_model,
                api.settings.speaker_assignment_prompt_version,
                "fixture-schema",
                request_meta["mode"],
                "approved",
                draft_path,
                draft_sha,
                len(request_meta["targets"]),
                len(request_meta["targets"]),
                0,
                now,
                now,
            ),
        )

    # Seed chapter 373 as an already accepted neighbor for range ZIP assertions.
    neighbor_wav = api.settings.work_dir / "fixture_neighbor.wav"
    _write_tone(neighbor_wav, frequency=660, duration_ms=420)
    neighbor_m4a = api.settings.output_dir / "golden-fixture-book" / "chapter_0373" / "job_900" / "render_0001" / "chapter.m4a"
    neighbor_m4a.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(neighbor_wav), "-c:a", "aac", "-b:a", "128k", str(neighbor_m4a)],
        check=True,
    )
    with api.db.transaction() as connection:
        job = int(
            connection.execute(
                """INSERT INTO jobs(
                    book_id,status,from_chapter,to_chapter,voice_name,repair_mode,output_format,
                    settings_json,total_chapters,completed_chapters,scheduled_at,created_at,started_at,finished_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book_id, "completed", 373, 373, "fixture_narrator", "off", "m4a", "{}", 1, 1, now, now, now, now, now),
            ).lastrowid
        )
        jc = int(
            connection.execute(
                "INSERT INTO job_chapters(job_id,chapter_id,sequence,status,text_revision_id,finished_at) VALUES(?,?,?,?,?,?)",
                (job, chapter_373, 1, "completed", revision_373, now),
            ).lastrowid
        )
        artifact = int(
            connection.execute(
                """INSERT INTO artifacts(
                    chapter_id,job_chapter_id,text_revision_id,artifact_type,path,sha256,size_bytes,
                    duration_ms,status,created_at,verified_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    chapter_373,
                    jc,
                    revision_373,
                    "chapter_m4a",
                    str(neighbor_m4a),
                    sha256_file(neighbor_m4a),
                    neighbor_m4a.stat().st_size,
                    420,
                    "active",
                    now,
                    now,
                ),
            ).lastrowid
        )
        approval = {
            "status": "approved",
            "recorded_at": now,
            "approved_at": now,
            "artifact_id": artifact,
            "job_id": job,
            "output_path": str(neighbor_m4a),
            "sha256": sha256_file(neighbor_m4a),
            "duration_ms": 420,
            "notes": "fixture neighbor accepted",
        }
        connection.execute(
            "UPDATE chapters SET active_audio_artifact_id=?,human_approval_json=?,audio_status='completed',updated_at=? WHERE id=?",
            (artifact, json.dumps(approval), now, chapter_373),
        )
    return {
        "book_id": book_id,
        "chapter_id": chapter_372,
        "chapter_number": 372,
        "neighbor_chapter_id": chapter_373,
        "revision_id": revision_372,
        "character_id": int(character["id"]),
        "initial_casting_plan_id": int(approved["id"]),
        "marker_text": MARKER_TEXT,
    }


def canonical_read_only() -> dict[str, Any]:
    import sqlite3
    import hashlib

    path = ROOT / "data" / "app.db"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        fk = connection.execute("PRAGMA foreign_key_check").fetchall()
        schema = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        chapters = {
            row["chapter_number"]: dict(row)
            for row in connection.execute(
                "SELECT id,chapter_number,audio_status,active_audio_artifact_id,human_approval_json FROM chapters WHERE chapter_number IN (369,372,373)"
            )
        }
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("jobs", "artifacts")
        }
    finally:
        connection.close()
    return {
        "path": str(path),
        "sha256": digest,
        "quick_check": quick,
        "foreign_key_violations": len(fk),
        "schema": int(schema),
        "chapters": chapters,
        "counts": counts,
    }


def inspect_isolated(api, fixture: dict[str, Any], run_root: Path) -> dict[str, Any]:
    rows = api.db.fetch_all(
        """SELECT a.*,c.chapter_number,j.id AS job_id
           FROM artifacts a
           JOIN chapters c ON c.id=a.chapter_id
           LEFT JOIN job_chapters jc ON jc.id=a.job_chapter_id
           LEFT JOIN jobs j ON j.id=jc.job_id
           WHERE c.book_id=?
           ORDER BY a.id""",
        (fixture["book_id"],),
    )
    segments = api.db.fetch_all(
        """SELECT s.id,s.segment_index,s.text_path,s.audio_sha256,s.resolved_voice_id,
                  s.attempt_count,j.id AS job_id
           FROM segments s
           JOIN job_chapters jc ON jc.id=s.job_chapter_id
           JOIN jobs j ON j.id=jc.job_id
           ORDER BY s.id""",
    )
    approvals = api.db.fetch_all(
        "SELECT id,event_code,job_id,chapter_id,details_json FROM audit_events WHERE event_code='human_qa_recorded' ORDER BY id"
    )
    chapter = dict(api.db.fetch_one("SELECT * FROM chapters WHERE id=?", (fixture["chapter_id"],)))
    active_artifact_id = int(chapter["active_audio_artifact_id"] or 0)
    active = dict(api.db.fetch_one("SELECT * FROM artifacts WHERE id=?", (active_artifact_id,)))
    marker_segments = []
    for row in segments:
        text = api.store.read_text(row["text_path"])
        if "truyen tong" in text:
            marker_segments.append({**dict(row), "text": text})
    return {
        "jobs": [dict(row) for row in api.db.fetch_all("SELECT id,status,from_chapter,to_chapter,total_chapters FROM jobs ORDER BY id")],
        "artifacts": [dict(row) for row in rows],
        "segments": [dict(row) for row in segments],
        "marker_segments": marker_segments,
        "qa_audit_count": len(approvals),
        "qa_audit": [dict(row) for row in approvals],
        "chapter": chapter,
        "active_artifact": active,
        "provider_calls": list(api.tts_service.calls),
        "worker_wake_count": int(api.worker.wake_count),
        "run_root": str(run_root),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    for stale in sorted(TEST_ROOT.glob("cert_*")):
        if stale.is_dir() and TEST_ROOT.resolve() in stale.resolve().parents:
            import shutil

            shutil.rmtree(stale)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_root = TEST_ROOT / f"cert_{timestamp}_{os.getpid()}"
    run_root.mkdir(parents=True, exist_ok=True)
    api = configure_isolated_api(run_root)
    fixture = seed_fixture(api)

    import uvicorn

    port = _reserve_port()
    server = uvicorn.Server(
        uvicorn.Config(
            api.app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                import urllib.request

                with urllib.request.urlopen(f"{base_url}/api/runtime", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("isolated runtime did not start")

        browser = subprocess.run(
            [
                "node",
                str(ROOT / "scripts" / "browser_golden_journey_certification.mjs"),
                base_url,
                str(run_root),
                json.dumps(fixture, ensure_ascii=False),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=args.timeout,
            env={**os.environ, "TEMP": str(run_root / "temp"), "TMP": str(run_root / "temp")},
        )
        if browser.returncode != 0:
            raise RuntimeError(f"browser certification failed\nSTDOUT:\n{browser.stdout}\nSTDERR:\n{browser.stderr}")
        browser_evidence = json.loads(browser.stdout)
        isolated = inspect_isolated(api, fixture, run_root)
        canonical = canonical_read_only()
        return {
            "ok": True,
            "base_url": base_url,
            "fixture": fixture,
            "browser": browser_evidence,
            "isolated": isolated,
            "canonical": canonical,
        }
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        try:
            api.worker.stop()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
