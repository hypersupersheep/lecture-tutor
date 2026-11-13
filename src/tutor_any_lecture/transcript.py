"""The transcript contract: segments, transcript.json, the input parsers and the health check."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .plan import read_json


class EmptyTranscript(ValueError):
    """An input file held no timed segment."""


class AcquireError(RuntimeError):
    """An input could not be read, or an external tool or ASR backend failed."""


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[dict] | None = None


@dataclass
class Transcript:
    segments: list[Segment]
    language: str | None

    def to_json(self) -> str:
        """The exact text of transcript.json."""
        segments = []
        for s in self.segments:
            d = {"start": s.start, "end": s.end, "text": s.text}
            if s.words is not None:
                d["words"] = s.words
            segments.append(d)
        return json.dumps({"language": self.language, "segments": segments}, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, path: Path) -> Transcript:
        """Read transcript.json. A missing key or a wrong type raises ValueError("transcript.json: …")."""
        data = read_json(path, "transcript.json")
        if not isinstance(data, dict) or "segments" not in data or "language" not in data:
            raise ValueError('transcript.json: the top level must be an object with "language" and "segments"')
        if not isinstance(data["language"], (str, type(None))):
            raise ValueError(f"transcript.json: language must be text or null, got {data['language']!r}")
        if not isinstance(data["segments"], list):
            raise ValueError("transcript.json: segments must be a list")
        segments = [_segment(d, n) for n, d in enumerate(data["segments"])]
        return cls(segments, data["language"])

    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _segment(d, n: int) -> Segment:
    where = f"transcript.json: segment {n}"
    if not isinstance(d, dict):
        raise ValueError(f"{where} is not an object")
    missing = [k for k in ("start", "end", "text") if k not in d]
    if missing:
        raise ValueError(f"{where} is missing {', '.join(missing)}")
    if not (_is_number(d["start"]) and _is_number(d["end"])):
        raise ValueError(f"{where}: start and end must be numbers")
    if not isinstance(d["text"], str):
        raise ValueError(f"{where}: text must be text, got {d['text']!r}")
    words = d.get("words")
    if words is not None and not isinstance(words, list):
        raise ValueError(f"{where}: words must be a list or null")
    return Segment(d["start"], d["end"], d["text"], words)


def primary_subtag(code: str | None) -> str | None:
    """"en-orig" -> "en", "zh-Hans" -> "zh"; None, "" and "auto" -> None."""
    if not code:
        return None
    tag = code.strip().lower().replace("_", "-").split("-")[0]
    if not tag or tag == "auto":
        return None
    return tag


# --- text input -------------------------------------------------------------


def _normalise(text: str) -> str:
    """Strip one leading BOM and turn CRLF, then lone CR, into LF."""
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _collapse(text: str) -> str:
    return " ".join(text.split())


_TS = r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
_TIMING = re.compile(rf"\s*{_TS}\s*-->\s*{_TS}(?:\s+.*)?")
# Only real WebVTT tags; only v and lang take an annotation after a space, so "<c and y>" is text.
_VTT_TAG = re.compile(r"</?(?:c|i|b|u|ruby|rt)(?:\.[^\s>]+)?>|</?(?:v|lang)(?:\.[^\s>]+)?(?:[ \t][^>]*)?>")
_VTT_TIME_TAG = re.compile(r"<(\d+:)?\d{2}:\d{2}\.\d{3}>")


def _ms_to_seconds(h: str | None, m: str, s: str, ms: str) -> float:
    # Integer milliseconds divided once, so "00:00:03.010" is exactly 3.01.
    return (int(h or 0) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)) / 1000


def _blocks(text: str) -> list[list[str]]:
    """Blocks of lines; only a zero-length line ends one (a space-only line is payload)."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in _normalise(text).split("\n"):
        if line == "":
            if current:
                blocks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _read_cues(text: str, clean=None) -> list[Segment]:
    """The cue reader shared by SRT and VTT. ``clean`` removes format-specific tags."""
    segments: list[Segment] = []
    for block in _blocks(text):
        idx = next((i for i, line in enumerate(block) if "-->" in line), None)
        if idx is None:  # WEBVTT header, NOTE, STYLE, REGION
            continue
        m = _TIMING.fullmatch(block[idx])
        if m is None:
            continue
        start = _ms_to_seconds(*m.group(1, 2, 3, 4))
        end = _ms_to_seconds(*m.group(5, 6, 7, 8))
        payload = " ".join(block[idx + 1:])
        if clean is not None:
            payload = clean(payload)
        payload = _collapse(payload)
        if payload:
            segments.append(Segment(start, end, payload))
    return segments


