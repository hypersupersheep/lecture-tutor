"""A public video URL to a transcript: captions first, then (only with consent) audio and ASR.

yt-dlp is used without cookies or credentials of any kind. Only audio is ever downloaded,
into a temp folder that is removed when the run ends.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import yt_dlp

from tutor_any_lecture import asr, ffmpeg

from ..profile import Profile
from ..slides import load_pages, slide_terms
from ..source import SourceInfo
from ..transcript import (
    AcquireError,
    EmptyTranscript,
    Health,
    Segment,
    Transcript,
    health,
    parse_vtt,
    primary_subtag,
)
from ..unit import UnitPaths

# Every options dict starts from these, so yt-dlp writes nothing on stdout
# (the CLI prints exactly one JSON object there) and never expands a playlist.
_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "logtostderr": True,
    "noplaylist": True,
}

# Colour codes yt-dlp may put around "ERROR:" when stderr is a terminal.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class NeedsUserFile(Exception):
    """No usable captions, and no audio may or can be downloaded."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "No usable captions for this video. Ways forward: provide the video or audio file, "
            "provide a transcript file, or enable public_video_audio in the profile."
        )


# --- caption choice ----------------------------------------------------------


def _match(wanted: str, keys) -> str | None:
    """The key equal to ``wanted``, else the first key (sorted) with the same primary subtag."""
    keys = list(keys)
    if wanted in keys:
        return wanted
    tag = primary_subtag(wanted)
    if tag is None:
        return None
    for key in sorted(keys):
        if primary_subtag(key) == tag:
            return key
    return None


def _is_translation(entries) -> bool:
    # YouTube serves machine translations of the original track with a tlang parameter.
    return any("tlang" in parse_qs(urlsplit(e.get("url") or "").query) for e in entries or [])


def _track_url(entries) -> str:
    entries = entries or []
    for e in entries:
        if e.get("ext") == "vtt":
            return e.get("url") or ""
    return (entries[0].get("url") or "") if entries else ""


def pick_caption(info: dict, lecture_language: str) -> tuple[str, str, str] | None:
    """Choose a caption track as ``(kind, lang, url)``; ``None`` when nothing fits.

    A manual track ("cc") must match the target language. An automatic track ("auto")
    must not be a translation; the original-language track wins even when it differs
    from ``lecture_language``.
    """
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    info_lang = info.get("language")

    if lecture_language != "auto":
        target = lecture_language
    elif info_lang:
        target = info_lang
    else:
        origs = [k for k in auto if k.endswith("-orig")]
        target = origs[0][: -len("-orig")] if len(origs) == 1 else "en"

    key = _match(target, subs.keys())
    if key is not None:
        return ("cc", key, _track_url(subs[key]))

    originals = {k: v for k, v in auto.items() if not _is_translation(v)}
    key = f"{target}-orig"
    if key not in originals:
        key = _match(info_lang, originals.keys()) if info_lang else None
    if key is not None:
        return ("auto", key, _track_url(originals[key]))
    return None


def _unroll_auto(segments: list[Segment]) -> list[Segment]:
    """Remove the repeats of YouTube's rolling automatic captions.

    Each cue loses the longest leading run of words that equals a trailing run of the
    preceding input cue (before that cue's own trimming); cues left empty are dropped.
    """
    out: list[Segment] = []
    prev: list[str] | None = None
    for seg in segments:
        words = seg.text.split()
        rest = words
        if prev is not None:
            for k in range(min(len(words), len(prev)), 0, -1):
                if words[:k] == prev[-k:]:
                    rest = words[k:]
                    break
        if rest:
            out.append(Segment(seg.start, seg.end, " ".join(rest)))
        prev = words
    return out


# --- yt-dlp calls ------------------------------------------------------------


