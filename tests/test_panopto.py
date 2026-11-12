import json

import pytest

from conftest import fx
from tutor_any_lecture.acquire.panopto import import_panopto, load_extract
from tutor_any_lecture.cli import main
from tutor_any_lecture.transcript import EmptyTranscript, Transcript
from tutor_any_lecture.unit import UnitPaths


def write_extract(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8", newline="\n")
    return p


def test_tool_results_wrapper_with_tail():
    d = load_extract(fx("panopto", "tool_results.json"))
    assert d["n"] == 3


def test_import_writes_three_files(tmp_path):
    h = import_panopto(fx("panopto", "plain.json"), tmp_path, False)
    u = UnitPaths(tmp_path)
    assert u.transcript.exists()
    assert u.chapters.exists()
    assert json.loads(u.source.read_text(encoding="utf-8"))["platform"] == "panopto"
    assert h.ok


def test_lecture_date_parsed(tmp_path):
    import_panopto(fx("panopto", "plain.json"), tmp_path, False)
    src = json.loads(UnitPaths(tmp_path).source.read_text(encoding="utf-8"))
    assert src["lecture_date"] == "2026-10-06 16:00"


def test_duration_is_last_stamp(tmp_path):
    h = import_panopto(fx("panopto", "plain.json"), tmp_path, False)
    u = UnitPaths(tmp_path)
    src = json.loads(u.source.read_text(encoding="utf-8"))
    t = Transcript.from_json(u.transcript)
    assert src["duration"] == 80
    assert h.duration_known
    assert not h.overrun
    assert h.coverage == 1.0
    assert len(t.segments) == 6
    assert t.segments[-1].start == 80
    assert t.segments[-1].end == 80
    assert t.language is None
    assert src["lecture_language"] is None
    assert src["kind"] == "platform"
    assert src["acquisition"] == "panopto"
    assert src["health"]["ok"] is True


def test_single_stamp_at_zero_has_unknown_duration(tmp_path):
    extract = write_extract(tmp_path, "one.json", {"transcript": "[0:00] only line"})
    unit = tmp_path / "u"
    h = import_panopto(extract, unit, False)
    src = json.loads(UnitPaths(unit).source.read_text(encoding="utf-8"))
    assert src["duration"] is None
    assert not h.duration_known
    assert h.ok
    assert src["title"] == ""
    assert src["url"] is None
    assert src["lecture_date"] is None
    assert Transcript.from_json(UnitPaths(unit).transcript).segments[0].end == 5


def test_chapters_title_and_start(tmp_path):
    import_panopto(fx("panopto", "plain.json"), tmp_path, False)
    chapters = json.loads(UnitPaths(tmp_path).chapters.read_text(encoding="utf-8"))
    assert chapters == [
        {"title": "Welcome", "start": 0.0},
        {"title": "Limpets and anemones", "start": 31.0},
        {"title": "Closing Remarks", "start": 3723.0},
        {"title": "Untimed note", "start": None},
    ]


def test_panopto_refuses_overwrite(tmp_path):
    unit = tmp_path / "课程 资料" / "第1周"
    import_panopto(fx("panopto", "plain.json"), unit, False)
    before = UnitPaths(unit).transcript.read_bytes()
    with pytest.raises(FileExistsError):
        import_panopto(fx("panopto", "plain.json"), unit, False)
    # A missing extract still gives FileExistsError: the guard runs before the extract is read.
    with pytest.raises(FileExistsError):
        import_panopto(tmp_path / "missing.json", unit, False)
    assert UnitPaths(unit).transcript.read_bytes() == before
    import_panopto(fx("panopto", "tool_results.json"), unit, True)
    assert len(Transcript.from_json(UnitPaths(unit).transcript).segments) == 3


def test_empty_transcript_writes_nothing(tmp_path):
    extract = write_extract(tmp_path, "empty.json", {"title": "T", "transcript": "", "contents": []})
    unit = tmp_path / "u"
    with pytest.raises(EmptyTranscript):
        import_panopto(extract, unit, False)
    u = UnitPaths(unit)
    assert not u.transcript.exists()
    assert not u.chapters.exists()
    assert not u.source.exists()


def test_cli_acquire_panopto(tmp_path, capsys):
    argv = ["acquire", "panopto", "--extract", str(fx("panopto", "plain.json")), "--unit", str(tmp_path / "u")]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["health"]["ok"] is True
    assert main(argv) == 3
    assert "--force" in capsys.readouterr().err
    assert main(argv + ["--force"]) == 0
