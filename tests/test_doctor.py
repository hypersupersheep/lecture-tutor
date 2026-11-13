import dataclasses
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from tutor_any_lecture import __version__, asr, doctor
from tutor_any_lecture.cli import main
from tutor_any_lecture.config import config_dir
from tutor_any_lecture.doctor import run_doctor

REQUIRED = ["python", "ffmpeg", "yt_dlp", "config_dir"]
OPTIONAL = ["js_runtime", "browser", "asr_backend", "asr_model"]
ASR_FIX = ("Optional: needed only for audio or video without captions. "
           "Run the installer again with --with-asr (Windows: -WithAsr).")


def patch_checks(monkeypatch, required, optional=True):
    """Replace doctor.CHECKS: required checks return (required, "patched"), optional ones (optional, "patched")."""

    def fake(ok):
        return lambda: (ok, "patched")

    monkeypatch.setattr(
        doctor,
        "CHECKS",
        [dataclasses.replace(c, fn=fake(required if c.required else optional)) for c in doctor.CHECKS],
    )


# --- the three tests of the plan ---


def test_ready_when_required_ok(monkeypatch):
    patch_checks(monkeypatch, required=True, optional=False)
    assert run_doctor()["ready"] is True


def test_not_ready_exit_code(monkeypatch):
    patch_checks(monkeypatch, required=False)
    assert main(["doctor", "--json"]) == 3