@contextmanager
def _temp_dir():
    # Outside the unit and the user's folders; removed also when the body raises.
    tmp = Path(tempfile.mkdtemp(prefix="tutor-any-lecture-"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if tmp.exists():
            print(f"warning: could not delete the temporary folder {tmp}; delete it by hand", file=sys.stderr)


def _reason(error: Exception) -> str:
    """yt-dlp's message on one line, without colour codes or a leading "ERROR: "."""
    text = " ".join(_ANSI.sub("", str(error)).split())
    return text[len("ERROR: "):] if text.startswith("ERROR: ") else text


def _try_caption(url: str, kind: str, lang: str, duration: float | None) -> tuple[list[Segment], Health] | None:
    """Download one caption track; return its segments and health, or ``None`` if it is unusable."""
    with _temp_dir() as tmp:
        opts = {
            **_BASE_OPTS,
            "skip_download": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "outtmpl": str(tmp / "%(id)s.%(ext)s"),
            # Exactly one of the two: with both, yt-dlp prefers the manual track,
            # and the fallback to the automatic one would fetch the broken track again.
            ("writesubtitles" if kind == "cc" else "writeautomaticsub"): True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError:
            return None
        files = sorted(tmp.glob("*.vtt"))
        if not files:
            return None
        segments = parse_vtt(files[0].read_bytes().decode("utf-8-sig"))
    if kind == "auto":
        segments = _unroll_auto(segments)
    if not segments:
        return None
    h = health(segments, duration)
    return (segments, h) if h.ok else None


def _asr_from_audio(url: str, unit: Path, profile: Profile, duration: float | None) -> Transcript:
    """Download the audio stream only, transcribe it, and delete it."""
    with _temp_dir() as tmp:
        dl = tmp / "dl"
        opts = {
            **_BASE_OPTS,
            # Audio only: no "/best" fallback that could select a stream with video.
            "format": "bestaudio",
            "outtmpl": str(dl / "%(id)s.%(ext)s"),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError:
            raise NeedsUserFile() from None
        files = sorted(p for p in dl.iterdir() if p.is_file()) if dl.is_dir() else []
        if not files:
            raise NeedsUserFile()
        # Outside dl/, so it cannot collide with a download that is itself a .wav.
        wav = tmp / "audio.wav"
        ffmpeg.extract_audio(files[0], wav)
        language = None if profile.lecture_language == "auto" else profile.lecture_language
        return asr.transcribe(
            wav,
            language,
            slide_terms(load_pages(unit)),
            asr.default_budget_minutes(duration),
        )


# --- the adapter -------------------------------------------------------------


def acquire_url(url: str, unit: Path, profile: Profile, force: bool) -> Health:
    paths = UnitPaths(unit)
    # The guard comes first, before yt-dlp is touched; it keys on transcript.json only.
    if paths.transcript.exists() and not force:
        raise FileExistsError(f"{paths.transcript} already exists; rerun with --force to replace it")

    try:
        with yt_dlp.YoutubeDL(dict(_BASE_OPTS)) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise AcquireError(f"could not read the video page: {_reason(e)}") from e
    # Before any caption or audio download: one unit holds one video.
    if info.get("_type") == "playlist" or "entries" in info:
        raise AcquireError("this URL is a playlist; pass the URL of one video")
    duration = info.get("duration")

    pick = pick_caption(info, profile.lecture_language)
    result = _try_caption(url, pick[0], pick[1], duration) if pick is not None else None
    if result is None and pick is not None and pick[0] == "cc":
        # A broken manual track falls back once to the original-language automatic track.
        pick = pick_caption({**info, "subtitles": {}}, profile.lecture_language)
        result = _try_caption(url, pick[0], pick[1], duration) if pick is not None else None
    if result is not None:
        kind, lang, _ = pick
        segments, h = result
        _write(paths, info, url, duration, Transcript(segments, primary_subtag(lang)), kind, h)
        return h

    if profile.public_video_audio != "on":
        raise NeedsUserFile()
    transcript = _asr_from_audio(url, unit, profile, duration)
    if not transcript.segments:
        raise EmptyTranscript("no timed segments found")
    h = health(transcript.segments, duration)
    _write(paths, info, url, duration, transcript, "asr", h)
    return h


def _write(
    paths: UnitPaths,
    info: dict,
    url: str,
    duration: float | None,
    transcript: Transcript,
    acquisition: str,
    h: Health,
) -> None:
    paths.ensure()
    paths.transcript.write_text(transcript.to_json(), encoding="utf-8", newline="\n")
    SourceInfo(
        kind="url",
        title=info.get("title") or url,
        url=url,
        platform=(info.get("extractor_key") or "").lower() or None,
        duration=duration,
        lecture_language=transcript.language,
        acquisition=acquisition,
        health=dataclasses.asdict(h),
        tool_versions={"yt-dlp": yt_dlp.version.__version__},
        inputs_sha256={},
    ).write(paths.source)
