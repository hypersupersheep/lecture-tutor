import copy
import json
import shutil
import types
import wave
from pathlib import Path

import pytest
import yt_dlp

from tutor_any_lecture import asr
from tutor_any_lecture.acquire import local as local_module
from tutor_any_lecture.acquire import url as url_module
from tutor_any_lecture.acquire.url import NeedsUserFile, _unroll_auto, acquire_url, pick_caption
from tutor_any_lecture.cli import main
from tutor_any_lecture.profile import Profile
from tutor_any_lecture.transcript import AcquireError, Segment, Transcript, parse_vtt
from tutor_any_lecture.unit import UnitPaths

BANNED = {"cookiefile", "cookiesfrombrowser", "username", "allow_unplayable_formats"}


# ---- local helpers ---------------------------------------------------------

def orig():
    """One original-language track entry (no tlang)."""
    return {"ext": "vtt", "url": "https://y/api/timedtext?v=x&fmt=vtt"}


def tl(lang):
    """One auto-translated track entry: its URL carries tlang."""
    return {"ext": "vtt", "url": f"https://y/api/timedtext?v=x&fmt=vtt&tlang={lang}"}


def info(subs=None, auto=None, lang=None, duration=600.0):
    return {
        "id": "vid",
        "title": "Synthetic lecture",
        "extractor_key": "Youtube",
        "duration": duration,
        "language": lang,
        "subtitles": subs or {},
        "automatic_captions": auto or {},
    }


def _ts(sec):
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}.000"


def make_vtt(n, step=10, length=9):
    """n cues; cue i runs from i*step to i*step+length seconds with the text 'line i'."""
    out = ["WEBVTT", ""]
    for i in range(n):
        out += [f"{_ts(i * step)} --> {_ts(i * step + length)}", f"line {i}", ""]
    return "\n".join(out)


GOOD_VTT = make_vtt(60)   # healthy for a 600 s video
SHORT_VTT = make_vtt(6)   # ends at 59 s of 600 s: fails health

# YouTube automatic-caption shape: a single-space payload line, <c> and
# timestamp tags, 10 ms filler cues, two-line rolling cues. Built from a list
# so the single-space lines survive editors.
YT_AUTO_VTT = "\n".join([
    "WEBVTT",
    "Kind: captions",
    "Language: en",
    "",
    "00:00:00.160 --> 00:00:02.389 align:start position:0%",
    " ",
    "hello<00:00:00.480><c> and</c><00:00:00.960><c> welcome</c><00:00:01.440><c> back</c>",
    "",
    "00:00:02.389 --> 00:00:02.399 align:start position:0%",
    "hello and welcome back",
    " ",
    "",
    "00:00:02.399 --> 00:00:04.710 align:start position:0%",
    "hello and welcome back",
    "today<00:00:02.880><c> we</c><00:00:03.360><c> study</c><00:00:03.840><c> graphs</c>",
    "",
    "00:00:04.710 --> 00:00:04.720 align:start position:0%",
    "today we study graphs",
    " ",
    "",
    "00:00:04.720 --> 00:00:07.000 align:start position:0%",
    "today we study graphs",
    "first<00:00:05.200><c> the</c><00:00:05.680><c> shortest</c><00:00:06.160><c> path</c>",
    "",
    "00:00:07.000 --> 00:00:07.010 align:start position:0%",
    "first the shortest path",
    " ",
    "",
])


