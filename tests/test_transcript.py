import json
import pickle
import re
from pathlib import Path

import pytest

from conftest import fx
from tutor_any_lecture.acquire.importer import import_transcript
from tutor_any_lecture.transcript import (
    Health,
    Segment,
    Transcript,
    health,
    parse_srt,
    parse_stamped_txt,
    parse_vtt,
    parse_whisper_json,
    primary_subtag,
)
from tutor_any_lecture.unit import UnitPaths

# UTF-8 BOM, CRLF line ends, "," before the milliseconds. Built in the test; never a committed file.
CRLF_BOM_SRT: bytes = (
    b"\xef\xbb\xbf"
    b"1\r\n00:00:01,500 --> 00:00:03,000\r\nGood morning\r\n\r\n"
    b"2\r\n00:00:03,200 --> 00:00:06,000\r\nToday we study\r\ncompound interest\r\n"
)

BASE = [Segment(i * 10, i * 10 + 9, f"s{i}") for i in range(60)]


def read(name):
    if name == "crlf_bom.srt":
        return CRLF_BOM_SRT.decode("utf-8")
    return fx("transcripts", name).read_bytes().decode("utf-8")


def test_srt_crlf_bom_comma_ms():
    segs = parse_srt(read("crlf_bom.srt"))
    assert segs[0].start == 1.5 and segs[0].text == "Good morning"


def test_vtt_header_and_settings():
    segs = parse_vtt(read("cues.vtt"))
    assert segs[1].start == 62.0 and "align:start" not in segs[1].text


def test_stamped_txt_hours():
    segs = parse_stamped_txt("[1:02:03] a\n[1:02:10] b\n", None)
    assert segs[0].start == 3723 and segs[0].end == 3730 and segs[1].end == 3735


def test_health_thresholds():
    segs = [Segment(i * 10, i * 10 + 9, f"s{i}") for i in range(60)]
    h = health(segs, 600.0)
    assert h.ok and h.coverage >= 0.9


def test_health_detects_loop():
    segs = [Segment(i, i + 1, "thank you") for i in range(6)] + [Segment(7, 600, "x")]
    assert health(segs, 600.0).loop


def test_health_unknown_duration():
    h = health([Segment(0, 5, "a")], None)
    assert h.ok and not h.duration_known


@pytest.mark.parametrize(
    "segs, failed",
    [
        ([Segment(i * 10, i * 10 + 9, f"s{i}") for i in range(3, 57)], lambda h: h.coverage < 0.9),
        ([Segment(i * 10, i * 10 + 9, f"s{i // 4}") for i in range(60)], lambda h: h.repetition > 0.5 and not h.loop),
        ([s for i, s in enumerate(BASE) if not 24 <= i <= 36], lambda h: not h.spots_ok),
        (BASE + [Segment(600, 603, "tail")], lambda h: h.overrun),
    ],
    ids=["coverage", "repetition", "spots", "overrun"],
)
def test_health_fails_each_threshold(segs, failed):
    h = health(segs, 600.0)
    assert not h.ok and failed(h)


def test_health_empty_segments():
    assert health([], 600.0) == Health(0.0, 0.0, False, False, False, False, True)
    assert health([], None) == Health(0.0, 0.0, False, False, False, False, False)


def test_variants_parse_identically():
    lf = "1\n00:00:01,500 --> 00:00:03,000\nGood morning\n"
    crlf = "\ufeff" + lf.replace("\n", "\r\n").replace(",", ".")
    vtt = "WEBVTT\n\n00:00:01.500 --> 00:00:03.000 align:start\nGood morning\n"
    assert parse_srt(lf) == parse_srt(crlf) == parse_vtt(vtt) == [Segment(1.5, 3.0, "Good morning")]


def test_vtt_inline_tags_and_cue_end():
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "<v Ann>hi<00:00:01.500><c> there</c></v>\n\n"
        "00:00:03.000 --> 00:00:03.010\n"
        " \n\n"
        "00:00:03.010 --> 00:00:05.000 align:start position:0%\n"
        " \n"
        "a < b holds\n"
    )
    segs = parse_vtt(vtt)
    assert [s.text for s in segs] == ["hi there", "a < b holds"]
    assert segs[1].start == 3.01


def test_stamped_txt_continuation_and_last_end():
    segs = parse_stamped_txt(read("stamped.txt"), 3725.0)
    assert [s.start for s in segs] == [0.0, 7.0, 62.0, 3723.0]
    assert segs[1].text == "Today we cover discounting and why it matters"
    assert segs[1].end == 62.0 and segs[3].end == 3725.0
    assert parse_stamped_txt("no time stamps here\n", None) == []


