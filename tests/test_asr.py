import functools
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from tutor_any_lecture import asr, ffmpeg
from tutor_any_lecture.asr import (BackendMissing, BudgetExceeded, default_budget_minutes,
                                   select_model, transcribe)
from tutor_any_lecture.ffmpeg import extract_audio, ffmpeg_exe
from tutor_any_lecture.transcript import AcquireError, Segment, Transcript

PROMPT = "Black-Scholes, martingale"


# Local helpers. Module-level on purpose: the spawn child unpickles them by reference.
def _echo_backend(audio, model, **kwargs):
    return Transcript([Segment(0.0, 1.0, json.dumps(kwargs, default=str))], None)


def _slow_backend(audio, model, seconds=5, **kwargs):
    time.sleep(seconds)
    return Transcript([], None)


def _lang_backend(audio, model, **kwargs):
    return Transcript([Segment(0.0, 1.0, "x")], "zh-Hans")


def _boom_backend(audio, model, **kwargs):
    raise ValueError("boom")


def _dying_backend(audio, model, **kwargs):
    os._exit(7)


def _chatty_backend(audio, model, **kwargs):
    print("backend chatter")
    return Transcript([Segment(0.0, 1.0, "x")], None)


def _boom(audio, model, **kwargs):
    raise RuntimeError("boom")


def _native_noise(audio, model, **kwargs):
    os.write(1, b"native noise\n")   # what native code does: bypasses sys.stdout
    return Transcript([Segment(0.0, 1.0, "x")], None)


def fake_failing_ffmpeg(monkeypatch):
    """Local helper: every ffmpeg run exits 1 with an error on stderr."""
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, b"", b"Invalid data found when processing input\n")

    monkeypatch.setattr(ffmpeg.subprocess, "run", run)


def no_child_process(monkeypatch):
    """Local helper: records any attempt to set up the ASR child process."""
    started = []
    monkeypatch.setattr(asr.multiprocessing, "get_context", lambda *a, **k: started.append(a) or pytest.fail("child started"))
    return started


def run_with_fake_backend(monkeypatch, name="fake"):
    monkeypatch.setitem(asr.BACKENDS, name, _echo_backend)
    # A real backend name is checked for its package; the fake stands in for it.
    monkeypatch.setattr(asr, "_installed", lambda module: True)
    t = transcribe(Path("unused.wav"), None, PROMPT, budget_minutes=1, backend=name, model="x")
    return json.loads(t.segments[0].text)


def fake_slow_backend(monkeypatch, seconds=5):
    monkeypatch.setitem(asr.BACKENDS, "fake", functools.partial(_slow_backend, seconds=seconds))


def test_select_model_cpu(monkeypatch):
    monkeypatch.setattr(asr, "_cuda_devices", lambda: 0)
    assert select_model("faster") == "small"


def test_params_are_fixed(monkeypatch):
    # the echo fake reports its kwargs through its return value
    seen = run_with_fake_backend(monkeypatch)
    assert seen["condition_on_previous_text"] is False
    assert seen["word_timestamps"] is True
    assert seen["hallucination_silence_threshold"] == 2
    assert seen["initial_prompt"] == PROMPT
    assert seen["language"] is None
    assert "vad_filter" not in seen
    seen = run_with_fake_backend(monkeypatch, name="faster")
    assert seen["vad_filter"] is True


def test_budget_exceeded(monkeypatch, tmp_path):
    fake_slow_backend(monkeypatch, seconds=5)
    with pytest.raises(BudgetExceeded):
        transcribe(tmp_path / "a.wav", None, "", budget_minutes=0.01, backend="fake")


def test_transcribe_language_rule(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _lang_backend)
    # no language given: the backend's "zh-Hans" -> primary subtag "zh"
    assert transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake").language == "zh"
    # language given: it wins over the backend's report; "en-GB" -> "en"
    assert transcribe(Path("unused.wav"), "en-GB", "", budget_minutes=1, backend="fake").language == "en"


