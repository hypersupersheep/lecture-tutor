import json

import pytest

from fixtures.make_pdf import make_pdf
from tutor_any_lecture.acquire.importer import import_transcript
from tutor_any_lecture.cli import main
from tutor_any_lecture.slides import Page, extract_pdf
from tutor_any_lecture.suspects import _tokens, flag_suspects
from tutor_any_lecture.transcript import Segment, Transcript
from tutor_any_lecture.unit import UnitPaths

SLIDE = "A martingale has constant expectation"
VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nThe martingail property holds\n"


def make_unit(tmp_path):
    unit = tmp_path / "unit"
    vtt = tmp_path / "lecture.vtt"
    vtt.write_text(VTT, encoding="utf-8", newline="\n")
    import_transcript(vtt, unit, None, False)
    extract_pdf(make_pdf(tmp_path, [SLIDE + "\n1/1"]), unit)
    return unit


def test_flags_near_miss():
    transcript = Transcript([Segment(12.0, 15.0, "the martingail property holds")], "en")
    found = flag_suspects(transcript, [Page(1, None, SLIDE)], "en")
    assert len(found) == 1
    assert found[0]["time"] == 12.0
    assert found[0]["heard"] == "martingail" and found[0]["nearest"] == "martingale"
    assert found[0]["ratio"] == pytest.approx(0.9)


def test_no_slide_terms_no_suspects():
    transcript = Transcript([Segment(0.0, 2.0, "the martingail property")], None)
    assert flag_suspects(transcript, [Page(1, None, "a b c")], "") == []
    assert flag_suspects(transcript, [], "") == []


def test_ignores_diacritics_only():
    transcript = Transcript([Segment(0.0, 4.0, "by the Poincare inequality we get a bound")], "en")
    assert flag_suspects(transcript, [Page(1, None, "The Poincaré inequality")], "en") == []


def test_one_entry_per_segment_and_token():
    transcript = Transcript(
        [Segment(1.0, 4.0, "The martingail and the Martingail"), Segment(5.0, 6.0, "martingail again")],
        None,
    )
    found = flag_suspects(transcript, [Page(1, None, SLIDE)], "")
    assert [(s["time"], s["heard"]) for s in found] == [(1.0, "martingail"), (5.0, "martingail")]


def test_transcript_unchanged(tmp_path):
    unit = make_unit(tmp_path)
    paths = UnitPaths(unit)
    before = paths.transcript.read_bytes()
    assert main(["slides", "suspects", "--unit", str(unit)]) == 0
    assert paths.transcript.read_bytes() == before
    found = json.loads(paths.suspects.read_text(encoding="utf-8"))
    assert [(s["time"], s["heard"], s["nearest"]) for s in found] == [(1.0, "martingail", "martingale")]


def test_cli_suspects_needs_transcript(tmp_path):
    assert main(["slides", "suspects", "--unit", str(tmp_path)]) == 1
    assert not UnitPaths(tmp_path).suspects.exists()


def test_cjk_punctuation_ends_a_run():
    tokens = _tokens("ブラック・ショールズ")
    assert not any("・" in t for t in tokens)
    assert "ブラ" in tokens and "ショ" in tokens
    assert not any("゠" in t for t in _tokens("ブラック゠ショールズ"))
