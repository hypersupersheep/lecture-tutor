"""A public video URL to a transcript: captions first, then (only with consent) audio and ASR.

yt-dlp is used without cookies or credentials of any kind. Only audio is ever downloaded,
into a temp folder that is removed when the run ends, and never from a lecture-capture
or meeting platform: there only captions are used.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import yt_dlp

from tutor_any_lecture import asr, ffmpeg

from ..profile import PUBLIC_VIDEO_AUDIO_NOTICE, ConsentRequired, Profile, has_audio_consent
from ..slides import load_pages, slide_terms
from ..source import SourceInfo
from ..transcript import (
    AcquireError,
    EmptyTranscript,
    Health,
    Segment,
    Transcript,
    health,
    parse_srt,
    parse_vtt,
    primary_subtag,
)
from ..unit import UnitPaths
from .local import temp_dir

# Every options dict starts from these (through _opts), so yt-dlp writes nothing on stdout
# (the CLI prints exactly one JSON object there) and never expands a playlist.
_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "logtostderr": True,
    "noplaylist": True,
}
# The JavaScript runtimes yt-dlp may use for sites that need one; doctor accepts either.
# yt-dlp's own default enables deno only.
_JS_RUNTIMES = ("deno", "node")

# Extractor keys (compared without letter case, by prefix) of lecture-capture and meeting
# platforms. Their owners decide whether recordings may be downloaded, so audio is never
# fetched from them, whatever the profile says: only their captions are used.
CAPTURE_PLATFORMS = ("panopto", "kaltura", "mediasite", "echo360", "yuja", "opencast", "zoom")
CAPTURE_MESSAGE = (
    "this platform's recordings are not downloaded: use its captions, or a file its owner lets you download"
)



def _opts(**extra) -> dict:
    """A fresh options dict for one yt-dlp call (yt-dlp may edit the runtimes dict in place)."""
    return {**_BASE_OPTS, "js_runtimes": {name: {} for name in _JS_RUNTIMES}, **extra}


def is_capture_platform(info: dict) -> bool:
    """True when the extractor yt-dlp chose belongs to a lecture-capture or meeting platform."""
    key = (info.get("extractor_key") or info.get("extractor") or "").lower()
    return key.startswith(CAPTURE_PLATFORMS)


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

    A manual track ("cc") must match the target language; when the target is only a
    guess (``lecture_language`` is auto and the video declares no language), a lone
    manual track is used whatever its language. An automatic track ("auto") must not be
    a translation; the original-language track wins even when it differs from
    ``lecture_language``.
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
    if key is None and lecture_language == "auto" and not info_lang and len(subs) == 1:
        key = next(iter(subs))
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


def _reason(error: Exception) -> str:
    """yt-dlp's message on one line, without colour codes or a leading "ERROR: "."""
    text = " ".join(_ANSI.sub("", str(error)).split())
    return text[len("ERROR: "):] if text.startswith("ERROR: ") else text


def _try_caption(url: str, kind: str, lang: str, duration: float | None) -> tuple[list[Segment], Health] | None:
    """Download one caption track; return its segments and health (healthy or not).

    ``None`` when nothing usable came back: a download error, no caption file, no cues.
    """
    with temp_dir() as tmp:
        opts = _opts(
            skip_download=True,
            subtitleslangs=[lang],
            subtitlesformat="vtt",
            outtmpl=str(tmp / "%(id)s.%(ext)s"),
            # Exactly one of the two: with both, yt-dlp prefers the manual track,
            # and the fallback to the automatic one would fetch the broken track again.
            **{("writesubtitles" if kind == "cc" else "writeautomaticsub"): True},
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError:
            return None
        # VTT is asked for; a track that has no VTT form may still come back as SRT.
        vtt, srt = sorted(tmp.glob("*.vtt")), sorted(tmp.glob("*.srt"))
        if vtt:
            segments = parse_vtt(vtt[0].read_bytes().decode("utf-8-sig"))
        elif srt:
            segments = parse_srt(srt[0].read_bytes().decode("utf-8-sig"))
        else:
            return None
    if kind == "auto":
        segments = _unroll_auto(segments)
    if not segments:
        return None
    return segments, health(segments, duration)


def _asr_from_audio(
    url: str, unit: Path, profile: Profile, duration: float | None, budget_minutes: float | None
) -> Transcript:
    """Download the audio stream only, transcribe it, and delete it."""
    # Before the download: with no usable backend, BackendMissing is raised and nothing is fetched.
    backend, model = asr.resolve_backend()
    with temp_dir() as tmp:
        dl = tmp / "dl"
        # Audio only: no "/best" fallback that could select a stream with video.
        opts = _opts(format="bestaudio", outtmpl=str(dl / "%(id)s.%(ext)s"))
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
            asr.default_budget_minutes(duration) if budget_minutes is None else budget_minutes,
            backend=backend,
            model=model,
        )


