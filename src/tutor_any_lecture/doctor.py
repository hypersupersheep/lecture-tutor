"""Readiness checks: is this machine ready to run tutor-any-lecture?

Each check is a small function listed in ``CHECKS``. ``run_doctor`` runs them in order
and never raises: a check that raises is reported as not ok. Dependencies (``asr``,
``ffmpeg``, ``config``, ``yt_dlp``, the ASR backends) are imported inside the check that
needs them, so the report still comes out when one of them is missing. No check makes a
network call, downloads anything, starts a browser or runs ffmpeg.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__


@dataclass(frozen=True)
class Check:
    name: str
    required: bool
    fn: Callable[[], tuple]  # returns (ok, detail) or (ok, detail, fix); may raise
    fix: str                 # one line; what to do when the check is not ok (unless fn gives one)


# --- helpers ----------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+)\.(\d+)")


def _version_of(text: str) -> tuple[int, int] | None:
    """The first ``major.minor`` in ``text``, or None."""
    m = _VERSION_RE.search(text)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2))


def _tool_version(name: str) -> tuple[int, int] | None:
    """The version that ``<name> --version`` prints, or None when the program is not on PATH."""
    exe = shutil.which(name)
    if exe is None:
        return None
    try:
        proc = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return _version_of(proc.stdout.decode("utf-8", errors="replace"))


def _browser_candidates() -> list[str]:
    """Default Chromium-family browser paths for this OS (CHROME_PATH not included)."""
    if sys.platform == "darwin":
        apps = [
            "Google Chrome.app/Contents/MacOS/Google Chrome",
            "Chromium.app/Contents/MacOS/Chromium",
            "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        roots = ["/Applications", os.path.expanduser("~/Applications")]
        return [str(Path(root) / app) for root in roots for app in apps]
    if sys.platform == "win32":
        exes = [
            r"Google\Chrome\Application\chrome.exe",
            r"Chromium\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
        ]
        roots = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        return [str(Path(root) / exe) for root in roots if root for exe in exes]
    # Command names, looked up on PATH by check_browser.
    return [
        "google-chrome", "google-chrome-stable", "chromium",
        "chromium-browser", "microsoft-edge", "microsoft-edge-stable",
    ]


def _find_browser(candidate: str) -> str | None:
    """A bare command name is looked up on PATH; anything else must be an existing file."""
    if os.path.basename(candidate) == candidate:
        return shutil.which(candidate)
    return candidate if Path(candidate).is_file() else None


class _BrokenPackage(Exception):
    """A package is installed (find_spec locates it) but importing it raises."""

    def __init__(self, package: str, error: Exception) -> None:
        super().__init__(f"{package} is installed but cannot be imported: {type(error).__name__}: {error}")
        self.package = package


# backend -> (distribution, module) that the cache lookup imports.
_CACHE_MODULES = {
    "mlx": ("huggingface-hub", "huggingface_hub"),
    "faster": ("faster-whisper", "faster_whisper.utils"),
}


def _model_cached(backend: str, model: str) -> bool:
    """Whether ``model`` is already in the local cache. Never downloads (local_files_only).

    An unknown backend gives False, as does a package that is not installed. A package
    that is installed but fails to import raises ``_BrokenPackage``.
    """
    if backend not in _CACHE_MODULES:
        return False
    package, module = _CACHE_MODULES[backend]
    try:
        lib = importlib.import_module(module)
    except Exception as e:  # a broken native library may raise OSError, not ImportError
        if importlib.util.find_spec(module.split(".")[0]) is None:
            return False
        raise _BrokenPackage(package, e) from e
    try:
        if backend == "mlx":
            lib.snapshot_download(model, local_files_only=True)
        else:
            lib.download_model(model, local_files_only=True)
    except Exception:
        return False
    return True


# --- the checks -------------------------------------------------------------------

def check_python() -> tuple[bool, str]:
    return sys.version_info >= (3, 10), platform.python_version()


def check_ffmpeg() -> tuple[bool, str]:
    from . import ffmpeg

    p = ffmpeg.ffmpeg_exe()
    return bool(p), p or "not found"


def check_asr_backend() -> tuple[bool, str]:
    # select_backend probes with find_spec; it never imports a backend (mlx may abort on import).
    from . import asr

    return True, asr.select_backend()


def check_yt_dlp() -> tuple[bool, str]:
    import yt_dlp

    return True, yt_dlp.version.__version__


def check_config_dir() -> tuple[bool, str]:
    from .config import config_dir

    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, probe = tempfile.mkstemp(dir=d)
    os.close(fd)
    os.remove(probe)
    return True, str(d)


_JS_MINIMUMS = (("deno", (2, 3)), ("node", (22, 0)))


def check_js_runtime() -> tuple[bool, str]:
    found = []
    for name, minimum in _JS_MINIMUMS:
        v = _tool_version(name)
        if v is None:
            continue
        if v >= minimum:
            return True, f"{name} {v[0]}.{v[1]}"
        found.append(f"{name} {v[0]}.{v[1]}")
    if found:
        return False, ", ".join(found) + " (need deno >= 2.3 or node >= 22)"
    return False, "deno and node not found"


def check_browser() -> tuple[bool, str]:
    candidates = []
    chrome_path = os.environ.get("CHROME_PATH")
    if chrome_path:
        candidates.append(chrome_path)
    candidates.extend(_browser_candidates())
    for p in candidates:
        found = _find_browser(p)
        if found:
            return True, found
    return False, "not found"


def check_asr_model() -> tuple[bool, str]:
    from . import asr

    backend = asr.select_backend()
    model = asr.select_model(backend)
    try:
        cached = _model_cached(backend, model)
    except _BrokenPackage as e:
        return False, str(e), f"Optional: reinstall {e.package}"
    if cached:
        return True, model
    return False, f"{model} is not cached"


CHECKS: list[Check] = [
    Check("python", True, check_python,
          "Install Python 3.10 or newer and reinstall tutor-any-lecture with it."),
    Check("ffmpeg", True, check_ffmpeg,
          "Reinstall tutor-any-lecture (imageio-ffmpeg bundles ffmpeg), or install ffmpeg and put it on PATH."),
    Check("asr_backend", True, check_asr_backend,
          "Reinstall tutor-any-lecture so its ASR backend is installed: "
          "mlx-whisper on Apple Silicon, faster-whisper elsewhere."),
    Check("yt_dlp", True, check_yt_dlp,
          "Reinstall tutor-any-lecture so yt-dlp is installed."),
    Check("config_dir", True, check_config_dir,
          "Make the tutor-any-lecture config folder writable, "
          "or point XDG_CONFIG_HOME (APPDATA on Windows) at a writable folder."),
    Check("js_runtime", False, check_js_runtime,
          "Optional: install deno 2.3+ or node 22+ if a YouTube extraction asks for a JavaScript runtime."),
    Check("browser", False, check_browser,
          "Optional: install Chrome, Chromium or Edge, or set CHROME_PATH to the browser executable; "
          "it is used only for rendered outputs."),
    Check("asr_model", False, check_asr_model,
          "Optional: the model downloads once, on the first transcription."),
]


def run_doctor() -> dict:
    """Run every check in ``CHECKS`` (read at call time). Never raises."""
    checks = []
    ready = True
    for c in CHECKS:
        fix = c.fix
        try:
            result = c.fn()
            ok, detail = bool(result[0]), result[1]
            if len(result) > 2:  # the check named a fix more specific than its default
                fix = result[2]
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        checks.append({"name": c.name, "ok": ok, "detail": detail, "fix": "" if ok else fix})
        if c.required and not ok:
            ready = False
    return {"ready": ready, "checks": checks, "version": __version__}