class _FakeYDL:
    """Stands in for yt_dlp.YoutubeDL. State lives on the class; _install makes a fresh subclass per test."""

    info = {}
    info_error = None      # an exception the metadata call raises, or None
    captions = {}          # {(kind, key): vtt text}; kind is "cc" or "auto"
    caption_errors = set() # (kind, key) whose download raises DownloadError
    audio_error = False
    all_opts = []          # the options dict of every instance, in creation order
    last_opts = None       # == all_opts[-1]
    downloads = []         # paths of audio files written
    caption_requests = []  # (kind, key) of every caption download
    folders = []           # every folder a download was asked to write into

    def __init__(self, params=None, *args, **kwargs):
        self.params = dict(params or {})
        type(self).all_opts.append(self.params)
        type(self).last_opts = self.params

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True, **kwargs):
        assert download is False, "the metadata call must pass download=False"
        if type(self).info_error is not None:
            raise type(self).info_error
        return copy.deepcopy(type(self).info)

    def download(self, url_list):
        cls = type(self)
        out = self.params["outtmpl"]
        folder = Path(out["default"] if isinstance(out, dict) else out).parent
        cls.folders.append(folder)
        folder.mkdir(parents=True, exist_ok=True)
        if self.params.get("skip_download"):
            want_cc = bool(self.params.get("writesubtitles"))
            want_auto = bool(self.params.get("writeautomaticsub"))
            assert want_cc != want_auto, "set exactly one of writesubtitles / writeautomaticsub"
            assert self.params.get("subtitlesformat") == "vtt"
            kind = "cc" if want_cc else "auto"
            for key in self.params["subtitleslangs"]:
                cls.caption_requests.append((kind, key))
                if (kind, key) in cls.caption_errors:
                    raise yt_dlp.utils.DownloadError(f"ERROR: Unable to download video subtitles for {key!r}")
                text = cls.captions.get((kind, key))
                if text is not None:
                    (folder / f"vid.{key}.vtt").write_text(text, encoding="utf-8", newline="\n")
            return 0
        if cls.audio_error:
            raise yt_dlp.utils.DownloadError("Requested format is not available")
        path = folder / "vid.wav"
        with wave.open(str(path), "wb") as w:  # a real WAV, so the real extract_audio can read it
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 3200)  # 0.2 s of silence
        cls.downloads.append(str(path))
        return 0


def _install(monkeypatch, info_dict, captions=None, audio_error=False, info_error=None, caption_errors=()):
    class Fake(_FakeYDL):
        pass

    Fake.info = info_dict
    Fake.info_error = info_error
    Fake.captions = dict(captions or {})
    Fake.caption_errors = set(caption_errors)
    Fake.audio_error = audio_error
    Fake.all_opts, Fake.downloads, Fake.caption_requests, Fake.folders = [], [], [], []
    Fake.last_opts = None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", Fake)
    return Fake


@pytest.fixture
def fake_ydl(monkeypatch):
    """A 600 s video with one healthy manual English track."""
    return _install(monkeypatch, info(subs={"en": [orig()]}, lang="en"), {("cc", "en"): GOOD_VTT})


@pytest.fixture
def fake_ydl_no_caps(monkeypatch):
    """A 2400 s video with no caption tracks."""
    return _install(monkeypatch, info(lang="en", duration=2400.0))


@pytest.fixture
def fake_asr(monkeypatch):
    """Replaces asr.transcribe in-process: no child process, no model."""
    calls = []

    def fake(audio, language, initial_prompt, budget_minutes, backend=None, model=None):
        calls.append({
            "audio": str(audio),
            "audio_existed": Path(audio).exists(),
            "language": language,
            "initial_prompt": initial_prompt,
            "budget_minutes": budget_minutes,
        })
        return asr.AsrTranscript([Segment(i * 40.0, i * 40.0 + 39.0, f"line {i}") for i in range(60)], "en", device="mlx")

    fake.calls = calls
    monkeypatch.setattr(asr, "transcribe", fake)
    # acquire_url resolves the backend before any audio download; no real backend is needed here.
    monkeypatch.setattr(asr, "resolve_backend", lambda backend=None, model=None: ("fake", None))
    return fake


@pytest.fixture
def profile_on():
    return Profile(public_video_audio="on")


@pytest.fixture
def profile_off():
    return Profile()


def read_source(unit):
    return json.loads(UnitPaths(unit).source.read_text(encoding="utf-8"))


# ---- pick_caption ----------------------------------------------------------

def test_prefers_manual_cc():
    assert pick_caption(info(subs={"en": [orig()]}, auto={"en-orig": [orig()]}), "auto")[0] == "cc"


def test_never_picks_translated():
    i = info(lang="zh", auto={"en": [tl("en")], "zh-orig": [orig()]})
    assert pick_caption(i, "auto")[1] == "zh-orig"


def test_only_translated_means_none():
    assert pick_caption(info(lang="zh", auto={"en": [tl("en")]}), "auto") is None


def test_manual_other_language_means_none():
    assert pick_caption(info(subs={"fr": [orig()]}), "en") is None


