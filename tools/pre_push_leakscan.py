"""Pre-push leak scan: block a push that would publish a private term or an unreviewed binary.

The terms live outside the repository, one per line, in <config_dir>/denylist.txt
(blank lines and lines starting with "#" are ignored; a leading byte-order mark is
dropped). Matching is case-insensitive. A term made only of ASCII letters, digits and
spaces matches only as a whole word (no ASCII letter or digit touching it on either
side); any other term matches as a substring.

What is scanned. Git runs a pre-push hook with one line per pushed ref on stdin:
"<local ref> <local sha> <remote ref> <remote sha>". For each line the commits in
<remote sha>..<local sha> are scanned, or <local sha> --not --remotes when the remote
ref is new; a deleted ref (local sha all zeros) publishes nothing. With nothing on
stdin (the script run by hand) it scans the staged diff and the commits of HEAD that
are not on origin/<branch>, or on no remote at all. Merge commits are shown against
each parent (git log -m), so a change made only in a merge is scanned too.

Binary files. Every file git reports as binary in the scanned changes blocks the push
unless its path matches an fnmatch pattern in <config_dir>/leakscan-allow.txt (one
pattern per line, blank and "#" lines ignored; the file is optional).

Fail closed. A denylist that is missing, unreadable, not UTF-8 or without a single
term blocks; so do an unreadable stdin, a malformed ref line, an unreadable allow
file and any failing git command. The hook lives only in the owner's clone.

Standard library only, Python 3.9-compatible syntax: the pre-push hook runs it with
the system python3. It resolves the config dir itself, with the same rule as
tutor_any_lecture.config.config_dir(), so it never imports the package.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

APP = "tutor-any-lecture"
GIT = ["git", "-c", "core.quotepath=false"]
BOM = "\ufeff"
# A term of only ASCII letters, digits and spaces is matched as a whole word.
WORD_TERM = re.compile(r"[A-Za-z0-9 ]+")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# Options for every diff-producing git call: the raw content, never a converted one.
DIFF_OPTS = ["--no-color", "--no-ext-diff", "--no-textconv"]


class GitError(Exception):
    """A git command could not run or exited non-zero."""


class Blocked(Exception):
    """The push must be blocked; the message is the one line that says why."""


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


def _entries(path: Path, what: str, required: bool) -> list[str]:
    """The non-blank, non-comment lines of a UTF-8 list file, stripped.

    A missing file is a Blocked error when required, else an empty list. A file that
    cannot be read or is not UTF-8 is always a Blocked error.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        if required:
            raise Blocked(f"leak scan: blocked, no {what} at {path}") from None
        return []
    except OSError as exc:
        reason = exc.strerror or exc.__class__.__name__
        raise Blocked(f"leak scan: blocked, cannot read the {what} {path}: {reason}") from None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Blocked(f"leak scan: blocked, the {what} {path} is not UTF-8") from None
    if text.startswith(BOM):
        text = text[1:]
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _term_found(term: str, text: str, folded: str) -> bool:
    if WORD_TERM.fullmatch(term):
        pattern = r"(?<![A-Za-z0-9])(?i:" + re.escape(term) + r")(?![A-Za-z0-9])"
        return re.search(pattern, text) is not None
    return term.casefold() in folded


def scan(text: str, denylist: list[str]) -> list[str]:
    """Return the denylist entries found in text, case-insensitively, in denylist order."""
    folded = text.casefold()
    hits = []
    for raw in denylist:
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if _term_found(entry, text, folded):
            hits.append(entry)
    return hits


def _stdin_text() -> str:
    """What git wrote on stdin; empty when there is no stdin or it is a terminal."""
    stream = sys.stdin
    if stream is None:
        return ""
    try:
        if stream.isatty():
            return ""
        buf = getattr(stream, "buffer", None)
        if buf is not None:
            return buf.read().decode("utf-8", errors="replace")
        return stream.read()
    except (OSError, ValueError) as exc:
        raise Blocked(f"leak scan: blocked, cannot read the pushed refs on stdin: {exc}") from None


