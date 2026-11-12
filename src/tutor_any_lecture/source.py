"""source.json: where a unit's transcript came from, and file digests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

KINDS = ("local", "url", "platform", "transcript", "slides-only")
ACQUISITIONS = ("cc", "auto", "ocr", "asr", "import", "panopto", "slides")


@dataclass
class SourceInfo:
    kind: str
    title: str
    url: str | None
    platform: str | None
    duration: float | None
    lecture_language: str | None
    acquisition: str
    health: dict
    tool_versions: dict
    inputs_sha256: dict
    lecture_date: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}; got {self.kind!r}")
        if self.acquisition not in ACQUISITIONS:
            raise ValueError(f"acquisition must be one of {', '.join(ACQUISITIONS)}; got {self.acquisition!r}")

    def write(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(dataclasses.asdict(self), ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")

    @classmethod
    def read(cls, path: Path) -> SourceInfo:
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
