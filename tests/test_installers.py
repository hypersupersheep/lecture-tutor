import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tutor_any_lecture.config import config_dir

CANON = Path("skills/tutor-any-lecture/scripts")
SH_FILES = [Path("install.sh"), CANON / "install.sh"]
PS1_FILES = [Path("install.ps1"), CANON / "install.ps1"]


def home(tmp_path):
    """Environment for an installer subprocess: every home-like folder points into
    tmp_path, and the interpreter running pytest comes first on PATH."""
    env = dict(os.environ)
    for key in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
        env[key] = str(tmp_path)
    if sys.platform == "win32":
        for key, sub in (("APPDATA", "Roaming"), ("LOCALAPPDATA", "Local")):
            folder = tmp_path / "AppData" / sub
            folder.mkdir(parents=True, exist_ok=True)
            env[key] = str(folder)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def run(argv, env):
    """Run an installer with no terminal attached; return its stdout as text."""
    proc = subprocess.run(
        argv,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_sh_dry_run_plans_without_changes(tmp_path):
    out = run(["bash", "install.sh", "--dry-run", "--agents", "claude"], env=home(tmp_path))
    assert "PLAN: uv tool install" in out or "PLAN: python -m venv" in out
    assert not (tmp_path / ".claude").exists()


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("pwsh") is None, reason="pwsh on Windows"
)
def test_ps1_dry_run(tmp_path):
    out = run(["pwsh", "-File", "install.ps1", "-DryRun"], env=home(tmp_path))
    assert "PLAN:" in out


def test_no_curl_pipe():
    for path in SH_FILES:
        assert "| sh" not in path.read_text(encoding="utf-8")
    for path in PS1_FILES:
        assert "iex" not in path.read_text(encoding="utf-8").lower()


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_wrapper_matches_canonical_dry_run(tmp_path):
    env = home(tmp_path)
    args = ["--dry-run", "--agents", "claude"]
    wrapper = run(["bash", "install.sh", *args], env=env)
    canonical = run(["bash", str(CANON / "install.sh"), *args], env=env)
    assert wrapper == canonical
    assert "PLAN:" in wrapper


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
@pytest.mark.parametrize("xdg_set", [True, False], ids=["xdg-set", "xdg-unset"])
def test_sh_cli_path_matches_config_dir(tmp_path, monkeypatch, xdg_set):
    env = home(tmp_path)
    if not xdg_set:
        del env["XDG_CONFIG_HOME"]
    for key in ("HOME", "XDG_CONFIG_HOME"):
        if key in env:
            monkeypatch.setenv(key, env[key])
        else:
            monkeypatch.delenv(key, raising=False)
    out = run(["bash", "install.sh", "--dry-run", "--agents", "claude"], env=env)
    assert "PLAN: write " + str(config_dir() / "cli-path") in out


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("pwsh") is None, reason="pwsh on Windows"
)
def test_ps1_cli_path_matches_config_dir(tmp_path, monkeypatch):
    env = home(tmp_path)
    monkeypatch.setenv("APPDATA", env["APPDATA"])
    out = run(["pwsh", "-File", "install.ps1", "-DryRun"], env=env)
    assert "PLAN: write " + str(config_dir() / "cli-path") in out
