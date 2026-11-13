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
import signal
import sys
import threading
from datetime import date
from pathlib import Path

EXIT_OK = 0       # PASS or WARN, healthy transcript, doctor ready
EXIT_FAIL = 1     # a check failed
EXIT_USAGE = 2    # usage error, "not implemented" stub
EXIT_ACTION = 3   # needs user action
EXIT_INTERRUPTED = 130  # Ctrl+C (KeyboardInterrupt)
EXIT_STOPPED = 143      # SIGTERM, SIGHUP or SIGBREAK: an agent's shell timeout, a closed terminal

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
    "AcquireError": EXIT_FAIL,
    "ValueError": EXIT_FAIL,
}


def _one_line(e: Exception) -> str:
    """``str(e)`` with every run of whitespace collapsed to one space."""
    return " ".join(str(e).split())


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


def _print_json(obj) -> None:
    """Print ``obj`` as one JSON line on stdout.

    ASCII only (``ensure_ascii=True``): every non-ASCII character becomes a ``\\u`` escape,
    so a console with any code page shows the line unharmed and ``json.loads`` gives the
    original text back. JSON files keep ``ensure_ascii=False``.
    """
    print(json.dumps(obj, ensure_ascii=True))


def _path(value: str) -> Path:
    """argparse type for every path argument: ``~`` expanded, made absolute.

    Without it, ``--unit ~/x`` (quoted, or passed by an agent without a shell) would
    create a literal ``./~/x`` folder while the workspace went to the real home folder.
    """
    return Path(value).expanduser().absolute()


def _print_profile(profile) -> None:
    from .config import workspace

    shown = dataclasses.asdict(profile)
    # Printed as it resolves; profile.yaml keeps what the user wrote.
    shown["workspace"] = str(workspace(profile).absolute())
    _print_json(shown)


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


def _cmd_doctor(args) -> int:
    from . import doctor

    report = doctor.run_doctor()
    if args.json:
        _print_json(report)
    else:
        print(f"tutor-any-lecture {report['version']}")
        for check in report["checks"]:
            if check["ok"]:
                print(f"[ok] {check['name']}: {check['detail']}")
                continue
            tag = "[warn]" if check["fix"].startswith("Optional: ") else "[FAIL]"
            print(f"{tag} {check['name']}: {check['detail']}")
            print(f"  fix: {check['fix']}")
        print("ready" if report["ready"] else "not ready")
    return EXIT_OK if report["ready"] else EXIT_ACTION


def _run_acquire(call) -> int:
    """Run one acquisition and print its one-line JSON result.

    ``call`` takes no arguments and returns a ``Health``. A ``ValueError`` (an empty
    transcript, malformed or non-UTF-8 input), an ``AcquireError`` (a failed tool or
    ASR backend) or a ``FileNotFoundError`` (a missing input) becomes
    ``{"status": "error", ...}``. Other exceptions propagate to ``main``, which maps
    them through ``EXIT_BY_ERROR``.
    """
    from .transcript import AcquireError

    try:
        h = call()
    except (ValueError, AcquireError, FileNotFoundError) as e:
        _print_json({"status": "error", "message": str(e)})
        return EXIT_FAIL
    status = "ok" if h.ok else "unhealthy"
    _print_json({"status": status, "health": dataclasses.asdict(h)})
    return EXIT_OK if h.ok else EXIT_FAIL


def _cmd_acquire_import(args) -> int:
    from .acquire.importer import import_transcript

    return _run_acquire(lambda: import_transcript(Path(args.file), Path(args.unit), args.duration, args.force))


def _cmd_acquire_panopto(args) -> int:
    from .acquire.panopto import import_panopto

    return _run_acquire(lambda: import_panopto(Path(args.extract), Path(args.unit), args.force))


def _cmd_acquire_local(args) -> int:
    from .acquire.local import acquire_local
    from .profile import load_profile

    profile = load_profile()
    return _run_acquire(
        lambda: acquire_local(Path(args.file), Path(args.unit), profile, args.force, budget_minutes=args.budget_minutes)
    )


def _cmd_acquire_url(args) -> int:
    from .acquire.url import NeedsUserFile, acquire_url
    from .profile import load_profile

    profile = load_profile()
    try:
        return _run_acquire(
            lambda: acquire_url(args.url, Path(args.unit), profile, args.force, budget_minutes=args.budget_minutes)
        )
    except NeedsUserFile as e:
        _print_json({"status": "needs_user_file", "message": str(e)})
        return EXIT_BY_ERROR["NeedsUserFile"]


