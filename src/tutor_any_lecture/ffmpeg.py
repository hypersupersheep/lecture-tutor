"""The ffmpeg binary: find it, read a media file's duration, extract 16 kHz mono audio."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


def ffmpeg_exe() -> str:
    """ffmpeg on PATH, otherwise the binary bundled with imageio-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def stderr_tail(raw: bytes, lines: int = 10) -> str:
    """The last ``lines`` lines of ffmpeg's stderr, decoded as UTF-8 with replacement."""
    text = raw.decode("utf-8", errors="replace").strip()
    return "\n".join(text.splitlines()[-lines:])


def media_duration(path: Path) -> float | None:
    """Seconds from ffmpeg's ``Duration:`` line, or None when it has none (e.g. ``N/A``)."""
    # "ffmpeg -i" with no output file exits non-zero by design, so no check=True here.
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(path)],
        capture_output=True,
    )
    m = _DURATION_RE.search(proc.stderr.decode("utf-8", errors="replace"))
    if m is None:
        return None
    h, mins, secs = m.groups()
    return int(h) * 3600 + int(mins) * 60 + float(secs)


def extract_audio(src: Path, dst_wav: Path) -> None:
    """Write ``src``'s audio to ``dst_wav`` as 16 kHz mono 16-bit PCM."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-nostdin", "-y", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst_wav)],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not extract audio from {src}:\n{stderr_tail(proc.stderr)}")
