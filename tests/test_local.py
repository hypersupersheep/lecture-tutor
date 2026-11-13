import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

import pytest

from tutor_any_lecture import asr, slides
from tutor_any_lecture.acquire import local
from tutor_any_lecture.acquire.local import acquire_local, transcribe_audio
from tutor_any_lecture.cli import main
from tutor_any_lecture.ffmpeg import ffmpeg_exe
from tutor_any_lecture.profile import Profile
from tutor_any_lecture.source import SourceInfo, sha256_file
from tutor_any_lecture.transcript import AcquireError, EmptyTranscript, Segment, Transcript
from tutor_any_lecture.unit import UnitPaths


def _boom(audio, model, **kwargs):
    # Module-level, so the spawn child can unpickle it.
    raise RuntimeError("boom")


def temp_parent(base):
    """Local helper: the tool's temp parent under ``base``, as this OS names it."""
    if sys.platform == "win32":
        return Path(base) / "tutor-any-lecture"
    return Path(base) / f"tutor-any-lecture-{os.getuid()}"


def make_tone(folder):
    """Local helper: a 2 s tone in ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / "tone.wav"
    subprocess.run([ffmpeg_exe(), "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(src)],
                   check=True, capture_output=True)
    return src


class FakeASR:
    """Local helper: in-process stand-in for asr.transcribe."""

    def __init__(self, segments=None, error=None):
        self.segments = [Segment(0.0, 2.0, "hello world")] if segments is None else segments
        self.error = error
        self.calls = []

    def __call__(self, audio, language, initial_prompt, budget_minutes, backend=None, model=None):
        audio = Path(audio)
        self.calls.append({"audio": audio, "existed": audio.exists(), "language": language,
                           "initial_prompt": initial_prompt, "budget_minutes": budget_minutes,
                           "backend": backend, "model": model})
        if self.error is not None:
            raise self.error
        return asr.AsrTranscript(list(self.segments), "en", device="cpu")


def install_fake_asr(monkeypatch, **kwargs):
    """Local helper: replaces asr.transcribe and asr.resolve_backend in-process."""
    fake = FakeASR(**kwargs)
    monkeypatch.setattr(asr, "transcribe", fake)
    monkeypatch.setattr(asr, "resolve_backend", lambda backend=None, model=None: (backend or "fake", model))
    return fake


def run_acquire_local_with_fake_asr(monkeypatch, tmp_path):
    """Local helper: returns the temp dirs the audio lived in."""
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    acquire_local(src, unit, Profile(), False)
    assert [c["existed"] for c in fake.calls] == [True]   # the temp audio existed while ASR ran
    dirs = [c["audio"].parent for c in fake.calls]
    assert all(d != src.parent and unit not in (d, *d.parents) for d in dirs)
    return dirs


def test_local_deletes_temp_audio(monkeypatch, tmp_path):
    tmp_dirs = run_acquire_local_with_fake_asr(monkeypatch, tmp_path)
    assert tmp_dirs
    assert all(not d.exists() for d in tmp_dirs)


def test_local_writes_source_and_language(monkeypatch, tmp_path):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    paths = UnitPaths(unit)
    paths.ensure()
    SourceInfo(kind="slides-only", title="deck", url=None, platform=None, duration=None,
               lecture_language=None, acquisition="slides", health={}, tool_versions={},
               inputs_sha256={}).write(paths.source)
    fake = install_fake_asr(monkeypatch)
    h = acquire_local(src, unit, Profile(), False)   # a slides-only source.json needs no --force
    assert h.ok
    call = fake.calls[0]
    assert call["language"] is None                  # profile "auto" -> None
    assert call["initial_prompt"] == ""              # no pages.json -> slide_terms([]) == ""
    assert call["budget_minutes"] == 30.0            # max(30.0, 2 * 2.0 / 60)
    assert call["backend"] == "fake" and call["model"] is None
    assert paths.transcript.exists()
    source = json.loads(paths.source.read_text(encoding="utf-8"))
    assert source["kind"] == "local" and source["acquisition"] == "asr"
    assert source["lecture_language"] == "en"
    assert abs(source["duration"] - 2.0) < 0.1
    assert source["inputs_sha256"] == {"tone.wav": sha256_file(src)}
    assert source["health"]["ok"] is True
    assert source["tool_versions"]["asr_backend"] == "fake"
    assert source["tool_versions"]["asr_device"] == "cpu"


def test_local_passes_slide_terms_as_prompt(monkeypatch, tmp_path):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    pages = [slides.Page(1, None, "Black-Scholes martingale")]
    monkeypatch.setattr(slides, "load_pages", lambda unit: pages)
    fake = install_fake_asr(monkeypatch)
    acquire_local(src, unit, Profile(), False)
    prompt = fake.calls[0]["initial_prompt"]
    assert prompt == slides.slide_terms(pages) and "martingale" in prompt


def test_local_refuses_overwrite(monkeypatch, tmp_path):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    acquire_local(src, unit, Profile(), False)
    before = UnitPaths(unit).transcript.read_bytes()
    with pytest.raises(FileExistsError):
        acquire_local(src, unit, Profile(), False)
    with pytest.raises(FileExistsError):
        transcribe_audio(src, unit, Profile(), False)
    assert len(fake.calls) == 1                       # the fake ASR was not invoked again
    assert UnitPaths(unit).transcript.read_bytes() == before
    acquire_local(src, unit, Profile(), True)         # force overwrites
    assert len(fake.calls) == 2


def test_local_empty_transcript_writes_nothing(monkeypatch, tmp_path, tmp_cfg, capsys):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    install_fake_asr(monkeypatch, segments=[])
    with pytest.raises(EmptyTranscript):
        acquire_local(src, unit, Profile(), False)
    assert not UnitPaths(unit).transcript.exists() and not UnitPaths(unit).source.exists()
    code = main(["acquire", "local", "--file", str(src), "--unit", str(unit)])
    assert code == 1
    assert json.loads(capsys.readouterr().out) == {"status": "error", "message": "no timed segments found"}


def test_cli_acquire_local_ok(monkeypatch, tmp_path, tmp_cfg, capsys):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    code = main(["acquire", "local", "--file", str(src), "--unit", str(unit), "--budget-minutes", "7"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "ok" and out["health"]["ok"] is True
    assert fake.calls[0]["budget_minutes"] == 7.0
    assert main(["acquire", "local", "--file", str(src), "--unit", str(unit)]) == 3   # exists, no --force
    assert main(["acquire", "local", "--file", str(src), "--unit", str(unit), "--force"]) == 0


def test_cli_transcribe_ok(monkeypatch, tmp_path, tmp_cfg, capsys):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    code = main(["transcribe", "--audio", str(src), "--unit", str(unit),
                 "--backend", "fake", "--model", "m1", "--budget-minutes", "7"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "ok"
    call = fake.calls[0]
    assert call["audio"] == src                       # no extraction step
    assert call["backend"] == "fake" and call["model"] == "m1" and call["budget_minutes"] == 7.0
    source = json.loads(UnitPaths(unit).source.read_text(encoding="utf-8"))
    assert source["kind"] == "local" and source["acquisition"] == "asr"
    assert source["inputs_sha256"] == {"tone.wav": sha256_file(src)}
    assert source["tool_versions"]["asr_model"] == "m1"
    assert main(["transcribe", "--audio", str(src), "--unit", str(unit)]) == 3        # exists, no --force
    assert len(fake.calls) == 1


def test_cli_missing_file_exits_1(monkeypatch, tmp_path, tmp_cfg):
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    missing = tmp_path / "课程 资料" / "nope.wav"
    assert main(["acquire", "local", "--file", str(missing), "--unit", str(unit)]) == 1
    assert main(["transcribe", "--audio", str(missing), "--unit", str(unit)]) == 1
    assert not fake.calls and not UnitPaths(unit).transcript.exists()


def test_cli_budget_exceeded_exits_3(monkeypatch, tmp_path, tmp_cfg):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch, error=asr.BudgetExceeded("over budget"))
    assert main(["acquire", "local", "--file", str(src), "--unit", str(unit)]) == 3
    assert not UnitPaths(unit).transcript.exists()
    assert fake.calls and not fake.calls[0]["audio"].parent.exists()   # temp audio removed on failure too


def test_cli_local_backend_failure_is_error_json(monkeypatch, tmp_path, tmp_cfg, capsys):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    # The real asr.transcribe and its child process, with a backend that raises.
    monkeypatch.setitem(asr.BACKENDS, "fake", _boom)
    monkeypatch.setattr(asr, "resolve_backend", lambda backend=None, model=None: ("fake", "x"))
    code = main(["acquire", "local", "--file", str(src), "--unit", str(unit)])
    out = capsys.readouterr().out
    assert code == 1
    lines = out.splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["status"] == "error" and "boom" in obj["message"]
    assert not UnitPaths(unit).transcript.exists()


@pytest.mark.parametrize("command", ["transcribe", "acquire local"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_cli_budget_minutes_must_be_positive(monkeypatch, tmp_path, tmp_cfg, command, value):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    flag = "--audio" if command == "transcribe" else "--file"
    with pytest.raises(SystemExit) as exc:
        main([*command.split(), flag, str(src), "--unit", str(unit), "--budget-minutes", value])
    assert exc.value.code == 2
    assert not fake.calls and not UnitPaths(unit).transcript.exists()


def test_local_backend_missing_before_extraction(monkeypatch, tmp_path):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    extracted = []
    monkeypatch.setattr(local, "extract_audio", lambda src, dst: extracted.append(dst))

    def missing(backend=None, model=None):
        raise asr.BackendMissing("no ASR backend is installed")

    monkeypatch.setattr(asr, "resolve_backend", missing)
    with pytest.raises(asr.BackendMissing):
        acquire_local(src, unit, Profile(), False)
    assert extracted == [] and not unit.exists()


def test_local_undeletable_temp_warns_on_stderr(monkeypatch, tmp_path, capsys):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    fake = install_fake_asr(monkeypatch)
    # rmtree does nothing, but only where local.py calls it.
    monkeypatch.setattr(local, "shutil", types.SimpleNamespace(rmtree=lambda *a, **k: None))
    acquire_local(src, unit, Profile(), False)
    folder = fake.calls[0]["audio"].parent
    try:
        assert folder.exists()
        captured = capsys.readouterr()
        lines = captured.err.splitlines()
        assert len(lines) == 1
        assert lines[0].startswith("warning: could not delete the temporary folder") and str(folder) in lines[0]
        assert captured.out == ""
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_local_guard_fires_before_missing_input(monkeypatch, tmp_path):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    install_fake_asr(monkeypatch)
    acquire_local(src, unit, Profile(), False)
    missing = tmp_path / "课程 资料" / "nope.wav"
    with pytest.raises(FileExistsError):
        acquire_local(missing, unit, Profile(), False)
    with pytest.raises(FileExistsError):
        transcribe_audio(missing, unit, Profile(), False)


# A child process: enters the temporary-folder helper under main's signal handling, then waits.
SIGTERM_CHILD = """
import sys, time
from tutor_any_lecture import cli
from tutor_any_lecture.acquire import local