# --- the adapter -------------------------------------------------------------


def acquire_url(
    url: str, unit: Path, profile: Profile, force: bool, budget_minutes: float | None = None
) -> Health:
    paths = UnitPaths(unit)
    # The guard comes first, before yt-dlp is touched; it keys on transcript.json only.
    if paths.transcript.exists() and not force:
        raise FileExistsError(f"{paths.transcript} already exists; rerun with --force to replace it")

    try:
        # "in_playlist": a playlist page comes back with its entries unresolved, so the
        # refusal below costs one request. Only this call; the downloads never list entries.
        with yt_dlp.YoutubeDL(_opts(extract_flat="in_playlist")) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise AcquireError(f"could not read the video page: {_reason(e)}") from e
    # Before any caption or audio download: one unit holds one video.
    if info.get("_type") == "playlist" or "entries" in info:
        raise AcquireError("this URL is a playlist; pass the URL of one video")
    duration = info.get("duration")

    # Caption rungs: the picked track, then (after a broken manual track) the
    # original-language automatic track. Each tried track is (kind, lang, segments, health).
    tried: list[tuple[str, str, list[Segment], Health]] = []
    pick = pick_caption(info, profile.lecture_language)
    if pick is not None:
        result = _try_caption(url, pick[0], pick[1], duration)
        if result is not None:
            tried.append((pick[0], pick[1], *result))
        if pick[0] == "cc" and not (tried and tried[-1][3].ok):
            pick = pick_caption({**info, "subtitles": {}}, profile.lecture_language)
            result = _try_caption(url, pick[0], pick[1], duration) if pick is not None else None
            if result is not None:
                tried.append((pick[0], pick[1], *result))
    healthy = [t for t in tried if t[3].ok]
    if healthy:
        kind, lang, segments, h = healthy[0]
        _write(paths, info, url, duration, Transcript(segments, primary_subtag(lang)), kind, h)
        return h

    # The audio rung, when it may run. Otherwise the best unhealthy track is kept and
    # reported (the command exits 1); with no track at all the learner must bring a file.
    capture = is_capture_platform(info)
    if capture or profile.public_video_audio != "on":
        if tried:
            kind, lang, segments, h = max(tried, key=lambda t: t[3].coverage)
            _write(paths, info, url, duration, Transcript(segments, primary_subtag(lang)), kind, h)
            return h
        raise NeedsUserFile(CAPTURE_MESSAGE if capture else None)
    if not has_audio_consent(profile):
        # Switched on by hand in profile.yaml, without the notice: show it now.
        raise ConsentRequired(PUBLIC_VIDEO_AUDIO_NOTICE)
    transcript = _asr_from_audio(url, unit, profile, duration, budget_minutes)
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
    versions = {"yt-dlp": yt_dlp.version.__version__}
    if acquisition == "asr":
        # The device asr.transcribe reports: "cuda", "cpu" or "mlx".
        versions["asr_device"] = getattr(transcript, "device", None)
    SourceInfo(
        kind="url",
        title=info.get("title") or url,
        url=url,
        platform=(info.get("extractor_key") or "").lower() or None,
        duration=duration,
        lecture_language=transcript.language,
        acquisition=acquisition,
        health=dataclasses.asdict(h),
        tool_versions=versions,
        inputs_sha256={},
    ).write(paths.source)