def test_backend_error_is_reported(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _boom_backend)
    with pytest.raises(RuntimeError, match="boom"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")


def test_child_exit_without_reply_is_runtime_error(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _dying_backend)
    with pytest.raises(RuntimeError, match="without a result"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")


def test_backend_output_goes_to_stderr(monkeypatch, capfd):
    monkeypatch.setitem(asr.BACKENDS, "fake", _chatty_backend)
    transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    captured = capfd.readouterr()
    assert "backend chatter" not in captured.out and "backend chatter" in captured.err


def test_unknown_backend_is_backend_missing():
    with pytest.raises(BackendMissing):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="no-such-backend")


def test_default_budget_minutes():
    assert default_budget_minutes(None) == 30.0
    assert default_budget_minutes(600) == 30.0     # 2 * 600 / 60 = 20, below the floor of 30
    assert default_budget_minutes(3600) == 120.0   # 2 * 3600 / 60 = 120


def test_load_audio_array_float32_16k(tmp_path):
    np = pytest.importorskip("numpy")
    src = tmp_path / "第 1 周" / "tone.wav"
    src.parent.mkdir()
    subprocess.run([ffmpeg_exe(), "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(src)],
                   check=True, capture_output=True)
    arr = asr._load_audio_array(src)
    assert arr.dtype == np.float32 and arr.ndim == 1
    assert abs(arr.size - 32000) <= 800            # 2 s at 16 kHz = 32000 samples, within 0.05 s
    assert 0.0 < float(np.abs(arr).max()) <= 1.0


def test_extract_audio_failure_is_acquire_error(monkeypatch, tmp_path):
    fake_failing_ffmpeg(monkeypatch)
    with pytest.raises(AcquireError) as exc:
        extract_audio(tmp_path / "in.mp4", tmp_path / "out.wav")
    assert "could not extract audio" in str(exc.value) and "Invalid data found" in str(exc.value)


def test_audio_decode_failure_is_acquire_error(monkeypatch, tmp_path):
    pytest.importorskip("numpy")
    fake_failing_ffmpeg(monkeypatch)
    with pytest.raises(AcquireError, match="could not decode"):
        asr._load_audio_array(tmp_path / "in.wav")


def test_backend_failure_is_acquire_error(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _boom)
    with pytest.raises(AcquireError) as exc:
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    assert "boom" in str(exc.value)


def test_child_exit_without_reply_is_acquire_error(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _dying_backend)
    with pytest.raises(AcquireError, match="without a result"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")


def test_named_backend_not_installed_is_backend_missing(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: None)
    started = no_child_process(monkeypatch)
    with pytest.raises(BackendMissing) as exc:
        asr.resolve_backend("faster")
    assert str(exc.value) == "ASR backend 'faster' is not installed: pip install faster-whisper"
    with pytest.raises(BackendMissing) as exc:
        asr.resolve_backend("mlx")
    assert str(exc.value) == "ASR backend 'mlx' is not installed: pip install mlx-whisper"
    with pytest.raises(BackendMissing, match="faster-whisper"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    assert started == []


def test_child_error_carries_traceback_tail(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _boom)
    with pytest.raises(AcquireError) as exc:
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    assert "_boom" in str(exc.value)


def test_child_native_stdout_goes_to_stderr(monkeypatch, capfd):
    monkeypatch.setitem(asr.BACKENDS, "fake", _native_noise)
    t = transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    assert [s.text for s in t.segments] == ["x"]
    captured = capfd.readouterr()
    assert "native noise" not in captured.out and "native noise" in captured.err


def test_media_duration_unknown_is_none(monkeypatch, tmp_path):
    def run(argv, **kwargs):
        stderr = b"Input #0, srt, from 'x.srt':\n  Duration: N/A, bitrate: N/A\n"
        return subprocess.CompletedProcess(argv, 1, b"", stderr)

    monkeypatch.setattr(ffmpeg.subprocess, "run", run)
    assert ffmpeg.media_duration(tmp_path / "x.srt") is None


def test_no_backend_installed_is_backend_missing(monkeypatch):
    monkeypatch.setattr(asr, "_installed", lambda module: False)
    with pytest.raises(BackendMissing, match="no ASR backend is installed"):
        asr.select_backend()


def test_select_model_follows_the_ram_threshold(monkeypatch):
    monkeypatch.setattr(asr, "_ram_bytes", lambda: 16 * asr.GIB - 1)
    assert select_model("mlx") == "mlx-community/whisper-small-mlx"
    monkeypatch.setattr(asr, "_ram_bytes", lambda: 16 * asr.GIB)
    assert select_model("mlx") == "mlx-community/whisper-large-v3-turbo"
