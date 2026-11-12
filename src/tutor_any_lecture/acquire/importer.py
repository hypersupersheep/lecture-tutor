"""Import a transcript file the user already has (SRT, VTT, Whisper JSON or stamped text)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .. import __version__
from ..source import SourceInfo, sha256_file
from ..transcript import (
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


def import_transcript(file: Path, unit: Path, duration: float | None, force: bool) -> Health:
    file = Path(file)
    paths = UnitPaths(unit)
    # The guard comes first, before the input is read; it keys on transcript.json only.
    if paths.transcript.exists() and not force:
        raise FileExistsError(f"{paths.transcript} already exists; rerun with --force to replace it")

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
        inputs_sha256={file.name: sha256_file(file)},
    ).write(paths.source)
    return h