def test_whisper_json_shapes():
    obj = json.loads(read("whisper.json"))
    segs = parse_whisper_json(obj)
    assert segs == parse_whisper_json(obj["segments"])
    assert segs[0].text == "Compound interest grows on itself." and segs[0].words[0]["word"] == " Compound"
    assert segs[1].start == 4.2 and segs[1].words is None


def test_transcript_json_round_trip(tmp_path):
    t = Transcript(
        [Segment(0.0, 1.5, "复利 grows", [{"word": "复利", "start": 0.0, "end": 0.7}]), Segment(1.5, 3.0, "fast")],
        "zh",
    )
    p = tmp_path / "transcript.json"
    p.write_text(t.to_json(), encoding="utf-8", newline="\n")
    raw = p.read_bytes()
    assert Transcript.from_json(p) == t and t.text() == "复利 grows fast"
    assert raw.endswith(b"\n") and b"\r" not in raw and "复利".encode("utf-8") in raw
    data = json.loads(raw.decode("utf-8"))
    assert list(data) == ["language", "segments"] and "words" not in data["segments"][1]


def test_primary_subtag():
    assert primary_subtag("en-orig") == "en"
    assert primary_subtag("zh-Hans") == "zh"
    assert primary_subtag("ZH_hant") == "zh"
    assert primary_subtag("ja") == "ja"
    assert primary_subtag(None) is None and primary_subtag("") is None and primary_subtag("auto") is None


def test_import_crlf_bom_srt_file(tmp_path):
    f = tmp_path / "crlf_bom.srt"
    f.write_bytes(CRLF_BOM_SRT)
    unit = tmp_path / "unit"
    import_transcript(f, unit, None, False)
    first = Transcript.from_json(UnitPaths(unit).transcript).segments[0]
    assert first.start == 1.5 and first.text == "Good morning"


def test_vtt_keeps_text_in_angle_brackets():
    vtt = (
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n"
        "if x <c and y> d then <code> stays, <v Ann>Hello <c.loud>there</c></v>\n"
    )
    assert parse_vtt(vtt) == [Segment(1.0, 3.0, "if x <c and y> d then <code> stays, Hello there")]


def test_vtt_entities_decoded():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nQ&amp;A: a &lt; b &gt; c&nbsp;d &lt;i&gt;\n"
    assert parse_vtt(vtt) == [Segment(1.0, 3.0, "Q&A: a < b > c d <i>")]


def test_stamped_last_segment_never_ends_before_start():
    assert parse_stamped_txt("[10:00] late\n", 300.0) == [Segment(600.0, 600.0, "late")]


def test_no_literal_bom_in_python_files():
    root = Path(__file__).resolve().parents[1]
    folders = (root / "src", root / "tests", root / "tools")
    files = sorted(f for folder in folders for f in folder.rglob("*.py"))
    assert files
    offenders = [str(f) for f in files if "\ufeff" in f.read_text(encoding="utf-8")]
    assert offenders == []


def test_no_private_use_characters_in_python_files():
    root = Path(__file__).resolve().parents[1]
    files = sorted(f for folder in (root / "src", root / "tests") for f in folder.rglob("*.py"))
    assert files
    private_use = re.compile("[\ue000-\uf8ff]")
    offenders = [str(f) for f in files if private_use.search(f.read_text(encoding="utf-8"))]
    assert offenders == []


def test_transcript_pickles():
    t = Transcript([Segment(0.0, 1.0, "hi", [{"word": "hi", "start": 0.0, "end": 1.0}])], "en")
    assert pickle.loads(pickle.dumps(t)) == t


def test_whisper_json_missing_times_is_value_error():
    with pytest.raises(ValueError) as exc:
        parse_whisper_json([{"start": 0, "text": "a"}])
    assert str(exc.value) == "segment 1 has no start or end time"


@pytest.mark.parametrize(
    "obj, message",
    [
        ({"segments": 5}, "expected a list of segments"),
        ([{"start": 0, "end": 1, "text": "a"}, 7], "segment 2 is not an object"),
        ([{"start": "x", "end": 1, "text": "a"}], "segment 1 has a start or end time that is not a number"),
        ([{"start": 0, "end": None, "text": "a"}], "segment 1 has no start or end time"),
    ],
    ids=["segments-not-list", "item-not-object", "time-not-number", "end-null"],
)
def test_whisper_json_malformed_is_value_error(obj, message):
    with pytest.raises(ValueError) as exc:
        parse_whisper_json(obj)
    assert str(exc.value) == message


def test_whisper_json_item_without_text_is_skipped_before_time_check():
    assert parse_whisper_json([{"start": 0}, {"start": 0, "end": 1, "text": "a"}]) == [Segment(0.0, 1.0, "a")]
