"""Local media (a video or audio file on disk) to a transcript, through ASR."""

from __future__ import annotations

import dataclasses
import importlib.metadata
import shutil
import sys
import tempfile
from pathlib import Path

from tutor_any_lecture import asr, slides

from ..ffmpeg import extract_audio, media_duration
from ..profile import Profile
from ..source import SourceInfo, sha256_file
from ..transcript import EmptyTranscript, Health, health
from ..unit import UnitPaths

def _refuse_overwrite(unit: Path, force: bool) -> None:
    transcript = UnitPaths(unit).transcript
    # Keyed on transcript.json only: a slides-only source.json may be replaced freely.
    if transcript.exists() and not force:
        raise FileExistsError(f"{transcript} already exists; rerun with --force to replace it")


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist or is not a file")


def transcribe_audio(
    audio: Path,
    unit: Path,
    profile: Profile,
    force: bool,
    budget_minutes: float | None = None,
    backend: str | None = None,
    model: str | None = None,
) -> Health:
    """Transcribe ``audio`` as it is (no extraction) into the unit."""
    _refuse_overwrite(unit, force)
    audio = Path(audio)
    _require_file(audio)
    return _transcribe_into_unit(audio, audio, unit, profile, budget_minutes, backend, model)


def acquire_local(
    file: Path,
    unit: Path,
    profile: Profile,
    force: bool,
    budget_minutes: float | None = None,
) -> Health:
    """Extract ``file``'s audio to a temp folder, transcribe it into the unit, delete the audio."""
    _refuse_overwrite(unit, force)
    file = Path(file)
    _require_file(file)
    # Before the extraction, so a missing backend costs no audio work.
    backend, model = asr.resolve_backend()
    # Outside the unit and the user's folder, and removed also when transcription fails.
    tmp = Path(tempfile.mkdtemp(prefix="tutor-any-lecture-"))
    try:
        wav = tmp / "audio.wav"
        extract_audio(file, wav)
        return _transcribe_into_unit(wav, file, unit, profile, budget_minutes, backend, model)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if tmp.exists():
            print(f"warning: could not delete the temporary folder {tmp}; delete it by hand", file=sys.stderr)


def _transcribe_into_unit(
    audio: Path,
    origin: Path,
    unit: Path,
    profile: Profile,
    budget_minutes: float | None,
    backend: str | None,
    model: str | None,
) -> Health:
    """Transcribe ``audio``; write transcript.json and source.json describing ``origin``."""
    duration = media_duration(origin)
    language = None if profile.lecture_language == "auto" else profile.lecture_language
    prompt = slides.slide_terms(slides.load_pages(unit))
    budget = asr.default_budget_minutes(duration) if budget_minutes is None else budget_minutes
    name, model = asr.resolve_backend(backend, model)

    transcript = asr.transcribe(audio, language, prompt, budget, backend=name, model=model)
    if not transcript.segments:
        raise EmptyTranscript("no timed segments found")

    h = health(transcript.segments, duration)
    paths = UnitPaths(unit).ensure()
    paths.transcript.write_text(transcript.to_json(), encoding="utf-8", newline="\n")
    SourceInfo(
        kind="local",
        title=origin.stem,
        url=None,
        platform=None,
        duration=duration,
        lecture_language=transcript.language,
        acquisition="asr",
        health=dataclasses.asdict(h),
        tool_versions=_tool_versions(name, model, getattr(transcript, "device", None)),
        inputs_sha256={origin.name: sha256_file(origin)},
    ).write(paths.source)
    return h


def _tool_versions(name: str, model: str | None, device: str | None) -> dict:
    # device: what asr.transcribe reports (an AsrTranscript); None for any other transcript.
    versions = {"asr_backend": name, "asr_model": model, "asr_device": device}
    package = asr.BACKEND_PACKAGES.get(name)
    if package is not None:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    return versions