def test_manual_regional_variant_matches():
    assert pick_caption(info(subs={"en-GB": [orig()]}), "en")[:2] == ("cc", "en-GB")


def test_auto_target_inferred_from_single_orig():
    i = info(auto={"ja-orig": [orig()], "en": [tl("en")]})
    assert pick_caption(i, "auto")[:2] == ("auto", "ja-orig")


def test_original_auto_track_wins_over_lecture_language():
    i = info(lang="zh", auto={"zh-orig": [orig()], "en": [tl("en")]})
    assert pick_caption(i, "en")[:2] == ("auto", "zh-orig")


# ---- _unroll_auto ----------------------------------------------------------

def test_auto_rolling_captions_unrolled():
    segs = _unroll_auto(parse_vtt(YT_AUTO_VTT))
    assert [s.text for s in segs] == [
        "hello and welcome back",
        "today we study graphs",
        "first the shortest path",
    ]
    assert [s.start for s in segs] == pytest.approx([0.16, 2.399, 4.72])
    assert [s.end for s in segs] == pytest.approx([2.389, 4.71, 7.0])
    assert all("<" not in s.text for s in segs)


# ---- acquire_url -----------------------------------------------------------

def test_no_cookies_ever(fake_ydl, tmp_path, profile_on):
    acquire_url("https://y/x", tmp_path, profile_on, False)
    assert not (BANNED & set(fake_ydl.last_opts))
    assert fake_ydl.all_opts and all(not (BANNED & set(o)) for o in fake_ydl.all_opts)


def test_switch_off_needs_user_file(fake_ydl_no_caps, tmp_path, profile_off):
    with pytest.raises(NeedsUserFile):
        acquire_url("https://y/x", tmp_path, profile_off, False)
    assert fake_ydl_no_caps.downloads == []
    assert not UnitPaths(tmp_path).transcript.exists()


def test_switch_on_downloads_audio_then_deletes(fake_ydl_no_caps, fake_asr, tmp_path, profile_on):
    acquire_url("https://y/x", tmp_path, profile_on, False)
    assert fake_ydl_no_caps.downloads and all(not Path(p).exists() for p in fake_ydl_no_caps.downloads)
    assert all(not f.exists() for f in fake_ydl_no_caps.folders)
    assert all(not (BANNED & set(o)) for o in fake_ydl_no_caps.all_opts)
    call = fake_asr.calls[0]
    assert call["audio_existed"] and not Path(call["audio"]).exists()
    assert call["language"] is None and call["initial_prompt"] == "" and call["budget_minutes"] == 80.0


def test_audio_format_is_bestaudio_only(fake_ydl_no_caps, fake_asr, tmp_path, profile_on):
    h = acquire_url("https://y/x", tmp_path, profile_on, False)
    assert fake_ydl_no_caps.last_opts["format"] == "bestaudio"
    assert all(o["format"] == "bestaudio" for o in fake_ydl_no_caps.all_opts if "format" in o)
    src = read_source(tmp_path)
    assert h.ok and (src["kind"], src["acquisition"], src["lecture_language"]) == ("url", "asr", "en")
    assert src["tool_versions"]["asr_device"] == "mlx"


def test_no_audio_only_format_needs_user_file(monkeypatch, fake_asr, tmp_path, profile_on):
    fake = _install(monkeypatch, info(lang="en"), audio_error=True)
    with pytest.raises(NeedsUserFile):
        acquire_url("https://y/x", tmp_path, profile_on, False)
    assert fake.downloads == [] and fake_asr.calls == []
    assert fake.folders and all(not f.exists() for f in fake.folders)
    assert not UnitPaths(tmp_path).transcript.exists()


def test_broken_cc_falls_back_to_auto(monkeypatch, tmp_path, profile_off):
    fake = _install(
        monkeypatch,
        info(subs={"en": [orig()]}, auto={"en-orig": [orig()], "fr": [tl("fr")]}, lang="en"),
        {("cc", "en"): SHORT_VTT, ("auto", "en-orig"): GOOD_VTT},
    )
    h = acquire_url("https://y/x", tmp_path, profile_off, False)
    src = read_source(tmp_path)
    assert h.ok and src["acquisition"] == "auto" and src["lecture_language"] == "en"
    assert fake.caption_requests == [("cc", "en"), ("auto", "en-orig")]
    assert fake.downloads == []
    assert all(not f.exists() for f in fake.folders)
    t = Transcript.from_json(UnitPaths(tmp_path).transcript)
    assert t.language == "en" and len(t.segments) == 60


