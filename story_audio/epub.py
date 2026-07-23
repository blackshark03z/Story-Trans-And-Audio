from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .db import Database, utcnow
from .files import sha256_file
from .storage import ContentStore
from .text import lexical_sha256, qa_text, reflow_paragraphs
from .text_encoding import validate_canonical_text


CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


@dataclass(frozen=True)
class ImportedChapter:
    number: int
    title: str
    href: str
    paragraphs: list[str]


def _text_content(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _rootfile(archive: zipfile.ZipFile) -> str:
    root = ET.fromstring(archive.read("META-INF/container.xml"))
    node = root.find(".//c:rootfile", CONTAINER_NS)
    if node is None or not node.get("full-path"):
        raise ValueError("EPUB container.xml không có rootfile.")
    return str(node.get("full-path"))


def parse_epub(path: Path) -> tuple[str, str, list[ImportedChapter]]:
    with zipfile.ZipFile(path) as archive:
        opf_path = _rootfile(archive)
        opf_dir = posixpath.dirname(opf_path)
        opf = ET.fromstring(archive.read(opf_path))
        title_node = opf.find(".//dc:title", OPF_NS)
        author_node = opf.find(".//dc:creator", OPF_NS)
        title = _text_content(title_node) if title_node is not None else path.stem
        author = _text_content(author_node) if author_node is not None else ""

        manifest: dict[str, tuple[str, str]] = {}
        for item in opf.findall(".//opf:manifest/opf:item", OPF_NS):
            item_id = item.get("id")
            href = item.get("href")
            if item_id and href:
                manifest[item_id] = (href, str(item.get("properties") or ""))

        chapters: list[ImportedChapter] = []
        for position, itemref in enumerate(opf.findall(".//opf:spine/opf:itemref", OPF_NS), start=1):
            manifest_item = manifest.get(str(itemref.get("idref")))
            if not manifest_item:
                continue
            href, properties = manifest_item
            if "nav" in properties.split() or posixpath.basename(href).lower() in {"nav.xhtml", "toc.xhtml", "toc.ncx"}:
                continue
            entry_path = posixpath.normpath(posixpath.join(opf_dir, href))
            try:
                root = ET.fromstring(archive.read(entry_path))
            except (KeyError, ET.ParseError):
                continue
            body = next((element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "body"), None)
            if body is None:
                continue
            heading = next(
                (_text_content(element) for element in body.iter() if element.tag.rsplit("}", 1)[-1] in {"h1", "h2", "h3"} and _text_content(element)),
                f"Chương {position}",
            )
            paragraphs = [
                _text_content(element)
                for element in body.iter()
                if element.tag.rsplit("}", 1)[-1] == "p" and _text_content(element)
            ]
            if not paragraphs:
                body_text = _text_content(body)
                if body_text and body_text != heading:
                    paragraphs = [body_text]
            if not paragraphs:
                continue
            href_match = re.search(r"(?i)(?:chap|chapter|chuong)[_-]?(\d+)", posixpath.basename(href))
            heading_match = re.search(r"(?i)chương\s+(\d+)", heading)
            number = int(href_match.group(1)) if href_match else (int(heading_match.group(1)) if heading_match else position)
            if heading_match and int(heading_match.group(1)) != number:
                heading = re.sub(r"(?i)(chương\s+)\d+", rf"\g<1>{number}", heading, count=1)
            chapters.append(ImportedChapter(number, heading, href, paragraphs))
        if not chapters:
            raise ValueError("Không tìm thấy chương có nội dung trong EPUB.")
        chapters.sort(key=lambda item: item.number)
        return title, author, chapters


def import_epub(path: Path, db: Database, store: ContentStore) -> dict:
    path = path.resolve()
    if not path.exists() or path.suffix.lower() != ".epub":
        raise FileNotFoundError(f"Không tìm thấy EPUB: {path}")
    digest = sha256_file(path)
    existing = db.fetch_one("SELECT * FROM books WHERE source_sha256=?", (digest,))
    if existing:
        return {"book_id": existing["id"], "created": False, "chapter_count": existing["chapter_count"]}

    title, author, chapters = parse_epub(path)
    now = utcnow()
    with db.transaction() as connection:
        cursor = connection.execute(
            "INSERT INTO books(title,author,source_path,source_sha256,chapter_count,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (title, author, str(path), digest, len(chapters), now, now),
        )
        book_id = int(cursor.lastrowid)
        for chapter in chapters:
            raw_text = "\n".join(chapter.paragraphs)
            validate_canonical_text(raw_text, field=f"Chapter {chapter.number} raw text")
            raw_path, raw_sha = store.put_text(raw_text)
            reflowed, import_issues = reflow_paragraphs(chapter.paragraphs, chapter.title)
            validate_canonical_text(reflowed, field=f"Chapter {chapter.number} reflowed text")
            reflow_path, reflow_sha = store.put_text(reflowed)
            chapter_cursor = connection.execute(
                "INSERT INTO chapters(book_id,chapter_number,title,source_href,char_count,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (book_id, chapter.number, chapter.title, chapter.href, len(reflowed), now, now),
            )
            chapter_id = int(chapter_cursor.lastrowid)
            raw_cursor = connection.execute(
                "INSERT INTO text_revisions(chapter_id,kind,content_path,content_sha256,lexical_sha256,char_count,processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (chapter_id, "raw", raw_path, raw_sha, lexical_sha256(raw_text), len(raw_text), "epub-extract-v1", "verified", now),
            )
            raw_revision_id = int(raw_cursor.lastrowid)
            reflow_cursor = connection.execute(
                "INSERT INTO text_revisions(chapter_id,parent_revision_id,kind,content_path,content_sha256,lexical_sha256,char_count,processor_version,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (chapter_id, raw_revision_id, "reflowed", reflow_path, reflow_sha, lexical_sha256(reflowed), len(reflowed), "lossless-reflow-v1", "approved", now),
            )
            reflow_revision_id = int(reflow_cursor.lastrowid)
            connection.execute(
                "UPDATE chapters SET raw_text_revision_id=?,active_text_revision_id=? WHERE id=?",
                (raw_revision_id, reflow_revision_id, chapter_id),
            )
            all_issues = import_issues + qa_text(reflowed)
            for issue in all_issues:
                connection.execute(
                    "INSERT INTO qa_issues(chapter_id,text_revision_id,code,severity,message,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (chapter_id, reflow_revision_id, issue.code, issue.severity, issue.message, __import__("json").dumps(issue.details, ensure_ascii=False), now),
                )
    db.audit("book_imported", details={"book_id": book_id, "title": title, "chapters": len(chapters), "sha256": digest})
    return {"book_id": book_id, "created": True, "chapter_count": len(chapters), "title": title, "author": author}