def hold(args):
    with local.temp_dir() as tmp:
        (tmp / "audio.wav").write_bytes(b"audio")
        print(tmp, flush=True)
        time.sleep(60)
    return 0

cli._cmd_profile_show = hold
sys.exit(cli.main(["profile", "show"]))
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_runs_cleanup(tmp_path):
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    proc = subprocess.Popen([sys.executable, "-c", SIGTERM_CHILD], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        line = proc.stdout.readline().decode("utf-8", errors="replace").strip()
        assert line, proc.stderr.read().decode("utf-8", errors="replace")
        folder = Path(line)
        assert folder.parent == temp_parent(tmp_path) and (folder / "audio.wav").exists()
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 143, err.decode("utf-8", errors="replace")
        assert not folder.exists()
        assert folder.parent.is_dir()   # only the run's own folder goes
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def test_stale_temp_folders_are_swept(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    parent = temp_parent(tmp_path)
    old, recent = parent / "old-run", parent / "recent-run"
    now = time.time()
    for folder, age in ((old, 2 * 86400), (recent, 3600)):
        folder.mkdir(parents=True)
        (folder / "audio.wav").write_bytes(b"audio")
        os.utime(folder, (now - age, now - age))
    with local.temp_dir() as tmp:
        assert tmp.parent == parent
        assert not old.exists() and recent.exists()
    assert not tmp.exists() and recent.exists()

    # acquire_local makes its folder under the same parent, after the same sweep.
    os.utime(recent, (now - 2 * 86400, now - 2 * 86400))
    src = make_tone(tmp_path / "课程 资料")
    fake = install_fake_asr(monkeypatch)
    acquire_local(src, tmp_path / "课程 资料" / "第1周", Profile(), False)
    assert fake.calls[0]["audio"].parent.parent == parent
    assert not recent.exists()


def test_sweep_errors_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    old = temp_parent(tmp_path) / "old-run"
    old.mkdir(parents=True)
    os.utime(old, (time.time() - 2 * 86400,) * 2)

    real_rmtree = shutil.rmtree

    def refuse_old(path, *args, **kwargs):
        if Path(path).name == "old-run":
            raise PermissionError("in use")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(local, "shutil", types.SimpleNamespace(rmtree=refuse_old))
    with local.temp_dir() as tmp:
        assert tmp.is_dir()
    assert old.exists() and not tmp.exists()


def tree(path):
    """Local helper: every path under ``path`` (links not followed), with its kind."""
    found = []
    for root, dirs, files in os.walk(path):
        found += [(os.path.relpath(os.path.join(root, n), path), "dir") for n in dirs]
        found += [(os.path.relpath(os.path.join(root, n), path), "file") for n in files]
    return sorted(found)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_temp_parent_is_private_to_the_user(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    # A umask that would leave the folder unwritable to its owner: the mode is set exactly.
    old_umask = os.umask(0o277)
    try:
        with local.temp_dir() as tmp:
            parent = tmp.parent
            assert tmp.is_dir()
    finally:
        os.umask(old_umask)
    assert parent == tmp_path / f"tutor-any-lecture-{os.getuid()}"
    assert parent.name.endswith(str(os.getuid()))
    assert stat.S_IMODE(os.lstat(parent).st_mode) == 0o700
    assert not tmp.exists() and parent.is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
@pytest.mark.parametrize("kind", ["symlink", "mode-0777", "file"])
def test_untrusted_temp_parent_is_not_used(monkeypatch, tmp_path, kind):
    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    expected = temp_parent(base)
    stale_age = time.time() - 2 * 86400
    # What the untrusted path leads to holds a stale run folder that a sweep would remove.
    if kind == "symlink":
        watched = tmp_path / "elsewhere"
        watched.mkdir()
        expected.symlink_to(watched, target_is_directory=True)
    elif kind == "mode-0777":
        watched = expected
        watched.mkdir()
        os.chmod(watched, 0o777)
    else:
        watched = None
        expected.write_bytes(b"not a folder")
    if watched is not None:
        (watched / "old-run").mkdir()
        (watched / "old-run" / "audio.wav").write_bytes(b"audio")
        os.utime(watched / "old-run", (stale_age, stale_age))
        before = tree(watched)
    lstat_before = os.lstat(expected)

    src = make_tone(tmp_path / "课程 资料")
    fake = install_fake_asr(monkeypatch)
    h = acquire_local(src, tmp_path / "课程 资料" / "第1周", Profile(), False)
    assert h.ok
    run_folder = fake.calls[0]["audio"].parent
    assert fake.calls[0]["existed"]
    # The run's folder was somewhere else: a fresh private parent in the same temp folder.
    assert run_folder.parent.parent == base and run_folder.parent != expected
    if watched is not None:
        assert tree(watched) == before          # nothing created, nothing swept
    lstat_after = os.lstat(expected)
    assert (lstat_after.st_mode, lstat_after.st_ino) == (lstat_before.st_mode, lstat_before.st_ino)
    if kind == "file":
        assert expected.read_bytes() == b"not a folder"
    # The fresh parent went with the run's folder: only the untrusted path is left.
    assert [p.name for p in base.iterdir()] == [expected.name]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX folder creation")
def test_no_temp_folder_is_a_clean_error(monkeypatch, tmp_path):
    src = make_tone(tmp_path / "课程 资料")
    unit = tmp_path / "课程 资料" / "第1周"
    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    fake = install_fake_asr(monkeypatch)

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    with monkeypatch.context() as m:
        m.setattr(os, "mkdir", refuse)   # Path.mkdir and tempfile.mkdtemp both create through it
        with pytest.raises(AcquireError) as exc:
            acquire_local(src, unit, Profile(), False)
    assert str(exc.value).startswith("could not create a temporary folder")
    assert str(exc.value).startswith(f"could not create a temporary folder in {base}: ")
    assert not fake.calls and list(base.iterdir()) == []


# A child process: runs the ASR child-process helper with a slow fake backend under
# main's signal handling. The backend writes its own process id to the "audio" path.
ASR_CHILD_SCRIPT = """
import os, sys, time
from pathlib import Path
from tutor_any_lecture import asr, cli
from tutor_any_lecture.transcript import Segment, Transcript


def slow(audio, model, **kwargs):
    Path(audio).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(120)
    return Transcript([Segment(0.0, 1.0, "late")], None)


def run(args):
    asr.BACKENDS["slow"] = slow
    asr.transcribe(Path(sys.argv[1]), None, "", budget_minutes=5, backend="slow")
    return 0


if __name__ == "__main__":   # the spawn child imports this file too; only the parent runs main
    cli._cmd_profile_show = run
    sys.exit(cli.main(["profile", "show"]))
"""


def alive(pid):
    """Local helper: whether a process with this id still exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_ends_a_running_asr_child(tmp_path):
    script = tmp_path / "run_slow_asr.py"
    script.write_text(ASR_CHILD_SCRIPT, encoding="utf-8")
    pid_file = tmp_path / "child.pid"
    proc = subprocess.Popen([sys.executable, str(script), str(pid_file)], cwd=tmp_path,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child = None
    try:
        deadline = time.monotonic() + 60
        while not (pid_file.exists() and pid_file.read_text(encoding="utf-8").strip()):
            assert proc.poll() is None, proc.stderr.read().decode("utf-8", errors="replace")
            assert time.monotonic() < deadline, "the ASR child never started"
            time.sleep(0.05)
        child = int(pid_file.read_text(encoding="utf-8"))
        assert child != proc.pid and alive(child)
        # Every child of the process at this moment: the ASR child, and any helper it runs.
        children = {child}
        if shutil.which("pgrep"):
            listed = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True)
            children |= {int(p) for p in listed.stdout.split()}
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 143, err.decode("utf-8", errors="replace")
        # An ended child is reaped by its parent, or by init once the parent is gone.
        deadline = time.monotonic() + 10
        while any(alive(pid) for pid in children) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert [pid for pid in children if alive(pid)] == []
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        if child is not None and alive(child):
            os.kill(child, signal.SIGKILL)
