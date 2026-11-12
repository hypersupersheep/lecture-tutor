import dataclasses
import hashlib
import json
import shutil

import pytest

from conftest import fx
from tutor_any_lecture.acquire.importer import import_transcript
from tutor_any_lecture.cli import main
from tutor_any_lecture.source import SourceInfo, sha256_file
from tutor_any_lecture.transcript import Transcript
from tutor_any_lecture.unit import UnitPaths


def slides_only_info():
    return SourceInfo(
        kind="slides-only", title="deck", url=None, platform=None, duration=None, lecture_language=None,
        acquisition="slides", health={}, tool_versions={}, inputs_sha256={},
    )


def test_import_refuses_overwrite(tmp_path):
    unit = tmp_path / "课程 资料" / "第1周"
    import_transcript(fx("transcripts", "cues.vtt"), unit, None, False)
    with pytest.raises(FileExistsError):
        import_transcript(fx("transcripts", "cues.vtt"), unit, None, False)
    assert UnitPaths(unit).transcript.exists()


def test_import_writes_contract_files(tmp_path):
    src = fx("transcripts", "stamped.txt")
    h = import_transcript(src, tmp_path, None, False)
    u = UnitPaths(tmp_path)
    t = Transcript.from_json(u.transcript)
    s = json.loads(u.source.read_text(encoding="utf-8"))
    assert h.ok and not h.duration_known
    assert t.language is None and len(t.segments) == 4 and t.segments[-1].end == 3728.0
    assert s["kind"] == "transcript" and s["acquisition"] == "import" and s["title"] == "stamped"
    assert s["lecture_language"] is None and s["duration"] is None and s["url"] is None
    assert s["health"] == dataclasses.asdict(h)
    assert s["inputs_sha256"] == {"stamped.txt": sha256_file(src)}


def test_import_whisper_json_language_is_null(tmp_path):
    import_transcript(fx("transcripts", "whisper.json"), tmp_path, None, False)
    t = Transcript.from_json(UnitPaths(tmp_path).transcript)
    assert t.language is None and len(t.segments) == 2 and t.segments[0].words[0]["word"] == " Compound"


def test_import_replaces_slides_only_source(tmp_path):
    u = UnitPaths(tmp_path)
    slides_only_info().write(u.source)
    import_transcript(fx("transcripts", "cues.vtt"), tmp_path, None, False)
    assert SourceInfo.read(u.source).kind == "transcript"


def test_source_info_round_trip_and_value_sets(tmp_path):
    info = slides_only_info()
    p = tmp_path / "sources" / "source.json"
    info.write(p)
    assert SourceInfo.read(p) == info and SourceInfo.read(p).lecture_date is None
    with pytest.raises(ValueError):
        dataclasses.replace(info, acquisition="none")
    with pytest.raises(ValueError):
        dataclasses.replace(info, kind="slides")


def test_sha256_file_matches_hashlib(tmp_path):
    data = b"ab" * 600_000  # 1.2 MB, so more than one 1 MiB chunk
    p = tmp_path / "blob.bin"
    p.write_bytes(data)
    assert sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_cli_import_spaced_cjk_path(tmp_path, capsys):
    folder = tmp_path / "课程 资料"
    folder.mkdir()
    f = folder / "cues.vtt"
    shutil.copyfile(fx("transcripts", "cues.vtt"), f)
    unit = folder / "第1周"
    assert main(["acquire", "import", "--file", str(f), "--unit", str(unit)]) == 0
    assert UnitPaths(unit).transcript.exists()
    out = capsys.readouterr().out
    obj = json.loads(out)
    assert len(out.splitlines()) == 1 and set(obj) == {"status", "health"}
    assert obj["status"] == "ok" and obj["health"]["ok"] is True and obj["health"]["duration_known"] is False


def test_cli_import_unhealthy_exit_1(tmp_path, capsys):
    unit = tmp_path / "u"
    argv = ["acquire", "import", "--file", str(fx("transcripts", "cues.vtt")), "--unit", str(unit), "--duration", "600"]
    code = main(argv)
    obj = json.loads(capsys.readouterr().out)
    assert code == 1 and obj["status"] == "unhealthy"
    assert obj["health"]["coverage"] < 0.9 and obj["health"]["spots_ok"] is False
    assert UnitPaths(unit).transcript.exists() and UnitPaths(unit).source.exists()


def test_cli_import_empty_is_error(tmp_path, capsys):
    f = tmp_path / "plain.txt"
    f.write_text("no time stamps here\n", encoding="utf-8", newline="\n")
    unit = tmp_path / "u"
    code = main(["acquire", "import", "--file", str(f), "--unit", str(unit)])
    assert code == 1
    assert json.loads(capsys.readouterr().out) == {"status": "error", "message": "no timed segments found"}
    assert not UnitPaths(unit).transcript.exists() and not UnitPaths(unit).source.exists()


def test_cli_import_refuses_then_force(tmp_path, capsys):
    unit = tmp_path / "u"
    argv = ["acquire", "import", "--file", str(fx("transcripts", "cues.vtt")), "--unit", str(unit)]
    assert main(argv) == 0
    capsys.readouterr()
    assert main(argv) == 3
    captured = capsys.readouterr()
    assert captured.out == "" and "--force" in captured.err
    assert main(argv + ["--force"]) == 0