def _cmd_acquire_route(args) -> int:
    from .acquire.router import route

    plan = route(Path(args.folder), Path(args.unit))
    _print_json(plan)
    return EXIT_OK


def _cmd_transcribe(args) -> int:
    from .acquire.local import transcribe_audio
    from .profile import load_profile

    profile = load_profile()
    return _run_acquire(
        lambda: transcribe_audio(
            Path(args.audio), Path(args.unit), profile, args.force,
            budget_minutes=args.budget_minutes, backend=args.backend, model=args.model,
        )
    )


_SLIDES_USAGE = (
    "usage: tutor-any-lecture slides --pdf F --unit DIR [--images]"
    " | tutor-any-lecture slides suspects --unit DIR"
)


def _cmd_slides(args) -> int:
    if args.pdf is None or args.unit is None:
        print(_SLIDES_USAGE, file=sys.stderr)
        return EXIT_USAGE

    from .slides import extract_pdf

    pages = extract_pdf(Path(args.pdf), Path(args.unit), images=args.images)
    labelled = sum(1 for p in pages if p.label is not None)
    _print_json({"status": "ok", "pages": len(pages), "labelled": labelled})
    return EXIT_OK


def _cmd_slides_suspects(args) -> int:
    if args.pdf is not None:
        # "slides --pdf F suspects": two commands in one; run neither.
        print(_SLIDES_USAGE, file=sys.stderr)
        return EXIT_USAGE

    from .suspects import write_suspects

    found = write_suspects(Path(args.unit))
    _print_json({"status": "ok", "suspects": len(found)})
    return EXIT_OK


def _cmd_items_validate(args) -> int:
    from .items import validate_unit

    try:
        results = validate_unit(Path(args.unit))
    except ValueError as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_FAIL
    statuses = {r.status for r in results}
    status = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    _print_json({"status": status, "results": [dataclasses.asdict(r) for r in results]})
    return EXIT_FAIL if status == "FAIL" else EXIT_OK


def _cmd_items_assign(args) -> int:
    from .items import assign_unit

    try:
        assignment = assign_unit(Path(args.unit), args.force)
    except ValueError as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_FAIL
    _print_json(assignment)
    return EXIT_OK


def _cmd_items_next(args) -> int:
    from .items import next_for_unit

    try:
        out = next_for_unit(Path(args.unit), args.phase)
    except ValueError as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_FAIL
    _print_json(out)
    return EXIT_OK


def _cmd_items_get(args) -> int:
    from .items import get_from_unit

    try:
        item = get_from_unit(Path(args.unit), args.id)
    except KeyError:
        print(f"unknown item id: {args.id}", file=sys.stderr)
        return EXIT_USAGE
    except ValueError as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_FAIL
    _print_json(dataclasses.asdict(item))
    return EXIT_OK


def _cmd_cards_export(args) -> int:
    from . import cards

    try:
        path = cards.export_tsv(Path(args.unit))
    except ValueError as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_FAIL
    _print_json({"path": str(path)})
    return EXIT_OK


def _cmd_cards_add_misses(args) -> int:
    from . import cards, config
    from .plan import load_plan
    from .unit import UnitPaths

    unit = Path(args.unit)
    course = load_plan(UnitPaths(unit).plan).course
    ws = Path(args.workspace) if args.workspace is not None else config.workspace()
    try:
        added = cards.add_misses(unit, course, ws)
    except ValueError as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_FAIL
    _print_json({"added": added, "path": str(UnitPaths(unit).cards_tsv)})
    return EXIT_OK


def _cmd_progress_log(args) -> int:
    from . import config, progress

    ws = Path(args.workspace) if args.workspace is not None else config.workspace()
    try:
        a = progress.log_from_unit(
            Path(args.unit), args.item, args.phase, args.score, args.confidence, args.exposure, ws
        )
    except KeyError:
        print(f"unknown item id: {args.item}", file=sys.stderr)
        return EXIT_USAGE
    _print_json(dataclasses.asdict(a))
    return EXIT_OK


def _cmd_progress_due(args) -> int:
    from . import config, progress

    ws = Path(args.workspace) if args.workspace is not None else config.workspace()
    day = args.date if args.date is not None else date.today()
    _print_json(progress.due(progress.load_attempts(args.course, ws), day))
    return EXIT_OK


def _cmd_progress_render(args) -> int:
    from . import config, progress

    ws = Path(args.workspace) if args.workspace is not None else config.workspace()
    path = progress.render_progress(args.course, ws, date.today())
    print(str(path))
    return EXIT_OK


