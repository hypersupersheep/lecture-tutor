import functools
import importlib.util
import json
import os
import subprocess
import time
import types
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


def _long_boom(audio, model, **kwargs):
    raise RuntimeError("\n".join(f"detail {i}" for i in range(10)))


def _logging_backend(audio, model, log, fail_on=None, sleep_on=None, **kwargs):
    """Appends "device model compute_type" to ``log``; fails or sleeps on the device named."""
    device = kwargs.get("device")
    with open(log, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"{device} {model} {kwargs.get('compute_type')}\n")
    if fail_on == "any" or (fail_on is not None and fail_on == device):
        raise RuntimeError(f"{device} failed\nsecond line")
    if sleep_on is not None and sleep_on == device:
        time.sleep(5)
    return Transcript([Segment(0.0, 1.0, f"from {device}")], None)


def _env_backend(audio, model, **kwargs):
    names = ("HF_HUB_OFFLINE", "HF_HUB_DISABLE_TELEMETRY")
    return Transcript([Segment(0.0, 1.0, json.dumps({n: os.environ.get(n) for n in names}))], None)


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
    monkeypatch.setattr(asr, "model_cached", lambda backend, model: False)
    t = transcribe(Path("unused.wav"), None, PROMPT, budget_minutes=1, backend=name, model="x")
    return json.loads(t.segments[0].text)


def install_logging_backend(monkeypatch, tmp_path, name, cuda, **options):
    """Local helper: registers _logging_backend as ``name``; returns a reader of its calls."""
    log = tmp_path / "calls.txt"
    monkeypatch.setitem(asr.BACKENDS, name, functools.partial(_logging_backend, log=str(log), **options))
    monkeypatch.setattr(asr, "_installed", lambda module: True)
    monkeypatch.setattr(asr, "_cuda_devices", lambda: 1 if cuda else 0)
    monkeypatch.setattr(asr, "model_cached", lambda backend, model: False)

    def calls():
        if not log.exists():
            return []
        return [tuple(line.split(" ")) for line in log.read_text(encoding="utf-8").splitlines()]

    return calls


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


def test_named_backend_without_any_backend_gives_installer_hint(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: None)
    started = no_child_process(monkeypatch)
    for name in ("faster", "mlx"):
        with pytest.raises(BackendMissing) as exc:
            asr.resolve_backend(name)
        assert str(exc.value) == asr.NO_BACKEND
    with pytest.raises(BackendMissing) as exc:
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    assert str(exc.value) == asr.NO_BACKEND
    assert started == []


_REAL_FIND_SPEC = importlib.util.find_spec


def _only_installed(monkeypatch, module):
    """find_spec finds only ``module`` (any real spec stands in for it)."""
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name, *args, **kwargs: _REAL_FIND_SPEC("json") if name == module else None,
    )


def test_named_backend_not_installed_beside_the_other_is_pip_hint(monkeypatch):
    started = no_child_process(monkeypatch)
    _only_installed(monkeypatch, "mlx_whisper")
    with pytest.raises(BackendMissing) as exc:
        asr.resolve_backend("faster")
    assert str(exc.value) == "ASR backend 'faster' is not installed: pip install faster-whisper"
    with pytest.raises(BackendMissing, match="faster-whisper"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    _only_installed(monkeypatch, "faster_whisper")
    with pytest.raises(BackendMissing) as exc:
        asr.resolve_backend("mlx")
    assert str(exc.value) == "ASR backend 'mlx' is not installed: pip install mlx-whisper"
    assert started == []


def test_child_error_carries_traceback_tail(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _boom)
    with pytest.raises(AcquireError) as exc:
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    message = str(exc.value)
    assert message.startswith("ASR backend 'fake' failed: RuntimeError: boom\n")
    assert "_boom" in message


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


NO_BACKEND = ("speech recognition is not installed: run the installer again with --with-asr "
              "(Windows: -WithAsr), then rerun this command")


def test_no_backend_installed_is_backend_missing(monkeypatch):
    monkeypatch.setattr(asr, "_installed", lambda module: False)
    with pytest.raises(BackendMissing, match="speech recognition is not installed"):
        asr.select_backend()


def test_no_backend_message_names_the_installer_flag(monkeypatch):
    monkeypatch.setattr(asr, "_installed", lambda module: False)
    with pytest.raises(BackendMissing) as exc:
        asr.resolve_backend()
    assert str(exc.value) == NO_BACKEND
    assert "--with-asr" in str(exc.value) and "-WithAsr" in str(exc.value)


def test_select_model_follows_the_ram_threshold(monkeypatch):
    monkeypatch.setattr(asr, "_ram_bytes", lambda: 16 * asr.GIB - 1)
    assert select_model("mlx") == "mlx-community/whisper-small-mlx"
    monkeypatch.setattr(asr, "_ram_bytes", lambda: 16 * asr.GIB)
    assert select_model("mlx") == "mlx-community/whisper-large-v3-turbo"


def test_missing_ffmpeg_is_acquire_error(monkeypatch):
    import imageio_ffmpeg

    def no_bundled_ffmpeg():
        raise RuntimeError("no ffmpeg exe could be found")

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: None)
    monkeypatch.setattr(imageio_ffmpeg, "get_ffmpeg_exe", no_bundled_ffmpeg)
    with pytest.raises(AcquireError) as exc:
        ffmpeg_exe()
    assert str(exc.value).startswith("ffmpeg is not available")
    assert str(exc.value) == "ffmpeg is not available: install ffmpeg, or reinstall imageio-ffmpeg"


