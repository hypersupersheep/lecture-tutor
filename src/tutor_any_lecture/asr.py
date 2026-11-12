"""Speech recognition: pick a backend and a model, and transcribe within a time budget.

The backend runs in a child process started with the "spawn" method on every OS, so
the budget can be enforced by killing it. The parent resolves everything (backend
function, model, keyword arguments) and the child only calls the function it is given.
Nothing runs at import time: no backend, numpy or ctranslate2 is imported here at
module level.
"""

from __future__ import annotations

import importlib.util
import multiprocessing
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Callable

from .ffmpeg import ffmpeg_exe, stderr_tail
from .transcript import AcquireError, Segment, Transcript, primary_subtag

GIB = 1024 ** 3


class BackendMissing(Exception):
    """No usable ASR backend is installed, or the requested one is unknown."""


class BudgetExceeded(Exception):
    """Transcription did not finish within the time budget."""


# --- audio --------------------------------------------------------------------

def _load_audio_array(audio: Path):
    """``audio`` decoded by ffmpeg to 16 kHz mono float32 samples in [-1, 1]."""
    import numpy as np

    proc = subprocess.run(
        [ffmpeg_exe(), "-nostdin", "-i", str(audio),
         "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", "16000", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        # Never fall through to an empty array: a backend would turn it into zero segments.
        raise AcquireError(f"ffmpeg could not decode {audio}:\n{stderr_tail(proc.stderr)}")
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


# --- backends (module-level, so the spawn child can unpickle them) --------------

def _word_list(words) -> list[dict] | None:
    """Word timings as ``[{"word", "start", "end"}]``, or None when there are none."""
    if not words:
        return None
    return [{"word": str(w["word"]), "start": float(w["start"]), "end": float(w["end"])} for w in words]


def _mlx_backend(audio: str, model: str | None, **kwargs) -> Transcript:
    import mlx_whisper

    options = dict(kwargs)
    options["initial_prompt"] = options.get("initial_prompt") or None
    # An array, never a path: given a path, mlx_whisper would shell out to a bare "ffmpeg".
    result = mlx_whisper.transcribe(
        _load_audio_array(Path(audio)), path_or_hf_repo=model, verbose=None, **options
    )
    segments = []
    for s in result.get("segments", []):
        text = str(s.get("text") or "").strip()
        if text:
            segments.append(Segment(float(s["start"]), float(s["end"]), text, _word_list(s.get("words"))))
    return Transcript(segments, result.get("language"))


def _faster_backend(audio: str, model: str | None, **kwargs) -> Transcript:
    from faster_whisper import WhisperModel

    cuda = _cuda_devices() > 0
    whisper = WhisperModel(model, device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")
    options = dict(kwargs)
    options["initial_prompt"] = options.get("initial_prompt") or None
    generator, info = whisper.transcribe(audio, **options)
    segments = []
    for s in generator:  # the generator does the work; consume it here, inside the child
        text = (s.text or "").strip()
        if text:
            words = None
            if s.words:
                words = [{"word": w.word, "start": float(w.start), "end": float(w.end)} for w in s.words]
            segments.append(Segment(float(s.start), float(s.end), text, words))
    return Transcript(segments, info.language)


BACKENDS: dict[str, Callable] = {
    "mlx": _mlx_backend,
    "faster": _faster_backend,
}

# The distribution each real backend needs; its import name is the same with "_" for "-".
BACKEND_PACKAGES: dict[str, str] = {"mlx": "mlx-whisper", "faster": "faster-whisper"}


# --- choosing a backend and a model ---------------------------------------------

def _installed(module: str) -> bool:
    # find_spec locates the package without importing it.
    return importlib.util.find_spec(module) is not None


def select_backend() -> str:
    if sys.platform == "darwin" and platform.machine() == "arm64" and _installed("mlx_whisper"):
        return "mlx"
    if _installed("faster_whisper"):
        return "faster"
    raise BackendMissing("no ASR backend is installed: install mlx-whisper (Apple Silicon) or faster-whisper")


def _ram_bytes() -> int:
    """Physical memory in bytes, or 0 when it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(stat)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return 0
            return int(stat.ullTotalPhys)
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def _cuda_devices() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def select_model(backend: str) -> str:
    if backend == "mlx":
        if _ram_bytes() >= 16 * GIB:
            return "mlx-community/whisper-large-v3-turbo"
        return "mlx-community/whisper-small-mlx"
    if backend == "faster":
        return "large-v3-turbo" if _cuda_devices() > 0 else "small"
    raise BackendMissing(f"no default model for ASR backend {backend!r}")


def resolve_backend(backend: str | None = None, model: str | None = None) -> tuple[str, str | None]:
    name = select_backend() if backend is None else backend
    if name not in BACKENDS:
        raise BackendMissing(f"unknown ASR backend {name!r}; choose one of: {', '.join(sorted(BACKENDS))}")
    package = BACKEND_PACKAGES.get(name)
    # Checked here, in the parent, so a missing package fails before any audio work or child process.
    if package is not None and not _installed(package.replace("-", "_")):
        raise BackendMissing(f"ASR backend {name!r} is not installed: pip install {package}")
    if model is None and name in ("mlx", "faster"):
        model = select_model(name)
    return name, model


def default_budget_minutes(duration_s: float | None) -> float:
    if duration_s is None:
        return 30.0
    return max(30.0, 2 * duration_s / 60)


# --- transcription --------------------------------------------------------------

def _child(fn: Callable, audio: str, model: str | None, kwargs: dict, conn) -> None:
    """The spawn child: run one backend and send ``("ok", transcript)`` or ``("err", message)``."""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # The command's stdout carries one JSON object; whatever a backend prints goes to stderr.
    sys.stdout = sys.stderr
    try:
        # Also file descriptor 1, which native code (C, C++, Metal) writes to directly.
        os.dup2(2, 1)
    except OSError:
        pass
    try:
        conn.send(("ok", fn(audio, model, **kwargs)))
    except Exception:  # every backend failure goes back to the parent as a message
        # The tail ends with the "Type: message" line, so it is not repeated in front.
        conn.send(("err", "\n".join(traceback.format_exc().splitlines()[-5:])))
    finally:
        conn.close()


def transcribe(
    audio: Path,
    language: str | None,
    initial_prompt: str,
    budget_minutes: float,
    backend: str | None = None,
    model: str | None = None,
) -> Transcript:
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    name, model = resolve_backend(backend, model)
    fn = BACKENDS[name]
    lang = primary_subtag(language)
    kwargs = {
        "language": lang,
        "initial_prompt": initial_prompt,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "hallucination_silence_threshold": 2,
    }
    if name == "faster":
        kwargs["vad_filter"] = True

    ctx = multiprocessing.get_context("spawn")
    reader, writer = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(fn, str(audio), model, kwargs, writer))
    started = False
    try:
        proc.start()  # inside the try: a failed start still closes both pipe ends
        started = True
        # Close the parent's copy of the child's end, so a child that dies gives EOF, not a hang.
        writer.close()
        if not reader.poll(budget_minutes * 60):
            raise BudgetExceeded(
                f"transcription did not finish within {budget_minutes:g} minutes; "
                "rerun with a larger --budget-minutes"
            )
        try:
            status, payload = reader.recv()  # recv before join: a large reply would block the child
        except EOFError:
            proc.join()
            raise AcquireError(f"the ASR process exited without a result (exit code {proc.exitcode})") from None
        proc.join(timeout=30)
    finally:
        writer.close()  # closing twice is a no-op
        reader.close()
        if started:
            if proc.is_alive():
                proc.kill()
            proc.join()

    if status != "ok":
        raise AcquireError(f"ASR backend {name!r} failed: {payload}")
    reported = lang if lang is not None else primary_subtag(payload.language)
    return Transcript(payload.segments, reported)
