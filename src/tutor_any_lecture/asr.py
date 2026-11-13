"""Speech recognition: pick a backend and a model, and transcribe within a time budget.

The backend runs in a child process started with the "spawn" method on every OS, so
the budget can be enforced by killing it. The parent resolves everything (backend
function, model, keyword arguments) and the child only calls the function it is given.
Nothing runs at import time: no backend, numpy or ctranslate2 is imported here at
module level.
"""

from __future__ import annotations

import importlib
import importlib.util
import multiprocessing
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .ffmpeg import ffmpeg_exe, stderr_tail
from .transcript import AcquireError, Segment, Transcript, primary_subtag

GIB = 1024 ** 3


class BackendMissing(Exception):
    """No usable ASR backend is installed, or the requested one is unknown."""


# Speech recognition is the optional "asr" extra; the installers add it with this flag.
NO_BACKEND = (
    "speech recognition is not installed: run the installer again with --with-asr "
    "(Windows: -WithAsr), then rerun this command"
)


class BudgetExceeded(Exception):
    """Transcription did not finish within the time budget."""


@dataclass
class AsrTranscript(Transcript):
    """A transcript from ASR, with the device that produced it.

    ``device`` is "cuda", "cpu" or "mlx" for the real backends, None for any other.
    """

    device: str | None = None


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


def _faster_backend(
    audio: str, model: str | None, device: str = "cpu", compute_type: str = "int8", **kwargs
) -> Transcript:
    from faster_whisper import WhisperModel

    # The parent picks the device, so that it can retry on the CPU when CUDA fails.
    whisper = WhisperModel(model, device=device, compute_type=compute_type)
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
    raise BackendMissing(NO_BACKEND)


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


# faster-whisper's default model and compute type on each device.
_FASTER_MODELS = {"cuda": "large-v3-turbo", "cpu": "small"}
_FASTER_COMPUTE = {"cuda": "float16", "cpu": "int8"}


def select_device(backend: str) -> str | None:
    """The device ``backend`` runs on here: "mlx", "cuda" or "cpu"; None for another backend."""
    if backend == "mlx":
        return "mlx"
    if backend == "faster":
        return "cuda" if _cuda_devices() > 0 else "cpu"
    return None


def select_model(backend: str) -> str:
    if backend == "mlx":
        if _ram_bytes() >= 16 * GIB:
            return "mlx-community/whisper-large-v3-turbo"
        return "mlx-community/whisper-small-mlx"
    if backend == "faster":
        return _FASTER_MODELS[select_device(backend)]
    raise BackendMissing(f"no default model for ASR backend {backend!r}")


def resolve_backend(backend: str | None = None, model: str | None = None) -> tuple[str, str | None]:
    name = select_backend() if backend is None else backend
    if name not in BACKENDS:
        raise BackendMissing(f"unknown ASR backend {name!r}; choose one of: {', '.join(sorted(BACKENDS))}")
    package = BACKEND_PACKAGES.get(name)
    # Checked here, in the parent, so a missing package fails before any audio work or child process.
    if package is not None and not _installed(package.replace("-", "_")):
        # With no backend at all, the asr extra is missing: point at the installer, whose
        # tool environment pip would not reach. The pip text is only for the other backend's install.
        if not any(_installed(p.replace("-", "_")) for p in BACKEND_PACKAGES.values()):
            raise BackendMissing(NO_BACKEND)
        raise BackendMissing(f"ASR backend {name!r} is not installed: pip install {package}")
    if model is None and name in ("mlx", "faster"):
        model = select_model(name)
    return name, model


# backend -> (distribution, module) whose lookup finds a model in the local cache.
CACHE_LOOKUP: dict[str, tuple[str, str]] = {
    "mlx": ("huggingface-hub", "huggingface_hub"),
    "faster": ("faster-whisper", "faster_whisper.utils"),
}


def model_cached(backend: str, model: str) -> bool:
    """Whether ``model`` is already in the local cache. Never downloads (local_files_only).

    An unknown backend gives False, as does a lookup package that is not installed. A
    package that is installed but fails to import re-raises its error.
    """
    if backend not in CACHE_LOOKUP:
        return False
    module = CACHE_LOOKUP[backend][1]
    try:
        lib = importlib.import_module(module)
    except Exception:  # a broken native library may raise OSError, not ImportError
        if importlib.util.find_spec(module.split(".")[0]) is None:
            return False
        raise
    try:
        if backend == "mlx":
            lib.snapshot_download(model, local_files_only=True)
        else:
            lib.download_model(model, local_files_only=True)
    except Exception:
        return False
    return True


def _loads_offline(backend: str, model: str | None) -> bool:
    """``model_cached`` for the child's HF_HUB_OFFLINE; any lookup error means "no"."""
    if model is None:
        return False
    try:
        return model_cached(backend, model)
    except Exception:
        return False


def default_budget_minutes(duration_s: float | None) -> float:
    if duration_s is None:
        return 30.0
    return max(30.0, 2 * duration_s / 60)