def _cmd_map_validate(args) -> int:
    from . import conceptmap

    # An unreadable or malformed map.json raises ValueError, which main maps to EXIT_FAIL.
    results = conceptmap.validate_unit(Path(args.unit))
    print(conceptmap.format_results(results))
    return EXIT_FAIL if any(r.status == "FAIL" for r in results) else EXIT_OK


def _cmd_map_mermaid(args) -> int:
    from . import conceptmap

    # An unreadable or malformed map.json raises ValueError, which main maps to EXIT_FAIL.
    try:
        path = conceptmap.export_mermaid(Path(args.unit), args.view)
    except conceptmap.MapInvalid as e:
        print(conceptmap.format_results(e.results), file=sys.stderr)
        return EXIT_FAIL
    except conceptmap.UnknownView as e:
        print(_one_line(e), file=sys.stderr)
        return EXIT_USAGE
    print(str(path))
    return EXIT_OK


def _cmd_verify(args) -> int:
    from .verify import run_verify

    result = run_verify(Path(args.unit))
    if args.json:
        _print_json(result)
    else:
        for check in result["checks"]:
            print(f"{check['status']:<4}  {check['name']}")
            if check["status"] != "PASS":
                for detail in check["details"]:
                    print(f"      {detail}")
        print(result["report"])
    return EXIT_OK if result["overall"] == "PASS" else EXIT_FAIL


def _cmd_selftest(args) -> int:
    from .selftest import run_selftest

    # A non-empty --keep folder raises FileExistsError, which main maps to EXIT_ACTION.
    result = run_selftest(Path(args.keep)) if args.keep is not None else run_selftest()
    for step in result["steps"]:
        print(f"{'ok' if step['ok'] else 'FAIL':<4}  {step['name']}: {step['detail']}")
    if args.keep is not None:
        print(f"unit folder: {Path(args.keep)}")
    return EXIT_OK if result["ok"] else EXIT_FAIL


