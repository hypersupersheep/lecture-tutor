import argparse
import json
import re
import signal
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
    assert all(g in out for g in ["doctor", "acquire", "verify", "progress", "cards", "items", "map", "selftest"])


def test_parser_registers_eleven_groups():
    assert top_level_commands() == {
        "profile", "doctor", "acquire", "transcribe", "slides", "items",
        "cards", "progress", "map", "verify", "selftest",
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


def test_stdout_json_is_ascii(tmp_path, capsys):
    folder = tmp_path / "课程 资料"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"")
    assert main(["acquire", "route", "--folder", str(folder), "--unit", str(tmp_path / "unit")]) == 0
    out = capsys.readouterr().out
    assert out.isascii() and len(out.splitlines()) == 1
    plan = json.loads(out)
    assert "课程 资料" in plan["steps"][0]["argv"][3]
    assert plan["files"]["slides"] == [str(folder.resolve() / "a.pdf")]
