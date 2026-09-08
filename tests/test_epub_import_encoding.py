from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from story_audio.config import Settings
from story_audio.db import Database
from story_audio.epub import import_epub
from story_audio.storage import ContentStore


def legacy_decode_utf8(text: str) -> str:
    decoded: list[str] = []
    for byte in text.encode("utf-8"):
        try:
            decoded.append(bytes([byte]).decode("cp1252"))
        except UnicodeDecodeError:
            decoded.append(chr(byte))
    return "".join(decoded)


def write_epub(path: Path, paragraph: str) -> None:
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Encoding Fixture</dc:title><dc:creator>Owner</dc:creator></metadata>
  <manifest><item id="c40" href="chapter40.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="c40"/></spine>
</package>"""
    chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chương 40</h1><p>{paragraph}</p></body></html>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", container.encode("utf-8"))
        archive.writestr("OEBPS/content.opf", package.encode("utf-8"))
        archive.writestr("OEBPS/chapter40.xhtml", chapter.encode("utf-8"))


class EpubImportEncodingTests(unittest.TestCase):
    def test_real_epub_import_repairs_mojibake_before_canonical_storage(self) -> None:
        expected = "Trời vừa sáng. Âm Dương mở cửa, Đông Âu đã thức giấc."
        malformed = legacy_decode_utf8(expected)
        with tempfile.TemporaryDirectory(prefix="story-audio-encoding-epub-") as directory:
            root = Path(directory)
            data = root / "data"
            config = Settings(
                root=root,
                data_dir=data,
                db_path=data / "app.db",
                blobs_dir=data / "blobs",
                output_dir=data / "output",
                work_dir=data / "work",
                log_dir=root / "logs",
            )
            config.ensure_dirs()
            database = Database(config.db_path)
            database.initialize()
            store = ContentStore(config)
            epub_path = root / "encoding.epub"
            write_epub(epub_path, malformed)

            result = import_epub(epub_path, database, store)

            self.assertEqual(result["chapter_count"], 1)
            chapter = database.fetch_one("SELECT * FROM chapters WHERE book_id=?", (result["book_id"],))
            self.assertIsNotNone(chapter)
            self.assertEqual(int(chapter["chapter_number"]), 40)
            revision = database.fetch_one(
                "SELECT * FROM text_revisions WHERE id=?",
                (int(chapter["raw_text_revision_id"]),),
            )
            stored = store.read_text(str(revision["content_path"]))
            self.assertEqual(stored, expected)
            self.assertNotIn("Ã", stored)
            self.assertNotIn("Ä", stored)


if __name__ == "__main__":
    unittest.main()