def _clean_vtt(payload: str) -> str:
    # Entities are decoded after the tags are removed, so "&lt;i&gt;" stays as text.
    return html.unescape(_VTT_TIME_TAG.sub("", _VTT_TAG.sub("", payload)))


def parse_srt(text: str) -> list[Segment]:
    return _read_cues(text)


def parse_vtt(text: str) -> list[Segment]:
    return _read_cues(text, _clean_vtt)


_STAMP = re.compile(r"^\s*\[(\d+):(\d{2})(?::(\d{2}))?\]\s*(.*)$")


def parse_stamped_txt(text: str, duration: float | None) -> list[Segment]:
    """Lines like ``[m:ss] text`` or ``[h:mm:ss] text``; unstamped lines continue the previous one."""
    stamped: list[list] = []  # [start, text]
    for line in _normalise(text).split("\n"):
        m = _STAMP.match(line)
        if m:
            a, b, c, rest = m.groups()
            if c is None:
                start = float(int(a) * 60 + int(b))
            else:
                start = float(int(a) * 3600 + int(b) * 60 + int(c))
            stamped.append([start, rest])
        elif line.strip() and stamped:
            stamped[-1][1] += " " + line
    kept = [(start, _collapse(t)) for start, t in stamped if _collapse(t)]
    segments: list[Segment] = []
    for i, (start, t) in enumerate(kept):
        if i + 1 < len(kept):
            end = kept[i + 1][0]
        else:
            end = max(start, min(start + 5, duration or start + 5))
        segments.append(Segment(start, end, t))
    return segments


def parse_whisper_json(obj) -> list[Segment]:
    """Accepts ``{"segments": [...]}`` or a bare list of segment objects.

    Malformed input raises ``ValueError`` (never ``KeyError`` or ``TypeError``), so the
    CLI reports it as one error line. Items are counted from 1 in the messages.
    """
    items = obj.get("segments", []) if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        raise ValueError("expected a list of segments")
    segments: list[Segment] = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"segment {i} is not an object")
        text = item.get("text")
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            continue
        if item.get("start") is None or item.get("end") is None:
            raise ValueError(f"segment {i} has no start or end time")
        try:
            start, end = float(item["start"]), float(item["end"])
        except (TypeError, ValueError):
            raise ValueError(f"segment {i} has a start or end time that is not a number") from None
        segments.append(Segment(start, end, text, item.get("words")))
    return segments


# --- health -----------------------------------------------------------------


@dataclass
class Health:
    coverage: float
    repetition: float
    spots_ok: bool
    overrun: bool
    loop: bool
    ok: bool
    duration_known: bool


def health(segments: list[Segment], duration: float | None) -> Health:
    if not segments:
        return Health(
            coverage=0.0, repetition=0.0, spots_ok=False, overrun=False, loop=False, ok=False,
            duration_known=duration is not None,
        )

    norm = [" ".join(s.text.casefold().split()) for s in segments]
    repeats = 0
    run = longest = 1
    for prev, cur in zip(norm, norm[1:]):
        if cur == prev:
            repeats += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    repetition = repeats / len(segments)
    loop = longest >= 5

    duration_known = duration is not None and duration > 0
    if duration_known:
        coverage = (max(s.end for s in segments) - min(s.start for s in segments)) / duration
        spots_ok = all(
            any(abs(s.start - frac * duration) <= 60 for s in segments) for frac in (0.1, 0.5, 0.9)
        )
        overrun = any(s.end > duration + 2 for s in segments)
    else:
        coverage, spots_ok, overrun = 1.0, True, False

    ok = coverage >= 0.9 and repetition <= 0.5 and spots_ok and not overrun and not loop
    return Health(coverage, repetition, spots_ok, overrun, loop, ok, duration_known)