def test_child_error_line_appears_once(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _boom)
    with pytest.raises(AcquireError) as exc:
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    message = str(exc.value)
    assert message.startswith("ASR backend 'fake' failed: RuntimeError: boom\n")
    assert message.count("RuntimeError: boom") == 1
    assert "_boom" in message


def test_child_error_keeps_the_type_for_a_long_message(monkeypatch):
    monkeypatch.setitem(asr.BACKENDS, "fake", _long_boom)
    with pytest.raises(AcquireError) as exc:
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake")
    message = str(exc.value)
    # Only the first line of a ten-line message, after its type; then the frame lines.
    assert message.startswith("ASR backend 'fake' failed: RuntimeError: detail 0\n")
    assert message.count("RuntimeError: detail") == 1
    assert "detail 1" not in message and "detail 9" not in message
    assert "_long_boom" in message
    assert len(message.splitlines()) <= 6


def test_cuda_failure_retries_on_cpu(monkeypatch, tmp_path, capfd):
    calls = install_logging_backend(monkeypatch, tmp_path, "faster", cuda=True, fail_on="cuda")
    t = transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    assert [s.text for s in t.segments] == ["from cpu"]
    assert t.device == "cpu"
    # The model is the one the CPU path chooses, with the CPU's compute type.
    assert calls() == [("cuda", "large-v3-turbo", "float16"), ("cpu", "small", "int8")]
    err = capfd.readouterr().err
    assert "warning: GPU transcription failed (RuntimeError: cuda failed); retrying on the CPU\n" in err
    assert err.count("retrying on the CPU") == 1


def test_cuda_retry_keeps_a_named_model(monkeypatch, tmp_path, capfd):
    calls = install_logging_backend(monkeypatch, tmp_path, "faster", cuda=True, fail_on="cuda")
    transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster", model="medium")
    assert calls() == [("cuda", "medium", "float16"), ("cpu", "medium", "int8")]


def test_cpu_failure_is_not_retried(monkeypatch, tmp_path, capfd):
    calls = install_logging_backend(monkeypatch, tmp_path, "faster", cuda=False, fail_on="cpu")
    with pytest.raises(AcquireError, match="RuntimeError: cpu failed"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    assert calls() == [("cpu", "small", "int8")]
    assert "retrying" not in capfd.readouterr().err


def test_mlx_failure_is_not_retried(monkeypatch, tmp_path, capfd):
    calls = install_logging_backend(monkeypatch, tmp_path, "mlx", cuda=True, fail_on="any")
    with pytest.raises(AcquireError, match="RuntimeError: None failed"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="mlx", model="x")
    assert len(calls()) == 1
    assert "retrying" not in capfd.readouterr().err


def test_mlx_and_cpu_devices_are_reported(monkeypatch, tmp_path):
    install_logging_backend(monkeypatch, tmp_path, "mlx", cuda=False)
    assert transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="mlx", model="x").device == "mlx"
    install_logging_backend(monkeypatch, tmp_path, "faster", cuda=False)
    assert transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster").device == "cpu"


def test_cuda_dying_child_retries_on_cpu(monkeypatch, capfd):
    monkeypatch.setitem(asr.BACKENDS, "faster", _dying_backend)
    monkeypatch.setattr(asr, "_installed", lambda module: True)
    monkeypatch.setattr(asr, "_cuda_devices", lambda: 1)
    with pytest.raises(AcquireError, match="without a result"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    err = capfd.readouterr().err
    assert "warning: GPU transcription failed (the ASR process exited without a result (exit code 7)); " \
           "retrying on the CPU" in err


def test_budget_covers_both_attempts(monkeypatch, tmp_path):
    calls = install_logging_backend(monkeypatch, tmp_path, "faster", cuda=True, fail_on="cuda", sleep_on="cpu")

    def clock():
        # 59.5 s of the 60 s budget are gone once the CUDA attempt has run.
        return 59.5 if calls() else 0.0

    monkeypatch.setattr(asr, "time", types.SimpleNamespace(monotonic=clock))
    started = time.monotonic()
    with pytest.raises(BudgetExceeded, match="1 minutes"):
        transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="faster")
    assert time.monotonic() - started < 5      # the CPU attempt got the 0.5 s left, not a new minute


def test_cached_model_loads_offline(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setitem(asr.BACKENDS, "fake", _env_backend)
    lookups = []
    for cached, offline in ((True, "1"), (False, None)):
        monkeypatch.setattr(asr, "model_cached", lambda backend, model: lookups.append((backend, model)) or cached)
        t = transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake", model="m")
        assert json.loads(t.segments[0].text) == {"HF_HUB_OFFLINE": offline, "HF_HUB_DISABLE_TELEMETRY": "1"}
    assert lookups == [("fake", "m"), ("fake", "m")]
    assert "HF_HUB_OFFLINE" not in os.environ   # set in the child only


def test_cached_lookup_error_means_online(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setitem(asr.BACKENDS, "fake", _env_backend)

    def broken(backend, model):
        raise OSError("missing DLL")

    monkeypatch.setattr(asr, "model_cached", broken)
    t = transcribe(Path("unused.wav"), None, "", budget_minutes=1, backend="fake", model="m")
    assert json.loads(t.segments[0].text)["HF_HUB_OFFLINE"] is None


def test_model_cached_unknown_backend_is_false():
    assert asr.model_cached("no-such-backend", "small") is False
