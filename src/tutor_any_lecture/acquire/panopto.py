"""Turn the output of ``panopto_extract.js`` into transcript.json, chapters.json and source.json."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from .. import __version__
from ..source import SourceInfo, sha256_file
from ..transcript import EmptyTranscript, Health, Transcript, health, parse_stamped_txt
from ..unit import UnitPaths

_LINE_STAMP = re.compile(r"^\[(\d+:\d{2}(?::\d{2})?)\]", flags=re.M)
_CHAPTER = re.compile(r"^(.*\S)\s+(\d+:\d{2}(?::\d{2})?)$")
_LECTURE_DATE = re.compile(r"\((\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})")
_RETRY_CANCEL = "Retry Cancel "


def _stamp_seconds(stamp: str) -> float:
    """``m:ss`` or ``h:mm:ss`` to seconds."""
    parts = [int(p) for p in stamp.split(":")]
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    return float(parts[0] * 3600 + parts[1] * 60 + parts[2])


def _decode_first(text: str):
    """Decode the first JSON value in ``text``; whatever follows it is ignored."""
    value, _ = json.JSONDecoder().raw_decode(text.lstrip())
    return value


def load_extract(path: Path) -> dict:
    """Read an extract: plain JSON, or a tool-results wrapper ``[{"type":"text","text":"<json>"}]``
    followed by trailing data. Raises ``ValueError`` when the content is not a JSON object."""
    path = Path(path)
    value = _decode_first(path.read_bytes().decode("utf-8-sig"))
    if isinstance(value, list) and value and isinstance(value[0], dict) and isinstance(value[0].get("text"), str):
        value = value[0]["text"]
    # The payload may itself be JSON text, sometimes encoded twice.
    for _ in range(2):
        if not isinstance(value, str):
            break
        value = _decode_first(value)
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a Panopto extract: expected a JSON object")
    return value


def _duration(text: str) -> float | None:
    """The last stamp at the start of a line, in seconds; None when there is none or it is 0.

    The extract's own ``duration`` field shows the player's remaining time, so it is never used.
    """
    stamps = _LINE_STAMP.findall(text)
    if not stamps:
        return None
    seconds = _stamp_seconds(stamps[-1])
    return seconds or None


def _chapters(contents) -> list[dict]:
    """Chapters from the extract's ``contents``; a non-list counts as empty, non-strings are skipped."""
    if not isinstance(contents, list):
        return []
    chapters: list[dict] = []
    for raw in contents:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if s.startswith(_RETRY_CANCEL):
            s = s[len(_RETRY_CANCEL):]
        s = s.strip()
        if not s:
            continue
        m = _CHAPTER.match(s)
        if m:
            chapters.append({"title": m.group(1), "start": _stamp_seconds(m.group(2))})
        else:
            chapters.append({"title": s, "start": None})
    return chapters


def _lecture_date(details: str) -> str | None:
    m = _LECTURE_DATE.search(details)
    return f"{m.group(1)} {m.group(2)}" if m else None


def import_panopto(extract: Path, unit: Path, force: bool) -> Health:
    extract = Path(extract)
    paths = UnitPaths(unit)
    # The guard comes first, before the extract is read; it keys on transcript.json only,
    # so a slides-only unit (source.json without transcript.json) is replaced.
    if paths.transcript.exists() and not force:
        raise FileExistsError(f"{paths.transcript} already exists; rerun with --force to replace it")

    d = load_extract(extract)
    text = d["transcript"] if isinstance(d.get("transcript"), str) else ""
    # One duration value goes to the parser, to health() and into source.json.
    duration = _duration(text)
    segments = parse_stamped_txt(text, duration)
    if not segments:
        raise EmptyTranscript("no timed segments found")

    h = health(segments, duration)
    paths.ensure()
    paths.transcript.write_text(Transcript(segments, None).to_json(), encoding="utf-8", newline="\n")
    chapters = _chapters(d.get("contents", []))
    details = d.get("details") if isinstance(d.get("details"), str) else ""
    paths.chapters.write_text(json.dumps(chapters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    SourceInfo(
        kind="platform",
        title=d.get("title") or "",
        url=d.get("url") or None,
        platform="panopto",
        duration=duration,
        lecture_language=None,
        acquisition="panopto",
        health=dataclasses.asdict(h),
        tool_versions={"tutor-any-lecture": __version__},
        inputs_sha256={extract.name: sha256_file(extract)},
        lecture_date=_lecture_date(details),
    ).write(paths.source)
    return h
