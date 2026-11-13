import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from tutor_any_lecture import __version__
from tutor_any_lecture.config import config_dir

ROOT = Path(__file__).resolve().parents[1]
CANON = Path("skills/tutor-any-lecture/scripts")
SH_FILES = [Path("install.sh"), CANON / "install.sh"]
PS1_FILES = [Path("install.ps1"), CANON / "install.ps1"]
GIT_SOURCE = "git+https://github.com/hypersupersheep/tutor-any-lecture"
PS = shutil.which("pwsh") or shutil.which("powershell")

needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="bash")
needs_ps = pytest.mark.skipif(PS is None, reason="needs pwsh or powershell")


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
    # PowerShell would otherwise write a telemetry id into the home folder it is given.
    env["POWERSHELL_TELEMETRY_OPTOUT"] = "1"
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


# ---- shared helpers for the flag and stop tests ------------------------------


def run_rc(argv, env, cwd=ROOT):
    """Run an installer with no terminal attached; return the CompletedProcess."""
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def sh(*args):
    return ["bash", str(ROOT / "install.sh"), *args]


def ps(*args, script=None):
    script = script or (ROOT / "install.ps1")
    policy = ["-ExecutionPolicy", "Bypass"] if sys.platform == "win32" else []
    return [PS, "-NoProfile", *policy, "-File", str(script), *args]


def snapshot(folder):
    return sorted(str(p) for p in folder.rglob("*"))


def is_shell_file(path, folder):
    """A path PowerShell writes for itself into the home folder it is given:
    .cache/powershell, .local/share/powershell, AppData/Local/Microsoft/PowerShell."""
    parts = Path(path).relative_to(folder).parts
    return any("powershell" in part.lower() or part == "Microsoft" for part in parts)


def new_paths(folder, before):
    """Paths under ``folder`` that are not in the snapshot ``before``, leaving out the
    shell's own files and every new directory that exists only as their parent."""
    new = [Path(p) for p in snapshot(folder) if p not in set(before)]
    shell = {p for p in new if is_shell_file(p, folder)}
    holders = {a for p in shell for a in p.parents if a in new}

    def holds_only_shell_files(d):
        return all(q in shell or q in holders for q in new if d in q.parents)

    left_out = shell | {d for d in holders if holds_only_shell_files(d)}
    return [str(p) for p in new if p not in left_out]


def tool_dir(tmp_path, *names):
    """A folder holding links to just the named tools, to stand in for PATH."""
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    for name in names:
        real = shutil.which(name)
        assert real, name
        (bin_dir / name).symlink_to(real)
    return bin_dir


def copied_skill(tmp_path):
    """A copy of the skill folder with no pyproject.toml above it."""
    dest = tmp_path / "copy" / "skills" / "tutor-any-lecture"
    shutil.copytree(ROOT / "skills" / "tutor-any-lecture", dest)
    return dest


def test_version_file_matches_the_package():
    version = ROOT / "skills" / "tutor-any-lecture" / "VERSION"
    assert version.read_text(encoding="utf-8") == __version__ + "\n"


def test_ps1_files_are_ascii_for_windows_powershell():
    # Windows PowerShell 5.1 reads a script without a BOM in the ANSI code page.
    for path in PS1_FILES:
        assert (ROOT / path).read_bytes().isascii(), path


# A ternary, `$a ? $b : $c`, outside string literals: a lone ? and later a lone :.
PS_TERNARY = re.compile(r"(?<=\s)\?(?=\s)[^\n]*?\s:(?=\s)")
PS_STRING = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")


def test_ps1_avoids_powershell_7_only_operators():
    # The ternary pattern finds what it is meant to find, and leaves strings alone.
    assert PS_TERNARY.search("$x = $ok ? 'yes' : 'no'")
    assert not PS_TERNARY.search(PS_STRING.sub("''", "Write-Host 'Proceed ? [y/N] : '"))
    for path in PS1_FILES:
        code = "\n".join(
            line.split("#", 1)[0] for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        )
        for token in ("??", "&&", "||", "?."):
            assert token not in code, (path, token)
        bare = PS_STRING.sub("''", code)
        assert not PS_TERNARY.search(bare), (path, "ternary")


