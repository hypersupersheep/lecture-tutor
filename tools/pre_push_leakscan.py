"""Pre-push leak scan: block a push whose staged diff or unpushed commits contain a private term.

The terms live outside the repository, one per line, in <config_dir>/denylist.txt
(blank lines and lines starting with "#" are ignored). Matching is case-insensitive.
A missing denylist only warns; a failing git command blocks.

Standard library only, Python 3.9-compatible syntax: the pre-push hook runs it with
the system python3. It resolves the config dir itself, with the same rule as
tutor_any_lecture.config.config_dir(), so it never imports the package.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP = "tutor-any-lecture"
GIT = ["git", "-c", "core.quotepath=false"]


class GitError(Exception):
    """A git command could not run or exited non-zero."""


def _say(msg: str) -> None:
    """Print one line to stderr without ever raising on encoding."""
    buf = getattr(sys.stderr, "buffer", None)
    if buf is not None:
        buf.write((msg + "\n").encode("utf-8", "replace"))
        buf.flush()
    else:
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(errors="replace")
        print(msg, file=sys.stderr)


def _config_dir() -> Path:
    """Same rule as tutor_any_lecture.config.config_dir(), fallbacks included."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP


def _git(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([*GIT, *args], capture_output=True)
    except OSError as exc:
        raise GitError(f"git could not run: {exc}") from exc


def _git_text(*args: str) -> str:
    proc = _git(*args)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = err[0] if err else f"exit {proc.returncode}"
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.decode("utf-8", errors="replace")


def _log_range() -> list[str]:
    branch = _git_text("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "HEAD":
        # The probe is the one git call whose non-zero exit is not an error.
        probe = _git("rev-parse", "--verify", "--quiet", f"origin/{branch}")
        if probe.returncode == 0:
            return [f"origin/{branch}..HEAD"]
    return ["HEAD", "--not", "--remotes"]


def scan(text: str, denylist: list[str]) -> list[str]:
    """Return the denylist entries found in text, case-insensitively, in denylist order."""
    haystack = text.casefold()
    hits = []
    for raw in denylist:
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.casefold() in haystack:
            hits.append(entry)
    return hits


def main(argv: list[str] | None = None) -> int:
    """Return 0 when the push may go ahead, 1 when it must be blocked. argv is ignored."""
    denylist_path = _config_dir() / "denylist.txt"
    if not denylist_path.exists():
        _say(f"leak scan: warning: no denylist at {denylist_path}; nothing checked")
        return 0
    lines = denylist_path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("﻿"):
        lines[0] = lines[0][1:]

    try:
        log_range = _log_range()
        text = _git_text("diff", "--cached", "--no-color", "--no-ext-diff")
        text += _git_text("log", "-p", "--no-color", "--no-ext-diff", *log_range)
    except GitError as exc:
        _say(f"leak scan: {exc}")
        return 1

    hits = scan(text, lines)
    if hits:
        _say("leak scan: blocked, private terms found: " + ", ".join(hits))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
