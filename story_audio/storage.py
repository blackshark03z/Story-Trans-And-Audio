from __future__ import annotations

from pathlib import Path

from .config import Settings
from .files import atomic_write_text, sha256_text


class ContentStore:
    def __init__(self, config: Settings):
        self.config = config

    def put_text(self, text: str) -> tuple[str, str]:
        digest = sha256_text(text)
        relative = Path("text") / digest[:2] / f"{digest}.txt"
        target = self.config.blobs_dir / relative
        if not target.exists():
            atomic_write_text(target, text)
        return str(relative.as_posix()), digest

    def read_text(self, relative_path: str) -> str:
        path = (self.config.blobs_dir / Path(relative_path)).resolve()
        root = self.config.blobs_dir.resolve()
        if root not in path.parents:
            raise ValueError("Invalid content path")
        return path.read_text(encoding="utf-8")

    def absolute(self, relative_path: str) -> Path:
        path = (self.config.blobs_dir / Path(relative_path)).resolve()
        if self.config.blobs_dir.resolve() not in path.parents:
            raise ValueError("Invalid content path")
        return path