def test_url_refuses_overwrite(fake_ydl, tmp_path, profile_off):
    unit = tmp_path / "课程 资料" / "第1周"
    acquire_url("https://y/x", unit, profile_off, False)
    before = UnitPaths(unit).transcript.read_bytes()
    n = len(fake_ydl.all_opts)
    with pytest.raises(FileExistsError):
        acquire_url("https://y/x", unit, profile_off, False)
    assert len(fake_ydl.all_opts) == n  # yt-dlp was not touched the second time
    assert UnitPaths(unit).transcript.read_bytes() == before
    assert acquire_url("https://y/x", unit, profile_off, True).ok  # force overwrites


# ---- CLI -------------------------------------------------------------------

def test_cli_url_ok(tmp_cfg, fake_ydl, tmp_path, capsys):
    unit = tmp_path / "unit"
    assert main(["acquire", "url", "--url", "https://y/x", "--unit", str(unit)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and out["health"]["ok"] is True
    src = read_source(unit)
    assert (src["kind"], src["acquisition"], src["lecture_language"], src["url"]) == ("url", "cc", "en", "https://y/x")
    assert all(o.get("quiet") for o in fake_ydl.all_opts)


def test_cli_url_needs_user_file(tmp_cfg, fake_ydl_no_caps, tmp_path, capsys):
    assert main(["acquire", "url", "--url", "https://y/x", "--unit", str(tmp_path / "unit")]) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "needs_user_file"
    assert all(w in out["message"] for w in ("file", "transcript", "public_video_audio"))
    assert fake_ydl_no_caps.downloads == []


# ---- hardening -------------------------------------------------------------

def test_metadata_failure_is_acquire_error(monkeypatch, fake_asr, tmp_path, profile_on):
    error = yt_dlp.utils.DownloadError("ERROR: [youtube] abc: Video unavailable")
    fake = _install(monkeypatch, info(), info_error=error)
    with pytest.raises(AcquireError) as exc:
        acquire_url("https://y/x", tmp_path, profile_on, False)
    message = str(exc.value)
    assert len(message.splitlines()) == 1
    assert "Video unavailable" in message and "ERROR:" not in message
    assert message == "could not read the video page: [youtube] abc: Video unavailable"
    assert fake.folders == [] and not UnitPaths(tmp_path).transcript.exists()


def test_metadata_failure_reason_is_one_line(monkeypatch, fake_asr, tmp_path, profile_on):
    error = yt_dlp.utils.DownloadError("\x1b[0;31mERROR:\x1b[0m [youtube] abc:   Private video.\n  Sign in   if granted access")
    _install(monkeypatch, info(), info_error=error)
    with pytest.raises(AcquireError) as exc:
        acquire_url("https://y/x", tmp_path, profile_on, False)
    assert str(exc.value) == "could not read the video page: [youtube] abc: Private video. Sign in if granted access"


def test_cli_url_metadata_failure_is_error_json(tmp_cfg, monkeypatch, tmp_path, capsys):
    error = yt_dlp.utils.DownloadError("ERROR: [youtube] abc: Video unavailable")
    _install(monkeypatch, info(), info_error=error)
    unit = tmp_path / "unit"
    assert main(["acquire", "url", "--url", "https://y/x", "--unit", str(unit)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["status"] == "error" and "Video unavailable" in obj["message"]
    assert not UnitPaths(unit).transcript.exists()


def test_playlist_url_is_refused(monkeypatch, fake_asr, tmp_path, profile_on):
    fake = _install(monkeypatch, {"_type": "playlist", "entries": [{"id": "a"}, {"id": "b"}]})
    with pytest.raises(AcquireError) as exc:
        acquire_url("https://y/playlist?list=x", tmp_path, profile_on, False)
    assert str(exc.value) == "this URL is a playlist; pass the URL of one video"
    assert fake.caption_requests == [] and fake.downloads == [] and fake.folders == []
    assert fake_asr.calls == []
    assert not UnitPaths(tmp_path).transcript.exists()


def test_entries_without_type_is_a_playlist(monkeypatch, fake_asr, tmp_path, profile_on):
    fake = _install(monkeypatch, {**info(subs={"en": [orig()]}, lang="en"), "entries": []})
    with pytest.raises(AcquireError, match="playlist"):
        acquire_url("https://y/x", tmp_path, profile_on, False)
    assert fake.folders == []


def test_auto_captions_are_unrolled_through_acquire_url(monkeypatch, tmp_path, profile_off):
    # YT_AUTO_VTT runs to 7 s, so a 7 s video keeps it healthy.
    _install(monkeypatch, info(auto={"en-orig": [orig()]}, lang="en", duration=7.0), {("auto", "en-orig"): YT_AUTO_VTT})
    assert acquire_url("https://y/x", tmp_path, profile_off, False).ok
    texts = [s.text for s in Transcript.from_json(UnitPaths(tmp_path).transcript).segments]
    assert texts == ["hello and welcome back", "today we study graphs", "first the shortest path"]
    assert all(a != b for a, b in zip(texts, texts[1:]))
    assert read_source(tmp_path)["acquisition"] == "auto"


def test_caption_download_error_falls_back_to_auto(monkeypatch, tmp_path, profile_off):
    fake = _install(
        monkeypatch,
        info(subs={"en": [orig()]}, auto={"en-orig": [orig()]}, lang="en"),
        {("cc", "en"): GOOD_VTT, ("auto", "en-orig"): GOOD_VTT},
        caption_errors={("cc", "en")},
    )
    assert acquire_url("https://y/x", tmp_path, profile_off, False).ok
    assert fake.caption_requests == [("cc", "en"), ("auto", "en-orig")]
    assert read_source(tmp_path)["acquisition"] == "auto"
    assert all(not f.exists() for f in fake.folders)


def test_missing_vtt_file_falls_back_to_auto(monkeypatch, tmp_path, profile_off):
    # No text for ("cc", "en"): the manual download writes no .vtt file.
    fake = _install(
        monkeypatch,
        info(subs={"en": [orig()]}, auto={"en-orig": [orig()]}, lang="en"),
        {("auto", "en-orig"): GOOD_VTT},
    )
    assert acquire_url("https://y/x", tmp_path, profile_off, False).ok
    assert fake.caption_requests == [("cc", "en"), ("auto", "en-orig")]
    assert read_source(tmp_path)["acquisition"] == "auto"


def test_undeletable_temp_warns_on_stderr(monkeypatch, fake_ydl, tmp_path, profile_off, capsys):
    # rmtree does nothing, but only where the shared temp-folder helper (acquire/local.py) calls it.
    monkeypatch.setattr(local_module, "shutil", types.SimpleNamespace(rmtree=lambda *a, **k: None))
    try:
        assert acquire_url("https://y/x", tmp_path / "unit", profile_off, False).ok
        captured = capsys.readouterr()
        folder = fake_ydl.folders[0]
        assert folder.exists()
        lines = captured.err.splitlines()
        assert len(lines) == 1
        assert lines[0].startswith("warning: could not delete the temporary folder") and str(folder) in lines[0]
        assert captured.out == ""
    finally:
        for f in fake_ydl.folders:
            shutil.rmtree(f, ignore_errors=True)


def test_metadata_call_does_not_resolve_playlist_entries(fake_ydl, tmp_path, profile_off):
    acquire_url("https://y/x", tmp_path, profile_off, False)
    metadata_opts, caption_opts = fake_ydl.all_opts[0], fake_ydl.all_opts[1]
    assert metadata_opts.get("extract_flat") == "in_playlist"
    assert caption_opts.get("skip_download") is True
    assert "extract_flat" not in caption_opts


def test_no_backend_means_no_audio_download(monkeypatch, fake_ydl_no_caps, fake_asr, tmp_path, profile_on):
    def missing(backend=None, model=None):
        raise asr.BackendMissing("no ASR backend is installed")

    monkeypatch.setattr(asr, "resolve_backend", missing)
    with pytest.raises(asr.BackendMissing):
        acquire_url("https://y/x", tmp_path, profile_on, False)
    assert fake_ydl_no_caps.downloads == [] and fake_ydl_no_caps.folders == []
    assert fake_asr.calls == []
    assert not UnitPaths(tmp_path).transcript.exists()
