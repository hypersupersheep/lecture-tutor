import argparse
import json
import re
import shutil
import signal
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from tutor_any_lecture import cli
from tutor_any_lecture.cli import main


def top_level_commands():
    for action in cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_cli_help_lists_groups(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert all(g in out for g in ["doctor", "acquire", "verify", "progress", "cards", "items", "map", "selftest", "cite"])


def test_parser_registers_twelve_groups():
    assert top_level_commands() == {
        "profile", "doctor", "acquire", "transcribe", "slides", "items",
        "cards", "cite", "progress", "map", "verify", "selftest",
    }


def test_exit_table():
    assert (cli.EXIT_OK, cli.EXIT_FAIL, cli.EXIT_USAGE, cli.EXIT_ACTION) == (0, 1, 2, 3)
    assert cli.EXIT_BY_ERROR == {
        "ConsentRequired": 3,
        "NeedsUserFile": 3,
        "BudgetExceeded": 3,
        "BackendMissing": 3,
        "FileExistsError": 3,
        "ProfileError": 1,
        "PlanError": 1,
        "FileNotFoundError": 1,
        "AcquireError": 1,
        "ValueError": 1,
    }


def test_acquire_error_is_in_the_exit_table():
    assert cli.EXIT_BY_ERROR["AcquireError"] == cli.EXIT_FAIL


def test_value_error_is_in_the_exit_table():
    assert cli.EXIT_BY_ERROR["ValueError"] == cli.EXIT_FAIL


def test_main_prints_a_mapped_error_on_one_line(monkeypatch, capsys):
    def boom(args):
        raise ValueError("items.json: first line\n   second\tline")

    monkeypatch.setattr(cli, "_cmd_profile_show", boom)
    assert main(["profile", "show"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "items.json: first line second line\n"


def test_not_implemented_returns_usage(capsys):
    assert cli._not_implemented(argparse.Namespace()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "not implemented" in captured.err


def test_stub_accepts_any_arguments(capsys):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    cli._stub(sub, "later")
    args = parser.parse_args(["later", "--json", "--unit", "课程 资料/第1周", "-x", "--help"])
    assert args.func(args) == 2
    assert "not implemented" in capsys.readouterr().err


def test_main_maps_errors_by_class_name(monkeypatch, capsys):
    class Clash(FileExistsError):
        pass

    def boom(args):
        raise Clash("transcript.json exists; rerun with --force")

    monkeypatch.setattr(cli, "_cmd_profile_show", boom)
    assert main(["profile", "show"]) == 3
    assert "--force" in capsys.readouterr().err


def test_main_lets_unlisted_errors_propagate(monkeypatch):
    def boom(args):
        raise ZeroDivisionError("unlisted")

    monkeypatch.setattr(cli, "_cmd_profile_show", boom)
    with pytest.raises(ZeroDivisionError):
        main(["profile", "show"])


def test_profile_set_needs_consent_returns_3(tmp_cfg, capsys):
    assert main(["profile", "set", "public_video_audio", "on"]) == 3
    captured = capsys.readouterr()
    assert "personal study only" in captured.out
    assert "--i-understand" in captured.err


def test_profile_set_with_flag_then_show(tmp_cfg, capsys):
    assert main(["profile", "set", "public_video_audio", "on", "--i-understand"]) == 0
    capsys.readouterr()
    assert main(["profile", "show"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["public_video_audio"] == "on" and shown["goal"] == "deep"


def test_profile_set_bad_value_returns_1(tmp_cfg, capsys):
    assert main(["profile", "set", "goal", "fast"]) == 1
    assert "goal" in capsys.readouterr().err


def toml_list(text, key):
    """Local helper: the quoted strings of the list ``key = [...]`` that starts a line of ``text``."""
    m = re.search(rf"^{re.escape(key)}\s*=\s*\[(.*?)\]", text, re.M | re.S)
    assert m is not None, key
    return re.findall(r'"([^"]*)"', m.group(1))


def toml_section(text, header):
    """Local helper: the lines of ``text`` under ``[header]``, up to the next table header."""
    start = text.index(f"[{header}]\n") + len(header) + 3
    end = text.find("\n[", start)
    return text[start:] if end == -1 else text[start:end]


def test_asr_is_an_extra():
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    backends = ("mlx-whisper", "faster-whisper")
    deps = toml_list(toml_section(text, "project"), "dependencies")
    assert deps and not any(b in d for d in deps for b in backends)
    extra = toml_list(toml_section(text, "project.optional-dependencies"), "asr")
    assert all(any(d.startswith(b) for d in extra) for b in backends)
    assert "mlx-whisper>=0.4; sys_platform == 'darwin' and platform_machine == 'arm64'" in extra
    assert "faster-whisper>=1.1; sys_platform != 'darwin' or platform_machine != 'arm64'" in extra


def test_keyboard_interrupt_is_exit_130(monkeypatch, tmp_path, capsys):
    from tutor_any_lecture.acquire import local

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    folders = []

    def interrupted(args):
        with local.temp_dir() as tmp:
            folders.append(tmp)
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_cmd_profile_show", interrupted)
    assert main(["profile", "show"]) == 130
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "interrupted\n"
    assert folders and not folders[0].exists()


def test_sigterm_handler_is_exit_143(monkeypatch):
    before = signal.getsignal(signal.SIGTERM)

    def stopped(args):
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not before
        handler(signal.SIGTERM, None)

    monkeypatch.setattr(cli, "_cmd_profile_show", stopped)
    with pytest.raises(SystemExit) as exc:
        main(["profile", "show"])
    assert exc.value.code == 143
    assert signal.getsignal(signal.SIGTERM) is before   # main puts the old handler back


def test_one_stop_signal_ignores_every_stop_signal(monkeypatch):
    names = [n for n in ("SIGTERM", "SIGHUP", "SIGBREAK") if hasattr(signal, n)]
    before = {n: signal.getsignal(getattr(signal, n)) for n in names}
    during = {}

    def stopped(args):
        try:
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        finally:
            # Where the cleanup runs: a second signal of any of these kinds is ignored.
            during.update({n: signal.getsignal(getattr(signal, n)) for n in names})

    monkeypatch.setattr(cli, "_cmd_profile_show", stopped)
    with pytest.raises(SystemExit) as exc:
        main(["profile", "show"])
    assert exc.value.code == 143
    assert len(names) >= 2 and during == {n: signal.SIG_IGN for n in names}
    assert {n: signal.getsignal(getattr(signal, n)) for n in names} == before   # put back afterwards


def test_handlers_only_in_the_main_thread(monkeypatch):
    before = signal.getsignal(signal.SIGTERM)
    seen, codes = [], []

    def record(args):
        seen.append(signal.getsignal(signal.SIGTERM))
        return 0

    monkeypatch.setattr(cli, "_cmd_profile_show", record)
    worker = threading.Thread(target=lambda: codes.append(main(["profile", "show"])))
    worker.start()
    worker.join()
    assert codes == [0] and seen == [before]


# ---- paths and stdout JSON (Task 25) ------------------------------------------


def point_home_at(monkeypatch, home):
    """Local helper: ``~`` expands to ``home`` on POSIX (HOME) and on Windows (USERPROFILE)."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def test_tilde_in_unit_is_expanded(tmp_cfg, tmp_path, monkeypatch, capsys):
    from conftest import fx
    from tutor_any_lecture.unit import UnitPaths

    point_home_at(monkeypatch, tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    argv = ["acquire", "import", "--file", str(fx("transcripts", "cues.vtt")), "--unit", "~/x/u"]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert UnitPaths(tmp_path / "x" / "u").transcript.exists()
    assert not (cwd / "~").exists()


def test_path_arguments_are_absolute(tmp_path, monkeypatch):
    point_home_at(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    args = cli.build_parser().parse_args(["acquire", "route", "--folder", "rel/f", "--unit", "~/u"])
    assert Path(args.folder) == tmp_path / "rel" / "f" and Path(args.folder).is_absolute()
    assert Path(args.unit) == tmp_path / "u"


def test_profile_show_prints_an_absolute_workspace(tmp_cfg, tmp_path, monkeypatch, capsys):
    from tutor_any_lecture.config import config_dir

    point_home_at(monkeypatch, tmp_path)
    assert main(["profile", "set", "workspace", "~/ws"]) == 0
    capsys.readouterr()
    assert main(["profile", "show"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["workspace"] == str(tmp_path / "ws") and Path(shown["workspace"]).is_absolute()
    assert "workspace: ~/ws" in (config_dir() / "profile.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("platform, escaped", [("win32", True), ("linux", False), ("darwin", False)])
def test_stdout_json_is_ascii_only_on_windows(tmp_path, monkeypatch, capsys, platform, escaped):
    folder = tmp_path / "课程 资料"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"")
    monkeypatch.setattr(sys, "platform", platform)
    assert main(["acquire", "route", "--folder", str(folder), "--unit", str(tmp_path / "unit")]) == 0
    out = capsys.readouterr().out
    assert out.isascii() is escaped and len(out.splitlines()) == 1
    assert ("课程 资料" in out) is not escaped
    plan = json.loads(out)
    assert "课程 资料" in plan["steps"][0]["argv"][3]
    assert plan["files"]["slides"] == [str(folder.resolve() / "a.pdf")]


def test_stdout_json_keeps_line_separators_escaped(monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "linux")
    cli._print_json({"text": "a\u2028b\u2029c\x85d 第"})
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and len(out.splitlines()) == 1 and "第" in out
    assert json.loads(out) == {"text": "a\u2028b\u2029c\x85d 第"}


# ---- one way to report a written file (Task 29, L12) --------------------------


def ok_unit(tmp_path):
    """Local helper: a copy of the ok fixture unit."""
    from conftest import fx

    unit = tmp_path / "课程 资料" / "第1周"
    shutil.copytree(fx("units", "ok"), unit)
    return unit


def setup_cards_export(tmp_path):
    return ["cards", "export", "--unit", str(ok_unit(tmp_path))]


def setup_cards_add_misses(tmp_path):
    return ["cards", "add-misses", "--unit", str(ok_unit(tmp_path)), "--workspace", str(tmp_path / "ws")]


def setup_map_mermaid(tmp_path):
    return ["map", "mermaid", "--unit", str(ok_unit(tmp_path))]


def setup_items_assign(tmp_path):
    return ["items", "assign", "--unit", str(ok_unit(tmp_path)), "--force"]


def setup_slides_pdf(tmp_path):
    from fixtures.make_pdf import make_pdf

    pdf = make_pdf(tmp_path, ["Compound interest\n1/2", "Discounting\n2/2"])
    return ["slides", "--pdf", str(pdf), "--unit", str(tmp_path / "unit")]


def setup_slides_suspects(tmp_path):
    return ["slides", "suspects", "--unit", str(ok_unit(tmp_path))]


def setup_progress_render(tmp_path):
    from tutor_any_lecture.progress import Attempt, log_attempt

    ws = tmp_path / "ws"
    log_attempt(Attempt(ts="2026-11-20T10:00:00+00:00", course="C", unit="u1", item_id="c1-A", variant="A",
                        concept="c1", phase="pre", score=0, confidence=2, citation="(0:30)", exposure="none"), ws)
    return ["progress", "render", "--course", "C", "--workspace", str(ws)]


def setup_cite_link(tmp_path):
    return ["cite", "link", "--unit", str(ok_unit(tmp_path))]


WRITERS = {
    "cards-export": setup_cards_export,
    "cite-link": setup_cite_link,
    "cards-add-misses": setup_cards_add_misses,
    "map-mermaid": setup_map_mermaid,
    "items-assign": setup_items_assign,
    "slides-pdf": setup_slides_pdf,
    "slides-suspects": setup_slides_suspects,
    "progress-render": setup_progress_render,
}


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_commands_that_write_report_json_paths(tmp_path, capsys, name):
    argv = WRITERS[name](tmp_path)
    capsys.readouterr()
    assert main(argv) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    out = json.loads(lines[0])
    assert isinstance(out, dict) and ("path" in out) != ("paths" in out)
    paths = [out["path"]] if "path" in out else out["paths"]
    assert paths and all(Path(p).is_absolute() and Path(p).is_file() for p in paths)


@pytest.mark.parametrize("command", [
    ["acquire", "url", "--url", "https://video.example.com/v/1"],
    ["acquire", "local", "--file", "lecture.mp4"],
    ["transcribe", "--audio", "lecture.wav"],
], ids=["url", "local", "transcribe"])
def test_acquire_with_malformed_profile_is_error_json(tmp_cfg, tmp_path, monkeypatch, capsys, command):
    import yt_dlp

    from tutor_any_lecture.config import config_dir

    def no_network(*args, **kwargs):
        raise AssertionError("the profile is read before yt-dlp is touched")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", no_network)
    path = config_dir() / "profile.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- not\n- a mapping\n", encoding="utf-8", newline="\n")
    (tmp_path / "lecture.mp4").write_bytes(b"")
    (tmp_path / "lecture.wav").write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    assert main([*command, "--unit", str(tmp_path / "unit")]) == 1
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    out = json.loads(lines[0])
    assert out["status"] == "error" and "profile.yaml" in out["message"]
    assert captured.err == ""
    assert not (tmp_path / "unit").exists()


# ---- the tool writes the time links (Task 29, L10) -----------------------------


def test_cli_cite_link(tmp_path, capsys):
    from tutor_any_lecture.unit import UnitPaths

    unit = ok_unit(tmp_path)
    paths = UnitPaths(unit)
    source = json.loads(paths.source.read_text(encoding="utf-8"))
    source.update(kind="url", url="https://video.example.com/watch?v=x")
    paths.source.write_text(json.dumps(source) + "\n", encoding="utf-8", newline="\n")
    assert main(["cite", "link", "--unit", str(unit)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(paths.explanation), "linked": 3}
    note = paths.explanation.read_text(encoding="utf-8")
    assert "(slide 1, [0:42](https://video.example.com/watch?v=x&t=42s))" in note
    assert "(slide 2, [2:40](https://video.example.com/watch?v=x&t=160s))" in note
    assert main(["cite", "link", "--unit", str(unit)]) == 0
    assert json.loads(capsys.readouterr().out)["linked"] == 0
    assert main(["verify", "--unit", str(unit)]) == 0
    # a unit without explanation.md is a missing file: exit 1, one line on stderr
    paths.explanation.unlink()
    capsys.readouterr()
    assert main(["cite", "link", "--unit", str(unit)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.count("\n") == 1
