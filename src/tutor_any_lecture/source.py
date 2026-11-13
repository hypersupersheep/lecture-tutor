"""source.json: where a unit's transcript came from, and file digests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def _is_slide_deck(name) -> bool:
    """An ``inputs_sha256`` key that names the slide deck: the PDF that ``slides --pdf`` read.

    No acquisition reads a PDF, so the suffix tells the deck's entry from the transcript's.
    """
    return isinstance(name, str) and name.lower().endswith(".pdf")


def slide_digests(path: Path) -> dict[str, str]:
    """The slide-deck entries of ``inputs_sha256`` in the source.json at ``path``.

    An acquisition that replaces source.json carries them over. A missing or unreadable
    file gives ``{}``: it is being replaced anyway.
    """
    try:
        data = read_json(path, "source.json")
    except (OSError, ValueError):
        return {}
    inputs = data.get("inputs_sha256") if isinstance(data, dict) else None
    if not isinstance(inputs, dict):
        return {}
    return {k: v for k, v in inputs.items() if _is_slide_deck(k) and isinstance(v, str)}


def add_slide_digest(path: Path, name: str, digest: str) -> None:
    """Record the slide deck ``name`` in an existing source.json; nothing else changes.

    An earlier deck's entry is replaced. A malformed file raises ``ValueError("source.json: …")``
    and is left as it is.
    """
    SourceInfo.read(path)  # validates; raises before anything is written
    data = read_json(path, "source.json")
    inputs = {k: v for k, v in data["inputs_sha256"].items() if not _is_slide_deck(k)}
    inputs[name] = digest
    data["inputs_sha256"] = inputs
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Query parameters that name a recording on the capture platforms (Panopto's id,
# YuJa's v, Kaltura's entry_id, ...); everything else in a query may be a token.
RECORDING_ID_PARAMS = ("id", "v", "vid", "mid", "entry_id", "entryid")


def url_without_tokens(url) -> str | None:
    """A lecture-capture address without what could grant access to it, for source.json.

    Scheme, host and path stay, with the recording-id query parameters only
    (``RECORDING_ID_PARAMS``, the first value of each, in address order): tokens, other
    parameters, a user name in the host and the fragment are dropped. ``None`` for an
    empty or non-text value.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urlsplit(url.strip())
    kept: dict[str, str] = {}
    for name, value in parse_qsl(parts.query):
        if name in RECORDING_ID_PARAMS and name not in kept:
            kept[name] = value
    query = urlencode(kept)
    host = parts.netloc.rpartition("@")[2]
    return urlunsplit((parts.scheme, host, parts.path, query, ""))
