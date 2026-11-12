import argparse
import json

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