# --- transcription --------------------------------------------------------------

def _error_text(error: BaseException) -> str:
    """``Type: first line of the message``, then the traceback's last five frame lines.

    The traceback's own final ``Type: message`` line is left out, so the type and the
    message appear once, first, however many lines the message has.
    """
    lines = str(error).splitlines()
    head = f"{type(error).__name__}: {lines[0]}" if lines else type(error).__name__
    frames = "".join(traceback.format_tb(error.__traceback__)).splitlines()[-5:]
    return "\n".join([head, *frames])


def _child(fn: Callable, audio: str, model: str | None, kwargs: dict, conn, offline: bool = False) -> None:
    """The spawn child: run one backend and send ``("ok", transcript)`` or ``("err", message)``."""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if offline:
        # The model is in the local cache: load it with no network call. Set before the
        # backend imports huggingface_hub, which reads it once, at import.
        os.environ["HF_HUB_OFFLINE"] = "1"
    # The command's stdout carries one JSON object; whatever a backend prints goes to stderr.
    sys.stdout = sys.stderr
    try:
        # Also file descriptor 1, which native code (C, C++, Metal) writes to directly.
        os.dup2(2, 1)
    except OSError:
        pass
    try:
        conn.send(("ok", fn(audio, model, **kwargs)))
    except Exception as e:  # every backend failure goes back to the parent as a message
        conn.send(("err", _error_text(e)))
    finally:
        conn.close()


def _run_child(
    fn: Callable,
    audio: Path,
    model: str | None,
    kwargs: dict,
    offline: bool,
    deadline: float,
    budget_minutes: float,
) -> tuple[str, object]:
    """Run ``fn`` once in a spawn child, until ``deadline`` (a ``time.monotonic`` reading).

    Returns ``("ok", transcript)``, ``("err", message)`` for a backend error, or
    ``("died", message)`` when the child exits without a result. Raises ``BudgetExceeded``
    when the deadline passes; the child is ended in every case.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BudgetExceeded(_over_budget(budget_minutes))
    ctx = multiprocessing.get_context("spawn")
    reader, writer = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(fn, str(audio), model, kwargs, writer, offline))
    started = False
    try:
        proc.start()  # inside the try: a failed start still closes both pipe ends
        started = True
        # Close the parent's copy of the child's end, so a child that dies gives EOF, not a hang.
        writer.close()
        if not reader.poll(remaining):
            raise BudgetExceeded(_over_budget(budget_minutes))
        try:
            result = reader.recv()  # recv before join: a large reply would block the child
        except EOFError:
            proc.join()
            result = ("died", f"the ASR process exited without a result (exit code {proc.exitcode})")
        proc.join(timeout=30)
    finally:
        writer.close()  # closing twice is a no-op
        reader.close()
        if started:
            if proc.is_alive():
                proc.kill()
            proc.join()
    return result


def _over_budget(budget_minutes: float) -> str:
    return (
        f"transcription did not finish within {budget_minutes:g} minutes; "
        "rerun with a larger --budget-minutes"
    )


def transcribe(
    audio: Path,
    language: str | None,
    initial_prompt: str,
    budget_minutes: float,
    backend: str | None = None,
    model: str | None = None,
) -> AsrTranscript:
    """Transcribe ``audio`` in a child process within ``budget_minutes``.

    A failed CUDA run of the ``faster`` backend is retried once on the CPU, within the
    same budget. The result records the device that produced it.
    """
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    name, model = resolve_backend(backend, model)
    fn = BACKENDS[name]
    lang = primary_subtag(language)
    device = select_device(name)
    kwargs = {
        "language": lang,
        "initial_prompt": initial_prompt,
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "hallucination_silence_threshold": 2,
    }
    if name == "faster":
        kwargs["vad_filter"] = True
        kwargs.update(device=device, compute_type=_FASTER_COMPUTE[device])

    deadline = time.monotonic() + budget_minutes * 60  # one budget for every attempt
    status, payload = _run_child(fn, audio, model, kwargs, _loads_offline(name, model), deadline, budget_minutes)
    if status != "ok" and name == "faster" and device == "cuda":
        first = str(payload).splitlines()[0] if str(payload) else ""
        print(f"warning: GPU transcription failed ({first}); retrying on the CPU", file=sys.stderr)
        device = "cpu"
        # The model the CPU path would choose: its default replaces the CUDA default; a named model stays.
        if model == _FASTER_MODELS["cuda"]:
            model = _FASTER_MODELS["cpu"]
        kwargs.update(device=device, compute_type=_FASTER_COMPUTE[device])
        offline = _loads_offline(name, model)
        status, payload = _run_child(fn, audio, model, kwargs, offline, deadline, budget_minutes)

    if status == "died":
        raise AcquireError(payload)
    if status != "ok":
        raise AcquireError(f"ASR backend {name!r} failed: {payload}")
    reported = lang if lang is not None else primary_subtag(payload.language)
    return AsrTranscript(payload.segments, reported, device=device)
