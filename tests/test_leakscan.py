import ast
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.pre_push_leakscan import main as leak_main, scan

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "pre_push_leakscan.py"
ZERO = "0" * 40


@pytest.fixture(autouse=True)
def no_stdin(monkeypatch):
    """By default the scan runs as if by hand: nothing on stdin."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))


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
        "-c", "init.defaultBranch=main",
        *args,
    ]
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def sha(repo, rev="HEAD"):
    return git(repo, "rev-parse", rev).stdout.decode("utf-8").strip()


def commit_file(repo, name, text, message):
    """Write one text file, stage it and commit it; return the new commit's sha."""
    (repo / name).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", name)
    git(repo, "commit", "-q", "--no-verify", "-m", message)
    return sha(repo)


def new_repo(tmp_cfg, monkeypatch, name="repo"):
    repo = tmp_cfg / name
    repo.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_cfg))
    git(repo, "init", "-q")
    return repo


def run_hook(repo, cfg, stdin_text, remote="origin"):
    """Run the script as git runs a pre-push hook: in the repo, ref lines on stdin."""
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(cfg)
    env["APPDATA"] = str(cfg)
    env["GIT_CEILING_DIRECTORIES"] = str(cfg)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), remote, "https://example.invalid/repo.git"],
        cwd=repo,
        env=env,
        input=stdin_text.encode("utf-8"),
        capture_output=True,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def test_scan_matches_case_insensitive():
    assert scan("see secretword notes", ["SecretWord", "# comment", ""]) == ["SecretWord"]


def test_missing_denylist_blocks(tmp_cfg, capsys):
    assert leak_main([]) == 1
    err = capsys.readouterr().err
    assert "denylist.txt" in err
    assert len(err.strip().splitlines()) == 1


def test_empty_denylist_blocks(tmp_cfg, capsys):
    write_denylist(tmp_cfg, "# only a comment", "", "   ")
    assert leak_main([]) == 1
    assert "denylist.txt" in capsys.readouterr().err


def test_unreadable_denylist_blocks(tmp_cfg, capsys):
    d = tmp_cfg / "tutor-any-lecture"
    d.mkdir(parents=True)
    (d / "denylist.txt").write_bytes(b"\xff\xfeSecret\x80Word\n")
    assert leak_main([]) == 1
    assert "denylist.txt" in capsys.readouterr().err


