from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

import story_audio.api as api_module


class EpubUploadApiTests(unittest.TestCase):
    def _upload(self, filename: str, content: bytes) -> UploadFile:
        return UploadFile(filename=filename, file=io.BytesIO(content))

    def test_upload_persists_source_and_calls_importer(self) -> None:
        content = b"PK\x03\x04fixture-epub"
        with tempfile.TemporaryDirectory(prefix="story-audio-epub-upload-") as directory:
            imports_dir = Path(directory) / "imports"
            settings = SimpleNamespace(imports_dir=imports_dir)
            with patch.object(api_module, "settings", settings), patch.object(
                api_module,
                "import_epub",
                return_value={"book_id": 7, "created": True, "chapter_count": 3},
            ) as importer:
                result = asyncio.run(api_module.import_book_upload(self._upload("owner.epub", content)))

            self.assertEqual(result, {"book_id": 7, "created": True, "chapter_count": 3})
            importer.assert_called_once()
            imported_path = importer.call_args.args[0]
            self.assertEqual(imported_path.parent, imports_dir)
            self.assertEqual(imported_path.suffix, ".epub")
            self.assertEqual(imported_path.read_bytes(), content)
            self.assertFalse(any(path.name.startswith(".upload-") for path in imports_dir.iterdir()))

    def test_upload_rejects_non_epub_before_writing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="story-audio-epub-upload-") as directory:
            imports_dir = Path(directory) / "imports"
            settings = SimpleNamespace(imports_dir=imports_dir)
            with patch.object(api_module, "settings", settings), patch.object(api_module, "import_epub") as importer:
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(api_module.import_book_upload(self._upload("notes.txt", b"not epub")))

            self.assertEqual(raised.exception.status_code, 400)
            importer.assert_not_called()
            self.assertFalse(imports_dir.exists())

    def test_invalid_epub_is_removed_when_importer_rejects_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="story-audio-epub-upload-") as directory:
            imports_dir = Path(directory) / "imports"
            settings = SimpleNamespace(imports_dir=imports_dir)
            with patch.object(api_module, "settings", settings), patch.object(
                api_module, "import_epub", side_effect=ValueError("EPUB invalid")
            ):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(api_module.import_book_upload(self._upload("broken.epub", b"PK\x03\x04broken")))

            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(raised.exception.detail, "EPUB invalid")
            self.assertTrue(imports_dir.exists())
            self.assertEqual(list(imports_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
