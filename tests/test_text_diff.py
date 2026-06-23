from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from story_audio.db import Database, utcnow
from story_audio.files import sha256_text
from story_audio.storage import ContentStore
from story_audio.text_diff import TextDiffError, build_revision_diff, diff_texts
from tests.test_recovery import make_config


def seed_diff(root: Path):
    config = make_config(root)
    config.ensure_dirs()
    db, store = Database(config.db_path), ContentStore(config)
    db.initialize()
    now = utcnow()
    with db.transaction() as connection:
        book_id = int(connection.execute(
            "INSERT INTO books(title,source_path,source_sha256,created_at,updated_at) VALUES(?,?,?,?,?)",
            ("Diff Book", "diff.epub", "diff-book", now, now),
        ).lastrowid)
        chapter_a = int(connection.execute(
            "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
            (book_id, 1, "A", now, now),
        ).lastrowid)
        chapter_b = int(connection.execute(
            "INSERT INTO chapters(book_id,chapter_number,title,created_at,updated_at) VALUES(?,?,?,?,?)",
            (book_id, 2, "B", now, now),
        ).lastrowid)

    def add(chapter_id: int, kind: str, text: str, parent: int | None = None) -> int:
        path, digest = store.put_text(text)
        with db.connect() as connection:
            return int(connection.execute(
                """INSERT INTO text_revisions(
                    chapter_id,parent_revision_id,kind,content_path,content_sha256,lexical_sha256,
                    char_count,processor_version,status,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (chapter_id, parent, kind, path, digest, "lex", len(text), "test-v1", "approved", now),
            ).lastrowid)

    raw = add(chapter_a, "raw", "Xin chào bạn")
    reflowed = add(chapter_a, "reflowed", "Xin chào bạn.", raw)
    repaired = add(chapter_a, "repaired", "Xin chào, bạn!", reflowed)
    other = add(chapter_b, "raw", "Chương khác")
    with db.connect() as connection:
        connection.execute(
            "UPDATE chapters SET raw_text_revision_id=?,active_text_revision_id=? WHERE id=?",
            (raw, repaired, chapter_a),
        )
    return config, db, store, chapter_a, raw, reflowed, repaired, other


class TextDiffEngineTests(unittest.TestCase):
    def test_identical_text(self) -> None:
        result = diff_texts("Giống nhau.", "Giống nhau.")
        self.assertEqual(result["summary"]["blocks_changed"], 0)
        self.assertEqual(result["summary"]["tokens_added"], 0)
        self.assertTrue(result["summary"]["lexical_integrity"])

    def test_whitespace_only_change_is_marked(self) -> None:
        result = diff_texts("Xin chào bạn.", "Xin  chào\n bạn.")
        self.assertEqual(result["summary"]["tokens_added"], 0)
        self.assertTrue(result["summary"]["lexical_integrity"])
        self.assertTrue(any(op["whitespace_only"] for block in result["blocks"] for op in block["operations"]))

    def test_add_delete_and_replace_punctuation(self) -> None:
        added = diff_texts("Xin chào", "Xin chào!")
        deleted = diff_texts("Xin chào!", "Xin chào")
        replaced = diff_texts("Xin chào.", "Xin chào!")
        self.assertGreater(added["summary"]["punctuation_added"], 0)
        self.assertGreater(deleted["summary"]["punctuation_removed"], 0)
        self.assertEqual(replaced["summary"]["punctuation_changes"], 2)
        self.assertTrue(replaced["summary"]["lexical_integrity"])

    def test_paragraph_split_and_merge(self) -> None:
        split = diff_texts("Đoạn một. Đoạn hai.", "Đoạn một.\n\nĐoạn hai.")
        merged = diff_texts("Đoạn một.\n\nĐoạn hai.", "Đoạn một. Đoạn hai.")
        self.assertGreater(split["summary"]["blocks_changed"], 0)
        self.assertGreater(merged["summary"]["blocks_changed"], 0)

    def test_unicode_vietnamese_and_dialogue_quotes(self) -> None:
        result = diff_texts('Cô nói "xin chào"', 'Cô nói: “xin chào!”')
        self.assertTrue(result["summary"]["lexical_integrity"])
        self.assertGreater(result["summary"]["punctuation_changes"], 0)

    def test_large_text_warns_without_truncation(self) -> None:
        left, right = "a" * 30_000, "a" * 29_999 + "b"
        result = diff_texts(left, right)
        self.assertTrue(result["warnings"])
        self.assertEqual("".join(block["left"] for block in result["blocks"]), left)
        self.assertEqual("".join(block["right"] for block in result["blocks"]), right)

    def test_hard_limit_returns_explicit_error(self) -> None:
        with self.assertRaisesRegex(TextDiffError, "exceeds diff limit"):
            diff_texts("a" * 300_000, "b" * 300_000)


class RevisionDiffTests(unittest.TestCase):
    def test_structured_diff_metadata_has_no_internal_path_and_preserves_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, chapter, raw, _reflowed, repaired, _other = seed_diff(Path(directory))
            before = dict(db.fetch_one("SELECT raw_text_revision_id,active_text_revision_id FROM chapters WHERE id=?", (chapter,)))
            result = build_revision_diff(db, store, chapter, raw, repaired)
            after = dict(db.fetch_one("SELECT raw_text_revision_id,active_text_revision_id FROM chapters WHERE id=?", (chapter,)))
            self.assertEqual(before, after)
            serialized = repr(result)
            self.assertNotIn("content_path", serialized)
            self.assertNotIn(str(_config.blobs_dir), serialized)
            self.assertTrue(result["revision_a"]["is_raw_selected"])
            self.assertTrue(result["revision_b"]["is_active"])

    def test_cross_chapter_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, chapter, raw, _reflowed, _repaired, other = seed_diff(Path(directory))
            with self.assertRaisesRegex(TextDiffError, "same requested chapter"):
                build_revision_diff(db, store, chapter, raw, other)

    def test_missing_blob_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, chapter, raw, reflowed, _repaired, _other = seed_diff(Path(directory))
            row = db.fetch_one("SELECT content_path FROM text_revisions WHERE id=?", (raw,))
            store.absolute(row["content_path"]).unlink()
            with self.assertRaisesRegex(TextDiffError, "missing or unreadable"):
                build_revision_diff(db, store, chapter, raw, reflowed)

    def test_corrupt_blob_hash_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _config, db, store, chapter, raw, reflowed, _repaired, _other = seed_diff(Path(directory))
            row = db.fetch_one("SELECT content_path FROM text_revisions WHERE id=?", (raw,))
            store.absolute(row["content_path"]).write_text("corrupt", encoding="utf-8")
            with self.assertRaisesRegex(TextDiffError, "hash mismatch"):
                build_revision_diff(db, store, chapter, raw, reflowed)

    def test_xss_like_text_remains_plain_structured_data(self) -> None:
        result = diff_texts("safe", '<img src=x onerror=alert(1)><script>x</script>')
        payload = "".join(block["right"] for block in result["blocks"])
        self.assertIn("<script>", payload)
        self.assertTrue(all("html" not in block for block in result["blocks"]))


if __name__ == "__main__":
    unittest.main()