def test_json_shape(monkeypatch, capsys):
    patch_checks(monkeypatch, required=True)
    main(["doctor", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert {"ready", "checks", "version"} <= d.keys()


# --- the check list and the report ---


def test_check_names_and_required():
    assert [(c.name, c.required) for c in doctor.CHECKS] == (
        [(n, True) for n in REQUIRED] + [(n, False) for n in OPTIONAL]
    )
    assert all(c.fix for c in doctor.CHECKS)
    assert all(c.fix.startswith("Optional: ") == (not c.required) for c in doctor.CHECKS)


def test_report_entries(monkeypatch):
    patch_checks(monkeypatch, required=True, optional=False)
    d = run_doctor()
    assert list(d) == ["ready", "checks", "version"]
    assert d["version"] == __version__
    assert [c["name"] for c in d["checks"]] == REQUIRED + OPTIONAL
    assert all(set(c) == {"name", "ok", "detail", "fix"} for c in d["checks"])
    by_name = {c["name"]: c for c in d["checks"]}
    assert by_name["python"] == {"name": "python", "ok": True, "detail": "patched", "fix": ""}
    assert by_name["browser"]["ok"] is False
    assert by_name["browser"]["fix"].startswith("Optional: ")


def test_raising_check_is_not_ok(monkeypatch):
    def boom():
        raise RuntimeError("no backend")

    monkeypatch.setattr(doctor, "CHECKS", [doctor.Check("asr_backend", True, boom, "install one")])
    d = run_doctor()
    assert d["ready"] is False
    assert d["checks"] == [
        {"name": "asr_backend", "ok": False, "detail": "RuntimeError: no backend", "fix": "install one"}
    ]


# --- the CLI ---


def test_json_one_line_and_exit_0(monkeypatch, capsys):
    patch_checks(monkeypatch, required=True)
    assert main(["doctor", "--json"]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and out.count("\n") == 1
    assert json.loads(out)["ready"] is True


def test_text_output(monkeypatch, capsys):
    patch_checks(monkeypatch, required=True, optional=False)
    assert main(["doctor"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 14
    assert lines[0] == f"tutor-any-lecture {__version__}"
    assert "[ok] python: patched" in lines
    i = lines.index("[warn] browser: patched")
    assert lines[i + 1].startswith("  fix: Optional: ")
    assert not any(line.startswith("[FAIL]") for line in lines)
    assert lines[-1] == "ready"

    patch_checks(monkeypatch, required=False)
    assert main(["doctor"]) == 3
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 14
    j = lines.index("[FAIL] python: patched")
    assert lines[j + 1].startswith("  fix: ") and "Optional" not in lines[j + 1]
    assert "[ok] browser: patched" in lines
    assert lines[-1] == "not ready"


# --- the real checks ---


def test_version_of():
    assert doctor._version_of("deno 2.3.1 (stable, release, aarch64-apple-darwin)\nv8 13.5.212.10\n") == (2, 3)
    assert doctor._version_of("v22.11.0\n") == (22, 11)
    assert doctor._version_of("not a version") is None


def test_js_runtime_minimums(monkeypatch):
    def with_versions(found):
        monkeypatch.setattr(doctor, "_tool_version", lambda name: found.get(name))
        return doctor.check_js_runtime()

    assert with_versions({"deno": (2, 3)}) == (True, "deno 2.3")
    assert with_versions({"deno": (2, 2), "node": (22, 0)}) == (True, "node 22.0")
    assert with_versions({"node": (20, 18)}) == (False, "node 20.18 (need deno >= 2.3 or node >= 22)")
    assert with_versions({"deno": (2, 2), "node": (20, 18)}) == (
        False,
        "deno 2.2, node 20.18 (need deno >= 2.3 or node >= 22)",
    )
    assert with_versions({}) == (False, "deno and node not found")


def test_config_dir_check(tmp_cfg):
    assert doctor.check_config_dir() == (True, str(config_dir()))
    assert config_dir() == tmp_cfg / "tutor-any-lecture"
    assert config_dir().is_dir()
    assert list(config_dir().iterdir()) == []


def test_browser_from_chrome_path(monkeypatch, tmp_path):
    exe = tmp_path / "课程 资料" / "chrome"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setenv("CHROME_PATH", str(exe))
    assert doctor.check_browser() == (True, str(exe))

    monkeypatch.setenv("CHROME_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(doctor, "_browser_candidates", lambda: [])
    assert doctor.check_browser() == (False, "not found")


def test_asr_checks(monkeypatch):
    monkeypatch.setattr(asr, "select_backend", lambda: "faster")
    monkeypatch.setattr(asr, "select_model", lambda backend: "small")
    monkeypatch.setattr(doctor, "_model_cached", lambda backend, model: (backend, model) == ("faster", "small"))
    assert doctor.check_asr_backend() == (True, "faster")
    assert doctor.check_asr_model() == (True, "small")

    monkeypatch.setattr(doctor, "_model_cached", lambda backend, model: False)
    assert doctor.check_asr_model() == (False, "small is not cached")

    def missing():
        raise asr.BackendMissing("no ASR backend installed")

    monkeypatch.setattr(asr, "select_backend", missing)
    monkeypatch.setattr(doctor, "CHECKS", [c for c in doctor.CHECKS if c.name in ("asr_backend", "asr_model")])
    d = run_doctor()
    assert d["ready"] is True   # both checks are optional: speech recognition is an extra
    assert [(c["name"], c["ok"]) for c in d["checks"]] == [("asr_backend", False), ("asr_model", False)]
    assert d["checks"][0]["detail"] == "BackendMissing: no ASR backend installed"


def test_real_run_never_raises(tmp_cfg):
    d = run_doctor()
    by_name = {c["name"]: c for c in d["checks"]}
    assert list(by_name) == REQUIRED + OPTIONAL
    assert all(isinstance(c["ok"], bool) and isinstance(c["detail"], str) for c in d["checks"])
    for name in ("python", "ffmpeg", "yt_dlp", "config_dir"):
        assert by_name[name]["ok"] is True, by_name[name]
    assert d["ready"] == all(by_name[n]["ok"] for n in REQUIRED)


def test_broken_backend_import_is_reported_as_broken(monkeypatch):
    real_import = importlib.import_module

    def broken_import(name, *args, **kwargs):
        if name.split(".")[0] == "faster_whisper":
            raise OSError("missing DLL")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(asr, "select_backend", lambda: "faster")
    monkeypatch.setattr(asr, "select_model", lambda backend: "small")
    monkeypatch.setattr(importlib, "import_module", broken_import)
    # The package is installed: find_spec locates it, only importing it fails.
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: object())
    monkeypatch.setattr(doctor, "CHECKS", [c for c in doctor.CHECKS if c.name == "asr_model"])
    check = run_doctor()["checks"][0]
    assert check["ok"] is False
    assert "cannot be imported" in check["detail"] and "missing DLL" in check["detail"]
    assert "not cached" not in check["detail"]
    assert check["detail"] == "faster-whisper is installed but cannot be imported: OSError: missing DLL"
    assert check["fix"] == "Optional: reinstall faster-whisper"


def test_uninstalled_backend_package_keeps_not_cached_wording(monkeypatch):
    def not_installed(name, *args, **kwargs):
        raise ModuleNotFoundError(f"No module named {name!r}")

    monkeypatch.setattr(asr, "select_backend", lambda: "faster")
    monkeypatch.setattr(asr, "select_model", lambda backend: "small")
    monkeypatch.setattr(importlib, "import_module", not_installed)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: None)
    assert doctor.check_asr_model() == (False, "small is not cached")


@pytest.mark.parametrize("plat", ["darwin", "linux", "win32"])
def test_browser_candidates_per_platform(monkeypatch, plat):
    monkeypatch.setattr(sys, "platform", plat)
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        monkeypatch.setenv(var, rf"C:\Synthetic\{var}")
    candidates = doctor._browser_candidates()
    assert candidates

    def command_name(c):
        return "/" not in c and "\\" not in c

    for c in candidates:
        if plat == "darwin":
            assert ".app/" in PurePosixPath(c).as_posix() or command_name(c), c
        elif plat == "linux":
            assert command_name(c), c
        else:
            assert PureWindowsPath(c).suffix == ".exe" and not command_name(c), c


def test_tool_version_handles_missing_and_failing_tools(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    assert doctor._tool_version("deno") is None

    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/synthetic/bin/{name}")

    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 10))

    monkeypatch.setattr(doctor.subprocess, "run", timeout)
    assert doctor._tool_version("deno") is None

    def os_error(argv, **kwargs):
        raise OSError("exec format error")

    monkeypatch.setattr(doctor.subprocess, "run", os_error)
    assert doctor._tool_version("deno") is None


def test_model_cached_unknown_backend():
    assert doctor._model_cached("no-such-backend", "small") is False


def test_browser_found_by_command_name(monkeypatch):
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(doctor, "_browser_candidates", lambda: ["synthetic-browser"])
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/synthetic/bin/" + name if name == "synthetic-browser" else None)
    assert doctor.check_browser() == (True, "/synthetic/bin/synthetic-browser")


def test_ready_without_asr(monkeypatch, tmp_cfg):
    # No backend importable: find_spec finds neither mlx_whisper nor faster_whisper.
    monkeypatch.setattr(asr, "_installed", lambda module: False)
    d = run_doctor()
    by_name = {c["name"]: c for c in d["checks"]}
    assert d["ready"] is True
    assert main(["doctor", "--json"]) == 0
    for name in ("asr_backend", "asr_model"):
        assert by_name[name]["ok"] is False
        assert by_name[name]["fix"] == ASR_FIX
    assert "--with-asr" in by_name["asr_backend"]["detail"]