def _pushed_ranges(text: str) -> list[list[str]]:
    """One git revision range per pushed ref line; a deleted ref adds none."""
    ranges = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4 or not SHA.fullmatch(parts[1]) or not SHA.fullmatch(parts[3]):
            raise Blocked(f"leak scan: blocked, cannot read the pushed ref line: {line.strip()}")
        local_sha, remote_sha = parts[1], parts[3]
        if set(local_sha) == {"0"}:
            continue
        if set(remote_sha) == {"0"}:
            ranges.append([local_sha, "--not", "--remotes"])
        else:
            ranges.append([f"{remote_sha}..{local_sha}"])
    return ranges


def _head_range() -> list[str]:
    """The unpushed commits of HEAD, for a scan run by hand."""
    branch = _git_text("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "HEAD":
        # The probe is the one git call whose non-zero exit is not an error.
        probe = _git("rev-parse", "--verify", "--quiet", f"origin/{branch}")
        if probe.returncode == 0:
            return [f"origin/{branch}..HEAD"]
    return ["HEAD", "--not", "--remotes"]


def _binary_paths(numstat_z: str) -> list[str]:
    """Paths that `--numstat -z --no-renames` reports as binary ("-" added, "-" deleted)."""
    paths = []
    for record in numstat_z.split("\0"):
        fields = record.lstrip("\n").split("\t", 2)
        if len(fields) == 3 and fields[0] == "-" and fields[1] == "-":
            paths.append(fields[2])
    return paths


def _collect(ranges: list[list[str]], staged: bool) -> tuple[str, list[str]]:
    """The text to scan and the binary paths, for the staged diff and each range."""
    parts = []
    binaries = []
    if staged:
        parts.append(_git_text("diff", "--cached", *DIFF_OPTS))
        numstat = _git_text("diff", "--cached", "--numstat", "-z", "--no-renames")
        binaries.extend(_binary_paths(numstat))
    for rev_range in ranges:
        # -m: a merge commit shows what it changed against each parent.
        parts.append(_git_text("log", "-p", "-m", *DIFF_OPTS, *rev_range))
        numstat = _git_text(
            "log", "-m", "--numstat", "-z", "--no-renames", "--format=", *rev_range
        )
        binaries.extend(_binary_paths(numstat))
    return "".join(parts), binaries


def main(argv: list[str] | None = None) -> int:
    """Return 0 when the push may go ahead, 1 when it must be blocked.

    argv (git passes the remote name and URL) is ignored.
    """
    cfg = _config_dir()
    denylist_path = cfg / "denylist.txt"
    allow_path = cfg / "leakscan-allow.txt"
    try:
        terms = _entries(denylist_path, "denylist", required=True)
        if not terms:
            raise Blocked(f"leak scan: blocked, the denylist {denylist_path} holds no term")
        allowed = _entries(allow_path, "binary allow list", required=False)
        refs = _stdin_text()
        if refs.strip():
            text, binaries = _collect(_pushed_ranges(refs), staged=False)
        else:
            text, binaries = _collect([_head_range()], staged=True)
    except Blocked as exc:
        _say(str(exc))
        return 1
    except GitError as exc:
        _say(f"leak scan: blocked, {exc}")
        return 1

    blocked = False
    hits = scan(text, terms)
    if hits:
        _say("leak scan: blocked, private terms found: " + ", ".join(hits))
        blocked = True
    unreviewed = []
    for path in binaries:
        if path in unreviewed or any(fnmatch.fnmatchcase(path, pat) for pat in allowed):
            continue
        unreviewed.append(path)
    if unreviewed:
        _say(
            f"leak scan: blocked, binary files not allowed by {allow_path}: "
            + ", ".join(unreviewed)
        )
        blocked = True
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