def test_ps1_declares_the_new_flags():
    for path in PS1_FILES:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "[switch]$WithAsr" in text and "[switch]$CliOnly" in text, path
    canonical = (ROOT / CANON / "install.ps1").read_text(encoding="utf-8")
    assert "#   -WithAsr" in canonical and "#   -CliOnly" in canonical

# ---- install.sh ---------------------------------------------------------------


@needs_bash
def test_sh_unknown_flag_exits_2(tmp_path):
    assert run_rc(sh("--bogus", "--dry-run"), home(tmp_path)).returncode == 2


@needs_bash
def test_sh_unknown_agent_exits_2(tmp_path):
    assert run_rc(sh("--agents", "robot", "--dry-run"), home(tmp_path)).returncode == 2


@needs_bash
def test_sh_cli_only_with_agents_exits_2(tmp_path):
    proc = run_rc(sh("--cli-only", "--agents", "claude", "--dry-run"), home(tmp_path))
    assert proc.returncode == 2
    assert "--cli-only" in proc.stderr


@needs_bash
def test_sh_agent_names_ignore_case(tmp_path):
    proc = run_rc(sh("--agents", "Claude", "--dry-run"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert str(tmp_path / ".claude" / "skills" / "tutor-any-lecture") in proc.stdout


@needs_bash
def test_sh_dry_run_creates_nothing(tmp_path):
    env = home(tmp_path)
    before = snapshot(tmp_path)
    proc = run_rc(sh("--dry-run", "--with-asr", "--agents", "claude,codex,agents"), env)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(tmp_path) == before == []


@needs_bash
def test_sh_help_names_the_new_flags(tmp_path):
    proc = run_rc(sh("--help"), home(tmp_path))
    assert proc.returncode == 0
    assert "--with-asr" in proc.stdout and "--cli-only" in proc.stdout


@needs_bash
def test_sh_with_asr_names_the_extra(tmp_path):
    proc = run_rc(sh("--dry-run", "--with-asr"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "tutor-any-lecture[asr] @ " in proc.stdout
    assert "tutor-any-lecture[asr] @ " + "file://" + quote(str(ROOT.resolve())) in proc.stdout
    assert "PLAN: --with-asr on" in proc.stdout


@needs_bash
def test_sh_without_asr_installs_the_plain_package(tmp_path):
    proc = run_rc(sh("--dry-run"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "[asr]" not in proc.stdout
    assert "PLAN: --with-asr off" in proc.stdout and "PLAN: --cli-only off" in proc.stdout


@needs_bash
def test_sh_with_asr_file_url_for_a_folder_with_space_and_cjk(tmp_path):
    source = tmp_path / "课程 资料" / "第1周"
    source.mkdir(parents=True)
    proc = run_rc(sh("--dry-run", "--with-asr", "--from", str(source)), home(tmp_path / "h"))
    assert proc.returncode == 0, proc.stderr
    url = "file://" + quote(str(source.resolve()))
    assert "%20" in url and "tutor-any-lecture[asr] @ " + url in proc.stdout


@needs_bash
def test_sh_cli_only_copies_no_skill(tmp_path):
    (tmp_path / ".claude").mkdir()
    proc = run_rc(sh("--dry-run", "--cli-only"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "PLAN: copy" not in proc.stdout
    assert str(tmp_path / ".claude") not in proc.stdout
    assert "PLAN: write " in proc.stdout
    assert "PLAN: --cli-only on" in proc.stdout


@needs_bash
def test_sh_refuses_git_bash(tmp_path):
    fake = tmp_path / "fake"
    fake.mkdir()
    uname = fake / "uname"
    uname.write_text("#!/bin/sh\necho MINGW64_NT-10.0\n", encoding="utf-8", newline="\n")
    uname.chmod(0o755)
    env = home(tmp_path)
    env["PATH"] = str(fake) + os.pathsep + env["PATH"]
    proc = run_rc(sh("--dry-run", "--with-asr", "--agents", "claude"), env)
    assert proc.returncode == 3
    lines = [ln for ln in proc.stderr.splitlines() if "powershell" in ln]
    assert any("powershell -NoProfile -ExecutionPolicy Bypass -File" in ln for ln in lines)
    command = next(ln for ln in lines if ln.startswith("powershell "))
    assert "install.ps1" in command
    assert "-DryRun" in command and "-WithAsr" in command and '-Agents "claude"' in command


@needs_bash
def test_sh_missing_git_for_git_source_exits_3(tmp_path):
    script = tmp_path / "install.sh"
    shutil.copy(ROOT / CANON / "install.sh", script)
    env = home(tmp_path)
    # only what the script runs before the git check; no git
    env["PATH"] = str(tool_dir(tmp_path, "uname", "dirname"))
    proc = run_rc([shutil.which("bash"), str(script), "--dry-run"], env)
    assert proc.returncode == 3
    assert "needs git" in proc.stderr and "--from" in proc.stderr
    assert len(proc.stderr.strip().splitlines()) == 1


@needs_bash
@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_sh_git_fallback_installs_the_version_tag(tmp_path):
    skill = copied_skill(tmp_path)
    proc = run_rc(
        ["bash", str(skill / "scripts" / "install.sh"), "--dry-run", "--with-asr"],
        home(tmp_path / "h"),
    )
    assert proc.returncode == 0, proc.stderr
    assert f"tutor-any-lecture[asr] @ {GIT_SOURCE}@v{__version__}" in proc.stdout


# ---- install.ps1 --------------------------------------------------------------


@needs_ps
def test_ps1_unknown_flag_exits_2(tmp_path):
    assert run_rc(ps("-Bogus", "-DryRun"), home(tmp_path)).returncode == 2


@needs_ps
def test_ps1_unknown_agent_exits_2(tmp_path):
    assert run_rc(ps("-Agents", "robot", "-DryRun"), home(tmp_path)).returncode == 2


@needs_ps
def test_ps1_cli_only_with_agents_exits_2(tmp_path):
    proc = run_rc(ps("-CliOnly", "-Agents", "claude", "-DryRun"), home(tmp_path))
    assert proc.returncode == 2


@needs_ps
def test_ps1_agent_names_ignore_case(tmp_path):
    proc = run_rc(ps("-Agents", "Claude", "-DryRun"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "PLAN: copy " in proc.stdout


@needs_ps
def test_ps1_dry_run_creates_nothing(tmp_path):
    env = home(tmp_path)
    before = snapshot(tmp_path)
    proc = run_rc(ps("-DryRun", "-WithAsr", "-Agents", "claude,codex,agents"), env)
    assert proc.returncode == 0, proc.stderr
    assert new_paths(tmp_path, before) == []


def test_new_paths_leaves_out_only_the_shell_files(tmp_path):
    """The dry-run check ignores PowerShell's start-up files and nothing else."""
    (tmp_path / "AppData" / "Local").mkdir(parents=True)
    before = snapshot(tmp_path)
    shell_files = [
        tmp_path / ".cache" / "powershell" / "StartupProfileData-NonInteractive",
        tmp_path / ".local" / "share" / "powershell" / "Modules",
        tmp_path / "AppData" / "Local" / "Microsoft" / "PowerShell" / "StartupProfileData-NonInteractive",
    ]
    for f in shell_files:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("", encoding="utf-8", newline="\n")
    assert new_paths(tmp_path, before) == []
    # A file of the installer's own is still caught, with the new folders that hold it,
    # even inside a folder the shell also wrote to.
    own = tmp_path / ".local" / "share" / "tutor-any-lecture" / "cli-path"
    own.parent.mkdir(parents=True)
    own.write_text("x", encoding="utf-8", newline="\n")
    empty = tmp_path / ".claude"
    empty.mkdir()
    assert new_paths(tmp_path, before) == [
        str(empty),
        str(tmp_path / ".local"),
        str(tmp_path / ".local" / "share"),
        str(own.parent),
        str(own),
    ]


@needs_ps
def test_ps1_with_asr_names_the_extra(tmp_path):
    proc = run_rc(ps("-DryRun", "-WithAsr"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "tutor-any-lecture[asr] @ file:///" in proc.stdout
    assert "PLAN: -WithAsr on" in proc.stdout


@needs_ps
def test_ps1_cli_only_copies_no_skill(tmp_path):
    (tmp_path / ".claude").mkdir()
    proc = run_rc(ps("-DryRun", "-CliOnly"), home(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "PLAN: copy" not in proc.stdout
    assert "PLAN: write " in proc.stdout
    assert "PLAN: -CliOnly on" in proc.stdout


@needs_ps
def test_ps1_missing_git_for_git_source_exits_3(tmp_path):
    script = tmp_path / "install.ps1"
    shutil.copy(ROOT / CANON / "install.ps1", script)
    env = home(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    env["PATH"] = str(empty)
    proc = run_rc(ps("-DryRun", script=script), env)
    assert proc.returncode == 3
    assert "needs git" in proc.stderr and "-From" in proc.stderr


@needs_ps
@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_ps1_git_fallback_installs_the_version_tag(tmp_path):
    skill = copied_skill(tmp_path)
    proc = run_rc(
        ps("-DryRun", "-WithAsr", script=skill / "scripts" / "install.ps1"),
        home(tmp_path / "h"),
    )
    assert proc.returncode == 0, proc.stderr
    assert f"tutor-any-lecture[asr] @ {GIT_SOURCE}@v{__version__}" in proc.stdout


# ---- packaging ------------------------------------------------------------------


def test_sdist_includes_only_public_files():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"^\[tool\.hatch\.build\.targets\.sdist\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    assert section, "no sdist target"
    include = re.search(r"^include\s*=\s*\[(.*?)\]", section.group(1), re.M | re.S)
    assert include, "no include list"
    entries = re.findall(r'"([^"]*)"', include.group(1))
    # Each entry is anchored at the repository root, so none matches at any depth.
    assert entries == [
        "/src",
        "/README.md",
        "/README.zh-CN.md",
        "/LICENSE",
        "/THIRD_PARTY_NOTICES.md",
        "/pyproject.toml",
    ]


def ci_steps():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_ci_runs_the_installer_under_windows_powershell_5_1():
    runs = [s["run"] for s in ci_steps() if s.get("shell") == "powershell"]
    base = "powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1"
    assert any(base + " -DryRun" in r for r in runs)
    assert any(base + " -Yes -From . -Agents claude" in r for r in runs)
    assert any("cli-path" in r and "selftest" in r for r in runs)
    # The 5.1 install must write cli-path itself: the earlier pwsh install's file is removed first.
    real = [r for r in runs if base + " -Yes -From . -Agents claude" in r]
    assert len(real) == 1
    removal = real[0].find("Remove-Item")
    assert removal != -1 and "cli-path" in real[0][removal:real[0].find(base)]
    assert removal < real[0].find(base)


def test_ci_installs_from_a_folder_with_space_and_cjk_on_every_os():
    runs = [s.get("run", "") for s in ci_steps()]
    odd = [r for r in runs if "课程 资料" in r and "selftest" in r]
    assert any("install.sh" in r for r in odd) and any("install.ps1" in r for r in odd)


def test_ci_never_installs_asr_and_doctor_must_be_ready():
    runs = [s.get("run", "") for s in ci_steps()]
    assert not any("asr" in r.lower() for r in runs)
    doctor = [r for r in runs if "doctor" in r]
    assert doctor
    assert not any("-eq 3" in r for r in doctor)
