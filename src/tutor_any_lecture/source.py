"""source.json: where a unit's transcript came from, and file digests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .plan import read_json

KINDS = ("local", "url", "platform", "transcript", "slides-only")
ACQUISITIONS = ("cc", "auto", "ocr", "asr", "import", "panopto", "slides")
# The JSON types of each field as read back from source.json; lecture_date may be left out.
_TEXT, _OPT_TEXT, _OPT_NUMBER, _MAPPING = (str,), (str, type(None)), (int, float, type(None)), (dict,)
FIELD_TYPES = {
    "kind": _TEXT, "title": _TEXT, "url": _OPT_TEXT, "platform": _OPT_TEXT, "duration": _OPT_NUMBER,
    "lecture_language": _OPT_TEXT, "acquisition": _TEXT, "health": _MAPPING, "tool_versions": _MAPPING,
    "inputs_sha256": _MAPPING, "lecture_date": _OPT_TEXT,
}


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
        """Read source.json. A missing key, an unknown key or a wrong type raises ValueError("source.json: …")."""
        data = read_json(path, "source.json")
        if not isinstance(data, dict):
            raise ValueError("source.json: the top level must be an object")
        missing = [k for k in FIELD_TYPES if k not in data and k != "lecture_date"]
        if missing:
            raise ValueError(f"source.json: missing key(s): {', '.join(missing)}")
        unknown = sorted(k for k in data if k not in FIELD_TYPES)
        if unknown:
            raise ValueError(f"source.json: unknown key(s): {', '.join(unknown)}")
        for key, value in data.items():
            # bool is a subclass of int, but true/false is not a duration.
            if isinstance(value, bool) or not isinstance(value, FIELD_TYPES[key]):
                raise ValueError(f"source.json: {key} has the wrong type: {value!r}")
        try:
            return cls(**data)
        except ValueError as e:
            raise ValueError(f"source.json: {e}") from None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
