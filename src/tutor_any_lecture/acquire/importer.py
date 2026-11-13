"""Import a transcript file the user already has (SRT, VTT, Whisper JSON or stamped text)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .. import __version__, ffmpeg
from ..source import SourceInfo, sha256_file, slide_digests
from ..transcript import (
    AcquireError,
    EmptyTranscript,
    Health,
    Transcript,
    health,
    parse_srt,
    parse_stamped_txt,
    parse_vtt,
    parse_whisper_json,
)
from ..unit import UnitPaths
from .local import refuse_overwrite


def _media_seconds(media: Path) -> float:
    """The duration of the lecture recording ``media``, read with ffmpeg."""
    if not media.is_file():
        raise FileNotFoundError(f"{media} does not exist or is not a file")
    seconds = ffmpeg.media_duration(media)
    if seconds is None or seconds <= 0:
        raise AcquireError(f"could not read a duration from {media.name}; pass --duration instead")
    return seconds


def import_transcript(
    file: Path, unit: Path, duration: float | None, force: bool, media: Path | None = None
) -> Health:
    """Import ``file`` into the unit. ``media``, the lecture's recording, gives the duration."""
    file = Path(file)
    paths = UnitPaths(unit)
    # The guard comes first, before the input is read; it keys on transcript.json only.
    refuse_overwrite(unit, force)
    if media is not None:
        if duration is not None:
            raise ValueError("give the duration or a media file, not both")
        duration = _media_seconds(Path(media))

    text = file.read_bytes().decode("utf-8-sig")
    suffix = file.suffix.lower()
    if suffix == ".srt":
        segments = parse_srt(text)
    elif suffix == ".vtt":
        segments = parse_vtt(text)
    elif suffix == ".json":
        segments = parse_whisper_json(json.loads(text))
    else:
        segments = parse_stamped_txt(text, duration)
    if not segments:
        raise EmptyTranscript("no timed segments found")

    h = health(segments, duration)
    paths.ensure()
    # An import never claims a language, also when a Whisper JSON file names one.
    paths.transcript.write_text(Transcript(segments, None).to_json(), encoding="utf-8", newline="\n")
    SourceInfo(
        kind="transcript",
        title=file.stem,
        url=None,
        platform=None,
        duration=duration,
        lecture_language=None,
        acquisition="import",
        health=dataclasses.asdict(h),
        tool_versions={"tutor-any-lecture": __version__},
        inputs_sha256={**slide_digests(paths.source), file.name: sha256_file(file)},
    ).write(paths.source)
    return h
