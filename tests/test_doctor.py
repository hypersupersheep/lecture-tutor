import dataclasses
import json

from tutor_any_lecture import __version__, asr, doctor
from tutor_any_lecture.cli import main
from tutor_any_lecture.config import config_dir
from tutor_any_lecture.doctor import run_doctor

REQUIRED = ["python", "ffmpeg", "asr_backend", "yt_dlp", "config_dir"]
OPTIONAL = ["js_runtime", "browser", "asr_model"]


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
    assert len(lines) == 13
    assert lines[0] == f"tutor-any-lecture {__version__}"
    assert "[ok] python: patched" in lines
    i = lines.index("[warn] browser: patched")
    assert lines[i + 1].startswith("  fix: Optional: ")
    assert not any(line.startswith("[FAIL]") for line in lines)
    assert lines[-1] == "ready"

    patch_checks(monkeypatch, required=False)
    assert main(["doctor"]) == 3
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 15
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
    assert d["ready"] is False
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
