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
    _stub(sub, "acquire")
    _stub(sub, "transcribe")
    _stub(sub, "slides")
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
