import ast
import subprocess
import sys
from pathlib import Path

from tools.pre_push_leakscan import main as leak_main, scan

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "pre_push_leakscan.py"


def write_denylist(cfg, *lines):
    """Write a denylist under <cfg>/tutor-any-lecture/, one entry per line."""
    d = cfg / "tutor-any-lecture"
    d.mkdir(parents=True, exist_ok=True)
    (d / "denylist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def git(cwd, *args):
    """Run git in cwd with a fixed identity and no signing; return the CompletedProcess."""
    cmd = [
        "git",
        "-c", "user.name=Test",
        "-c", "user.email=test@example.invalid",
        "-c", "commit.gpgsign=false",
        *args,
    ]
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def test_scan_matches_case_insensitive():
    assert scan("see secretword notes", ["SecretWord", "# comment", ""]) == ["SecretWord"]


def test_missing_denylist_is_warning_not_block(tmp_cfg):
    assert leak_main([]) == 0


def test_unpushed_commit_with_term_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = tmp_cfg / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_cfg))
    git(repo, "init", "-q")
    (repo / "notes.txt").write_text("see secretword notes\n", encoding="utf-8", newline="\n")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "--no-verify", "-m", "init")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_staged_term_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = tmp_cfg / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_cfg))
    git(repo, "init", "-q")
    (repo / "clean.txt").write_text("hello\n", encoding="utf-8", newline="\n")
    git(repo, "add", "clean.txt")
    git(repo, "commit", "-q", "--no-verify", "-m", "init")
    (repo / "staged.txt").write_text("see secretword notes\n", encoding="utf-8", newline="\n")
    # staged, not committed: only `git diff --cached` can see it
    git(repo, "add", "staged.txt")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_origin_range_ignores_pushed_commit_and_catches_unpushed(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_cfg))
    upstream = tmp_cfg / "upstream.git"
    upstream.mkdir()
    git(upstream, "init", "-q", "--bare")
    repo = tmp_cfg / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "remote", "add", "origin", str(upstream))
    (repo / "old.txt").write_text("see secretword notes\n", encoding="utf-8", newline="\n")
    git(repo, "add", "old.txt")
    git(repo, "commit", "-q", "--no-verify", "-m", "pushed")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.decode("utf-8").strip()
    # also creates refs/remotes/origin/<branch>
    git(repo, "push", "-q", "origin", branch)
    monkeypatch.chdir(repo)
    # the term is only in a pushed commit: range origin/<branch>..HEAD is empty, so 0
    assert leak_main([]) == 0
    (repo / "new.txt").write_text("see secretword notes\n", encoding="utf-8", newline="\n")
    git(repo, "add", "new.txt")
    git(repo, "commit", "-q", "--no-verify", "-m", "unpushed")
    # the same term in an unpushed commit: caught by the origin/<branch>..HEAD range, so 1
    assert leak_main([]) == 1


def test_clean_repo_passes(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = tmp_cfg / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_cfg))
    git(repo, "init", "-q")
    (repo / "notes.txt").write_text("hello\n", encoding="utf-8", newline="\n")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-q", "--no-verify", "-m", "init")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 0


def test_git_failure_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    nogit = tmp_cfg / "nogit"
    nogit.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_cfg))
    monkeypatch.chdir(nogit)
    assert leak_main([]) == 1


def test_leakscan_is_stdlib_only_py39():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 9))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert "__future__" in roots
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}