def _positive_number(value: str) -> float:
    """argparse type for --duration and --budget-minutes: a positive, finite number."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive, finite number: {value!r}")
    return number


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

    doc = sub.add_parser("doctor", help="check that this machine is ready to run the tool")
    doc.add_argument("--json", action="store_true", help="print the report as one JSON line")
    doc.set_defaults(func=_cmd_doctor)
    acquire = sub.add_parser("acquire", help="get a lecture's transcript into a unit folder")
    acquire_sub = acquire.add_subparsers(dest="acquire_command")

    def _acquire_usage(args) -> int:
        # A bare "acquire" names no source: show the group's usage, exit as a usage error.
        acquire.print_usage(sys.stderr)
        return EXIT_USAGE

    acquire.set_defaults(func=_acquire_usage)
    imp = acquire_sub.add_parser("import", help="import a transcript file (.srt, .vtt, .json, .txt)")
    imp.add_argument("--file", type=_path, required=True, help="the transcript file")
    imp.add_argument("--unit", type=_path, required=True, help="the unit folder")
    imp.add_argument("--duration", type=_positive_number, default=None, help="the lecture length in seconds, if known")
    imp.add_argument("--force", action="store_true", help="replace an existing transcript")
    imp.set_defaults(func=_cmd_acquire_import)
    pan = acquire_sub.add_parser("panopto", help="import the JSON that panopto_extract.js returns")
    pan.add_argument("--extract", type=_path, required=True, help="the extract JSON file")
    pan.add_argument("--unit", type=_path, required=True, help="the unit folder")
    pan.add_argument("--force", action="store_true", help="replace an existing transcript")
    pan.set_defaults(func=_cmd_acquire_panopto)
    loc = acquire_sub.add_parser("local", help="transcribe a local video or audio file with ASR")
    loc.add_argument("--file", type=_path, required=True, help="the video or audio file")
    loc.add_argument("--unit", type=_path, required=True, help="the unit folder")
    loc.add_argument("--force", action="store_true", help="replace an existing transcript")
    loc.add_argument("--budget-minutes", type=_positive_number, default=None,
                     help="stop ASR after this many minutes (default: max(30, 2 x the media length))")
    loc.set_defaults(func=_cmd_acquire_local)
    url = acquire_sub.add_parser("url", help="get a public video's captions, or (with consent) its audio")
    url.add_argument("--url", required=True, help="the video URL")
    url.add_argument("--unit", type=_path, required=True, help="the unit folder")
    url.add_argument("--force", action="store_true", help="replace an existing transcript")
    url.add_argument("--budget-minutes", type=_positive_number, default=None,
                     help="stop ASR after this many minutes (default: max(30, 2 x the video length))")
    url.set_defaults(func=_cmd_acquire_url)
    rte = acquire_sub.add_parser("route", help="plan the acquisition commands for a materials folder (runs nothing)")
    rte.add_argument("--folder", type=_path, required=True, help="the materials folder")
    rte.add_argument("--unit", type=_path, required=True, help="the unit folder")
    rte.set_defaults(func=_cmd_acquire_route)
    tr = sub.add_parser("transcribe", help="transcribe an audio file as it is, with ASR")
    tr.add_argument("--audio", type=_path, required=True, help="the audio file")
    tr.add_argument("--unit", type=_path, required=True, help="the unit folder")
    tr.add_argument("--backend", default=None, help="the ASR backend (mlx or faster; default: chosen for this machine)")
    tr.add_argument("--model", default=None, help="the ASR model (default: chosen for the backend and machine)")
    tr.add_argument("--budget-minutes", type=_positive_number, default=None,
                    help="stop ASR after this many minutes (default: max(30, 2 x the media length))")
    tr.add_argument("--force", action="store_true", help="replace an existing transcript")
    tr.set_defaults(func=_cmd_transcribe)
    slides = sub.add_parser("slides", help="read a slide PDF into the unit, or flag ASR suspects")
    slides.add_argument("--pdf", type=_path, default=None, help="the slide PDF")
    slides.add_argument("--unit", type=_path, default=None, help="the unit folder")
    slides.add_argument("--images", action="store_true", help="also save one PNG per page")
    slides.set_defaults(func=_cmd_slides)
    slides_sub = slides.add_subparsers(dest="slides_command")
    suspects = slides_sub.add_parser("suspects", help="flag transcript words that look like misheard slide terms")
    suspects.add_argument("--unit", type=_path, required=True, help="the unit folder")
    suspects.set_defaults(func=_cmd_slides_suspects)
    items = sub.add_parser("items", help="check the item bank, assign variants, pick items to ask")
    items_sub = items.add_subparsers(dest="items_command", required=True)
    iv = items_sub.add_parser("validate", help="check items.json against plan.json and explanation.md")
    iv.add_argument("--unit", type=_path, required=True, help="the unit folder")
    iv.set_defaults(func=_cmd_items_validate)
    ia = items_sub.add_parser("assign", help="assign variants A/B/C to pre/post/d7 (reuses assignment.json)")
    ia.add_argument("--unit", type=_path, required=True, help="the unit folder")
    ia.add_argument("--force", action="store_true", help="replace an existing assignment.json")
    ia.set_defaults(func=_cmd_items_assign)
    inx = items_sub.add_parser("next", help="print the items to ask in one phase")
    inx.add_argument("--unit", type=_path, required=True, help="the unit folder")
    inx.add_argument("--phase", required=True, choices=["pre", "post", "d1", "d7", "d21"], help="the phase")
    inx.set_defaults(func=_cmd_items_next)
    ig = items_sub.add_parser("get", help="print one item by id")
    ig.add_argument("--unit", type=_path, required=True, help="the unit folder")
    ig.add_argument("--id", required=True, help="the item id")
    ig.set_defaults(func=_cmd_items_get)
    cards = sub.add_parser("cards", help="export Anki cards, add cards for missed quiz items")
    cards_sub = cards.add_subparsers(dest="cards_command", required=True)
    ce = cards_sub.add_parser("export", help="write cards.tsv (Anki import) from cards.json")
    ce.add_argument("--unit", type=_path, required=True, help="the unit folder")
    ce.set_defaults(func=_cmd_cards_export)
    cm = cards_sub.add_parser(
        "add-misses", help="add a card for each item missed after the lecture; course comes from plan.json"
    )
    cm.add_argument("--unit", type=_path, required=True, help="the unit folder")
    cm.add_argument("--workspace", type=_path, default=None, help="the workspace folder (default: the profile's)")
    cm.set_defaults(func=_cmd_cards_add_misses)
    progress = sub.add_parser("progress", help="log quiz attempts, list due reviews, render the progress page")
    progress_sub = progress.add_subparsers(dest="progress_command", required=True)
    pl = progress_sub.add_parser("log", help="log one attempt at an item; course and unit come from plan.json")
    pl.add_argument("--unit", type=_path, required=True, help="the unit folder")
    pl.add_argument("--item", required=True, help="the item id")
    pl.add_argument("--phase", required=True, choices=["pre", "post", "d1", "d7", "d21", "practice"], help="the phase")
    pl.add_argument("--score", required=True, type=float, choices=[0.0, 0.5, 1.0], help="the score")
    pl.add_argument("--confidence", required=True, type=int, choices=[1, 2, 3], help="the confidence")
    pl.add_argument("--exposure", default="unknown", choices=["none", "attended", "watched", "unknown"],
                    help="how the lecture was seen (default: unknown)")
    pl.add_argument("--workspace", type=_path, default=None, help="the workspace folder (default: the profile's)")
    pl.set_defaults(func=_cmd_progress_log)
    pd = progress_sub.add_parser("due", help="print the reviews due as JSON")
    pd.add_argument("--course", required=True, help="the course name, as in plan.json")
    pd.add_argument("--date", type=date.fromisoformat, default=None, help="the day, YYYY-MM-DD (default: today)")
    pd.add_argument("--workspace", type=_path, default=None, help="the workspace folder (default: the profile's)")
    pd.set_defaults(func=_cmd_progress_due)
    pr = progress_sub.add_parser("render", help="write the course's progress page")
    pr.add_argument("--course", required=True, help="the course name, as in plan.json")
    pr.add_argument("--workspace", type=_path, default=None, help="the workspace folder (default: the profile's)")
    pr.set_defaults(func=_cmd_progress_render)
    map_ = sub.add_parser("map", help="check the concept map, export it as a Mermaid flowchart")
    map_sub = map_.add_subparsers(dest="map_command", required=True)
    mv = map_sub.add_parser("validate", help="check map.json")
    mv.add_argument("--unit", type=_path, required=True, help="the unit folder")
    mv.set_defaults(func=_cmd_map_validate)
    mm = map_sub.add_parser("mermaid", help="write overview.mmd from map.json")
    mm.add_argument("--unit", type=_path, required=True, help="the unit folder")
    mm.add_argument("--view", default=None, help="export only this view (default: the whole map)")
    mm.set_defaults(func=_cmd_map_mermaid)
    ver = sub.add_parser("verify", help="run the delivery gate on a unit and write verify.json")
    ver.add_argument("--unit", type=_path, required=True, help="the unit folder")
    ver.add_argument("--json", action="store_true", help="print the result as one JSON line instead of a table")
    ver.set_defaults(func=_cmd_verify)
    st = sub.add_parser("selftest", help="run the bundled sample unit through the offline pipeline")
    st.add_argument("--keep", type=_path, default=None, metavar="DIR",
                    help="generate the unit in this new or empty folder and keep it")
    st.set_defaults(func=_cmd_selftest)
    return parser


# The signals that stop a command; SIGHUP exists on POSIX, SIGBREAK on Windows.
_STOP_SIGNALS = ("SIGTERM", "SIGHUP", "SIGBREAK")


def _stop(signum, frame) -> None:
    """Signal handler: end the command through ``SystemExit``, so every ``finally`` runs."""
    # Every stop signal this handler serves is ignored from here on, not only this one: a
    # second signal of any kind must not cut the cleanup short. ``main`` puts the old
    # handlers back once the cleanup is done.
    for name in _STOP_SIGNALS:
        other = getattr(signal, name, None)
        if other is None:
            continue
        try:
            if signal.getsignal(other) is _stop:
                signal.signal(other, signal.SIG_IGN)
        except (OSError, ValueError):
            pass
    raise SystemExit(EXIT_STOPPED)


def _install_stop_handlers() -> dict:
    """Route the stop signals to ``_stop``; returns the handlers they replaced.

    Only in the main thread, the one place Python allows it.
    """
    replaced: dict = {}
    if threading.current_thread() is not threading.main_thread():
        return replaced
    for name in _STOP_SIGNALS:
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            replaced[signum] = signal.signal(signum, _stop)
        except (OSError, ValueError):
            continue
    return replaced


def _restore_handlers(replaced: dict) -> None:
    for signum, handler in replaced.items():
        if handler is None:  # installed outside Python; it cannot be put back
            continue
        try:
            signal.signal(signum, handler)
        except (OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    # A stopped command (SIGTERM from an agent's shell timeout) still removes its temp
    # folder and ends a running ASR child: the handler raises SystemExit(143).
    replaced = _install_stop_handlers()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as e:
        for cls in type(e).__mro__:
            code = EXIT_BY_ERROR.get(cls.__name__)
            if code is not None:
                print(_one_line(e), file=sys.stderr)
                return code
        raise
    finally:
        _restore_handlers(replaced)
