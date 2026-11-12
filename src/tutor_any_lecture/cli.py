"""Command-line entry point: the argparse tree, the exit-code table and the handlers.

Handler convention: a handler is a module-level function ``_cmd_<path>(args) -> int``,
registered with ``set_defaults(func=...)`` inside ``build_parser()``. It imports its
module inside the function body, so ``--help`` works even when an optional dependency
is missing. It raises, or returns one of the four exit constants; it never calls
``sys.exit`` or ``parser.error``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys

EXIT_OK = 0       # PASS or WARN, healthy transcript, doctor ready
EXIT_FAIL = 1     # a check failed
EXIT_USAGE = 2    # usage error, "not implemented" stub
EXIT_ACTION = 3   # needs user action

# Keyed by exception class name, so this module imports none of the modules defining them.
EXIT_BY_ERROR: dict[str, int] = {
    "ConsentRequired": EXIT_ACTION,
    "NeedsUserFile": EXIT_ACTION,
    "BudgetExceeded": EXIT_ACTION,
    "BackendMissing": EXIT_ACTION,
    "FileExistsError": EXIT_ACTION,
    "ProfileError": EXIT_FAIL,
    "PlanError": EXIT_FAIL,
    "FileNotFoundError": EXIT_FAIL,
}


def _not_implemented(args) -> int:
    print("not implemented", file=sys.stderr)
    return EXIT_USAGE


def _stub(sub, name) -> None:
    """Register ``name`` as a placeholder that accepts any arguments."""
    # With a NUL prefix character no argument is read as an option, so
    # "--json", "-x" and even "--help" all land in ``rest``.
    p = sub.add_parser(name, help="not implemented yet", add_help=False, prefix_chars="\x00")
    p.add_argument("rest", nargs="*")
    p.set_defaults(func=_not_implemented)


def _print_profile(profile) -> None:
    print(json.dumps(dataclasses.asdict(profile), ensure_ascii=False))


def _cmd_profile_show(args) -> int:
    from .profile import load_profile

    _print_profile(load_profile())
    return EXIT_OK


def _cmd_profile_set(args) -> int:
    from .profile import ConsentRequired, set_value

    try:
        profile = set_value(args.key, args.value, i_understand=args.i_understand)
    except ConsentRequired as e:
        print(e.notice)
        print(
            f"Profile not changed. If you agree, rerun with --i-understand: "
            f"tutor-any-lecture profile set {args.key} {args.value} --i-understand",
            file=sys.stderr,
        )
        return EXIT_BY_ERROR["ConsentRequired"]
    _print_profile(profile)
    return EXIT_OK


def _run_acquire(call) -> int:
    """Run one acquisition and print its one-line JSON result.

    ``call`` takes no arguments and returns a ``Health``. Exceptions other than
    ``EmptyTranscript`` propagate to ``main``, which maps them through ``EXIT_BY_ERROR``.
    """
    from .transcript import EmptyTranscript

    try:
        h = call()
    except EmptyTranscript as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        return EXIT_FAIL
    status = "ok" if h.ok else "unhealthy"
    print(json.dumps({"status": status, "health": dataclasses.asdict(h)}, ensure_ascii=False))
    return EXIT_OK if h.ok else EXIT_FAIL


def _cmd_acquire_import(args) -> int:
    from pathlib import Path

    from .acquire.importer import import_transcript

    return _run_acquire(lambda: import_transcript(Path(args.file), Path(args.unit), args.duration, args.force))


def _cmd_acquire_panopto(args) -> int:
    from pathlib import Path

    from .acquire.panopto import import_panopto

    return _run_acquire(lambda: import_panopto(Path(args.extract), Path(args.unit), args.force))


def _cmd_acquire_local(args) -> int:
    from pathlib import Path

    from .acquire.local import acquire_local
    from .profile import load_profile

    profile = load_profile()
    return _run_acquire(
        lambda: acquire_local(Path(args.file), Path(args.unit), profile, args.force, budget_minutes=args.budget_minutes)
    )


def _cmd_acquire_url(args) -> int:
    from pathlib import Path

    from .acquire.url import NeedsUserFile, acquire_url
    from .profile import load_profile

    profile = load_profile()
    try:
        return _run_acquire(lambda: acquire_url(args.url, Path(args.unit), profile, args.force))
    except NeedsUserFile as e:
        print(json.dumps({"status": "needs_user_file", "message": str(e)}, ensure_ascii=False))
        return EXIT_BY_ERROR["NeedsUserFile"]


def _cmd_transcribe(args) -> int:
    from pathlib import Path

    from .acquire.local import transcribe_audio
    from .profile import load_profile

    profile = load_profile()
    return _run_acquire(
        lambda: transcribe_audio(
            Path(args.audio), Path(args.unit), profile, args.force,
            budget_minutes=args.budget_minutes, backend=args.backend, model=args.model,
        )
    )


def _cmd_slides(args) -> int:
    if args.pdf is None or args.unit is None:
        print(
            "usage: tutor-any-lecture slides --pdf F --unit DIR [--images]"
            " | tutor-any-lecture slides suspects --unit DIR",
            file=sys.stderr,
        )
        return EXIT_USAGE

    from pathlib import Path

    from .slides import extract_pdf

    pages = extract_pdf(Path(args.pdf), Path(args.unit), images=args.images)
    labelled = sum(1 for p in pages if p.label is not None)
    print(json.dumps({"status": "ok", "pages": len(pages), "labelled": labelled}, ensure_ascii=False))
    return EXIT_OK


def _cmd_slides_suspects(args) -> int:
    from pathlib import Path

    from .suspects import write_suspects

    found = write_suspects(Path(args.unit))
    print(json.dumps({"status": "ok", "suspects": len(found)}, ensure_ascii=False))
    return EXIT_OK


def _positive_seconds(value: str) -> float:
    """argparse type for --duration: a positive, finite number of seconds."""
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {value!r}") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive, finite number of seconds: {value!r}")
    return seconds


def build_parser() -> argparse.ArgumentParser:
    """The only place subcommands are registered. Builds a fresh parser on every call."""
    parser = argparse.ArgumentParser(
        prog="tutor-any-lecture",
        description="Turn any lecture video, recording or slide deck into a tutor.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("profile", help="show or change your profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    show = profile_sub.add_parser("show", help="print the effective profile as JSON")
    show.set_defaults(func=_cmd_profile_show)
    set_ = profile_sub.add_parser("set", help="change one profile key")
    set_.add_argument("key", metavar="KEY")
    set_.add_argument("value", metavar="VALUE")
    set_.add_argument(
        "--i-understand",
        action="store_true",
        help="consent to the notice shown when turning public_video_audio on",
    )
    set_.set_defaults(func=_cmd_profile_set)

    _stub(sub, "doctor")
    acquire = sub.add_parser("acquire", help="get a lecture's transcript into a unit folder")
    acquire_sub = acquire.add_subparsers(dest="acquire_command")

    def _acquire_usage(args) -> int:
        # A bare "acquire" names no source: show the group's usage, exit as a usage error.
        acquire.print_usage(sys.stderr)
        return EXIT_USAGE

    acquire.set_defaults(func=_acquire_usage)
    imp = acquire_sub.add_parser("import", help="import a transcript file (.srt, .vtt, .json, .txt)")
    imp.add_argument("--file", required=True, help="the transcript file")
    imp.add_argument("--unit", required=True, help="the unit folder")
    imp.add_argument("--duration", type=_positive_seconds, default=None, help="the lecture length in seconds, if known")
    imp.add_argument("--force", action="store_true", help="replace an existing transcript")
    imp.set_defaults(func=_cmd_acquire_import)
    pan = acquire_sub.add_parser("panopto", help="import the JSON that panopto_extract.js returns")
    pan.add_argument("--extract", required=True, help="the extract JSON file")
    pan.add_argument("--unit", required=True, help="the unit folder")
    pan.add_argument("--force", action="store_true", help="replace an existing transcript")
    pan.set_defaults(func=_cmd_acquire_panopto)
    loc = acquire_sub.add_parser("local", help="transcribe a local video or audio file with ASR")
    loc.add_argument("--file", required=True, help="the video or audio file")
    loc.add_argument("--unit", required=True, help="the unit folder")
    loc.add_argument("--force", action="store_true", help="replace an existing transcript")
    loc.add_argument("--budget-minutes", type=float, default=None,
                     help="stop ASR after this many minutes (default: max(30, 2 x the media length))")
    loc.set_defaults(func=_cmd_acquire_local)
    url = acquire_sub.add_parser("url", help="get a public video's captions, or (with consent) its audio")
    url.add_argument("--url", required=True, help="the video URL")
    url.add_argument("--unit", required=True, help="the unit folder")
    url.add_argument("--force", action="store_true", help="replace an existing transcript")
    url.set_defaults(func=_cmd_acquire_url)
    tr = sub.add_parser("transcribe", help="transcribe an audio file as it is, with ASR")
    tr.add_argument("--audio", required=True, help="the audio file")
    tr.add_argument("--unit", required=True, help="the unit folder")
    tr.add_argument("--backend", default=None, help="the ASR backend (mlx or faster; default: chosen for this machine)")
    tr.add_argument("--model", default=None, help="the ASR model (default: chosen for the backend and machine)")
    tr.add_argument("--budget-minutes", type=float, default=None,
                    help="stop ASR after this many minutes (default: max(30, 2 x the media length))")
    tr.add_argument("--force", action="store_true", help="replace an existing transcript")
    tr.set_defaults(func=_cmd_transcribe)
    slides = sub.add_parser("slides", help="read a slide PDF into the unit, or flag ASR suspects")
    slides.add_argument("--pdf", default=None, help="the slide PDF")
    slides.add_argument("--unit", default=None, help="the unit folder")
    slides.add_argument("--images", action="store_true", help="also save one PNG per page")
    slides.set_defaults(func=_cmd_slides)
    slides_sub = slides.add_subparsers(dest="slides_command")
    suspects = slides_sub.add_parser("suspects", help="flag transcript words that look like misheard slide terms")
    suspects.add_argument("--unit", required=True, help="the unit folder")
    suspects.set_defaults(func=_cmd_slides_suspects)
    _stub(sub, "items")
    _stub(sub, "cards")
    _stub(sub, "progress")
    _stub(sub, "map")
    _stub(sub, "verify")
    _stub(sub, "selftest")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        for cls in type(e).__mro__:
            code = EXIT_BY_ERROR.get(cls.__name__)
            if code is not None:
                print(str(e), file=sys.stderr)
                return code
        raise