def test_denylist_bom_is_ignored(tmp_cfg, monkeypatch):
    d = tmp_cfg / "tutor-any-lecture"
    d.mkdir(parents=True)
    (d / "denylist.txt").write_bytes(b"\xef\xbb\xbfSecretWord\n")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "notes.txt", "see secretword notes\n", "init")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_unpushed_commit_with_term_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "notes.txt", "see secretword notes\n", "init")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_staged_term_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "clean.txt", "hello\n", "init")
    (repo / "staged.txt").write_text("see secretword notes\n", encoding="utf-8", newline="\n")
    # staged, not committed: only `git diff --cached` can see it
    git(repo, "add", "staged.txt")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_origin_range_ignores_pushed_commit_and_catches_unpushed(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    upstream = tmp_cfg / "upstream.git"
    upstream.mkdir()
    git(upstream, "init", "-q", "--bare")
    repo = new_repo(tmp_cfg, monkeypatch)
    git(repo, "remote", "add", "origin", str(upstream))
    commit_file(repo, "old.txt", "see secretword notes\n", "pushed")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.decode("utf-8").strip()
    # also creates refs/remotes/origin/<branch>
    git(repo, "push", "-q", "origin", branch)
    monkeypatch.chdir(repo)
    # the term is only in a pushed commit: range origin/<branch>..HEAD is empty, so 0
    assert leak_main([]) == 0
    commit_file(repo, "new.txt", "see secretword notes\n", "unpushed")
    # the same term in an unpushed commit: caught by the origin/<branch>..HEAD range, so 1
    assert leak_main([]) == 1


def test_stdin_refs_choose_the_scanned_range(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    # c1 holds the term and is taken as already on the remote; c2 is clean
    c1 = commit_file(repo, "old.txt", "see secretword notes\n", "c1")
    c2 = commit_file(repo, "clean.txt", "hello\n", "c2")
    # the term sits on a branch that is not checked out
    git(repo, "checkout", "-q", "-b", "side")
    c3 = commit_file(repo, "side.txt", "see secretword notes\n", "c3")
    git(repo, "checkout", "-q", "main")

    code, err = run_hook(repo, tmp_cfg, f"refs/heads/side {c3} refs/heads/side {c2}\n")
    assert code == 1, err
    assert "SecretWord" in err
    # main's pushed range c1..c2 is clean, although c1 itself holds the term
    code, err = run_hook(repo, tmp_cfg, f"refs/heads/main {c2} refs/heads/main {c1}\n")
    assert code == 0, err


def test_deleted_ref_line_scans_nothing(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    c1 = commit_file(repo, "notes.txt", "see secretword notes\n", "c1")
    code, err = run_hook(repo, tmp_cfg, f"(delete) {ZERO} refs/heads/old {c1}\n")
    assert code == 0, err


def test_malformed_stdin_line_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "notes.txt", "hello\n", "c1")
    code, err = run_hook(repo, tmp_cfg, "refs/heads/main\n")
    assert code == 1
    assert err.strip()


def test_new_branch_scans_commits_not_on_any_remote(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    upstream = tmp_cfg / "upstream.git"
    upstream.mkdir()
    git(upstream, "init", "-q", "--bare")
    repo = new_repo(tmp_cfg, monkeypatch)
    git(repo, "remote", "add", "origin", str(upstream))
    commit_file(repo, "old.txt", "see secretword notes\n", "pushed")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "feature")
    c2 = commit_file(repo, "clean.txt", "hello\n", "clean")
    # a new branch: the term is only in a commit the remote already has
    code, err = run_hook(repo, tmp_cfg, f"refs/heads/feature {c2} refs/heads/feature {ZERO}\n")
    assert code == 0, err
    c3 = commit_file(repo, "new.txt", "see secretword notes\n", "unpushed")
    code, err = run_hook(repo, tmp_cfg, f"refs/heads/feature {c3} refs/heads/feature {ZERO}\n")
    assert code == 1, err


def test_annotated_tag_message_is_scanned(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "clean.txt", "hello\n", "c1")
    git(repo, "tag", "-a", "v1", "-m", "release notes: see secretword")
    tag = sha(repo, "refs/tags/v1")
    code, err = run_hook(repo, tmp_cfg, f"refs/tags/v1 {tag} refs/tags/v1 {ZERO}\n")
    assert code == 1, err
    git(repo, "tag", "-a", "v2", "-m", "release notes")
    tag = sha(repo, "refs/tags/v2")
    code, err = run_hook(repo, tmp_cfg, f"refs/tags/v2 {tag} refs/tags/v2 {ZERO}\n")
    assert code == 0, err


def test_merge_commit_changes_are_scanned(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "a.txt", "hello\n", "c1")
    git(repo, "checkout", "-q", "-b", "side")
    commit_file(repo, "b.txt", "side work\n", "c2")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    # the term enters only in the merge commit itself
    (repo / "merge.txt").write_text("see secretword notes\n", encoding="utf-8", newline="\n")
    git(repo, "add", "merge.txt")
    git(repo, "commit", "-q", "--no-verify", "-m", "merge side")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_binary_file_blocks_unless_allowed(tmp_cfg, monkeypatch, capsys):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "clean.txt", "hello\n", "c1")
    (repo / "assets").mkdir()
    (repo / "assets" / "image data.bin").write_bytes(b"\x00\x01\x02\xff\x00binary")
    git(repo, "add", "assets")
    git(repo, "commit", "-q", "--no-verify", "-m", "c2")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1
    assert "assets/image data.bin" in capsys.readouterr().err
    allow = tmp_cfg / "tutor-any-lecture" / "leakscan-allow.txt"
    allow.write_text("# reviewed binaries\n\nassets/*.bin\n", encoding="utf-8", newline="\n")
    assert leak_main([]) == 0


def test_ascii_terms_match_whole_words():
    assert scan("xabcd", ["ABC"]) == []
    assert scan("abc1", ["ABC"]) == []
    assert scan("the ABC rule", ["ABC"]) == ["ABC"]
    assert scan("abc.example", ["ABC"]) == ["ABC"]
    assert scan("in Secret Word2 form", ["secret word"]) == []
    assert scan("(secret word)", ["secret word"]) == ["secret word"]


def test_non_ascii_terms_match_as_substrings():
    assert scan("这是秘密词汇", ["秘密词"]) == ["秘密词"]
    assert scan("xZÜRICHy", ["zürich"]) == ["zürich"]
    assert scan("xa-by", ["A-B"]) == ["A-B"]


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


# ---- Task 28: prefix terms, fixed log format, target remote, deleted binaries ----


BINARY = b"\x00\x01\x02\xff\x00binary"


def commit_binary(repo, name, message):
    """Write one binary file, stage it and commit it; return the new commit's sha."""
    (repo / name).write_bytes(BINARY)
    git(repo, "add", name)
    git(repo, "commit", "-q", "--no-verify", "-m", message)
    return sha(repo)


def test_star_terms_match_prefixes():
    assert scan("ABC0013", ["ABC0*"]) == ["ABC0*"]
    assert scan("abc0", ["ABC0*"]) == ["ABC0*"]
    assert scan("xabc0013", ["ABC0*"]) == []
    assert scan("see (abc0013) here", ["ABC0*"]) == ["ABC0*"]
    assert scan("x9abc0", ["ABC0*"]) == []
    # a term without a star keeps the whole-word rule
    assert scan("ABC0013", ["ABC0"]) == []


def test_commit_messages_are_scanned_whatever_format_pretty_says(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    git(repo, "config", "format.pretty", "oneline")
    (repo / "clean.txt").write_text("hello\n", encoding="utf-8", newline="\n")
    git(repo, "add", "clean.txt")
    # the term is only in the body of the message, which the oneline format hides
    git(repo, "commit", "-q", "--no-verify", "-m", "clean subject", "-m", "body with secretword")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1


def test_new_branch_range_uses_the_named_remote(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    for name in ("origin", "mirror"):
        bare = tmp_cfg / f"{name}.git"
        bare.mkdir()
        git(bare, "init", "-q", "--bare")
        git(repo, "remote", "add", name, str(bare))
    commit_file(repo, "old.txt", "see secretword notes\n", "only on mirror")
    # the term is on the mirror remote, and not on origin
    git(repo, "push", "-q", "mirror", "main")
    git(repo, "checkout", "-q", "-b", "feature")
    c2 = commit_file(repo, "clean.txt", "hello\n", "clean")
    line = f"refs/heads/feature {c2} refs/heads/feature {ZERO}\n"
    code, err = run_hook(repo, tmp_cfg, line, remote="origin")
    assert code == 1, err
    assert "SecretWord" in err
    code, err = run_hook(repo, tmp_cfg, line, remote="mirror")
    assert code == 0, err


def test_deleting_a_binary_does_not_block(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    c1 = commit_binary(repo, "image.bin", "c1")
    git(repo, "rm", "-q", "image.bin")
    git(repo, "commit", "-q", "--no-verify", "-m", "remove the binary")
    c2 = sha(repo)
    code, err = run_hook(repo, tmp_cfg, f"refs/heads/main {c2} refs/heads/main {c1}\n")
    assert code == 0, err
    # by hand too: the binary was staged for removal only
    commit_binary(repo, "other.bin", "c3")
    git(repo, "rm", "-q", "other.bin")
    monkeypatch.chdir(repo)
    git(repo, "update-ref", "refs/remotes/origin/main", sha(repo))
    assert leak_main([]) == 0


def test_binary_added_in_a_merge_blocks(tmp_cfg, monkeypatch, capsys):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    commit_file(repo, "a.txt", "hello\n", "c1")
    git(repo, "checkout", "-q", "-b", "side")
    commit_file(repo, "b.txt", "side work\n", "c2")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    # the binary enters only in the merge commit itself
    (repo / "merged.bin").write_bytes(BINARY)
    git(repo, "add", "merged.bin")
    git(repo, "commit", "-q", "--no-verify", "-m", "merge side")
    monkeypatch.chdir(repo)
    assert leak_main([]) == 1
    assert "merged.bin" in capsys.readouterr().err


def test_binary_in_a_pushed_range_blocks(tmp_cfg, monkeypatch):
    write_denylist(tmp_cfg, "SecretWord")
    repo = new_repo(tmp_cfg, monkeypatch)
    c1 = commit_file(repo, "clean.txt", "hello\n", "c1")
    c2 = commit_binary(repo, "image.bin", "c2")
    code, err = run_hook(repo, tmp_cfg, f"refs/heads/main {c2} refs/heads/main {c1}\n")
    assert code == 1, err
    assert "image.bin" in err
    # a binary changed in place blocks as well
    (repo / "image.bin").write_bytes(BINARY + b"\x00more")
    git(repo, "commit", "-q", "--no-verify", "-am", "c3")
    c3 = sha(repo)
    code, err = run_hook(repo, tmp_cfg, f"refs/heads/main {c3} refs/heads/main {c2}\n")
    assert code == 1, err
    assert "image.bin" in err
