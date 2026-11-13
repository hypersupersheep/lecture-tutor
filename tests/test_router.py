import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import fx
from tutor_any_lecture.acquire.router import route
from tutor_any_lecture.cli import main


def touch(folder, *names):
    # local helper: create empty files
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"")


def boom(*args, **kwargs):
    # local helper: any call is a test failure
    raise AssertionError("route() must not start a process")


def kinds(steps):
    # local helper: the two tokens after "tutor-any-lecture" in each step
    return [s["argv"][1:3] for s in steps]


def test_pdf_beats_photos(tmp_path):
    touch(tmp_path, "a.pdf", "1.jpg", "2.jpg", "3.jpg", "v.mp4")
    assert route(tmp_path)["slide_source"] == "pdf"


def test_transcript_skips_asr(tmp_path):
    touch(tmp_path, "v.mp4", "v.srt")
    steps = route(tmp_path)["steps"]
    assert (
        steps[0]["argv"][1:3] == ["acquire", "import"]
        and not any("transcribe" in s["argv"] for s in steps)
        and not any(s["argv"][1:3] == ["acquire", "local"] for s in steps)
    )


def test_two_videos_asks(tmp_path):
    touch(tmp_path, "a.mp4", "b.mp4")
    assert route(tmp_path)["questions"]


def test_never_executes(tmp_path, monkeypatch):
    touch(tmp_path, "v.mp4", "a.pdf")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    steps = route(tmp_path)["steps"]
    assert any(s["argv"][1:3] == ["acquire", "local"] for s in steps)


def test_video_alone_uses_acquire_local(tmp_path):
    touch(tmp_path, "v.mp4")
    plan = route(tmp_path)
    video = str(tmp_path.resolve() / "v.mp4")
    asr = [s for s in plan["steps"] if s["argv"][1:3] == ["acquire", "local"]]
    assert len(asr) == 1
    assert asr[0]["argv"] == ["tutor-any-lecture", "acquire", "local", "--file", video, "--unit", "<unit>"]
    assert asr[0]["gpu"] is True and asr[0]["network"] is True and asr[0]["runnable"] is True
    assert asr[0]["reads"] == [video]
    assert plan["files"]["video"] == [video]
    assert plan["questions"] == []


def test_slides_step_precedes_asr(tmp_path):
    touch(tmp_path / "a", "v.mp4", "a.pdf")
    assert kinds(route(tmp_path / "a")["steps"]) == [["slides", "--pdf"], ["acquire", "local"]]
    touch(tmp_path / "b", "v.srt", "a.pdf")
    assert kinds(route(tmp_path / "b")["steps"]) == [["acquire", "import"], ["slides", "--pdf"]]


def test_slide_source_precedence(tmp_path):
    touch(tmp_path / "a", "a.pptx", "1.jpg", "2.jpg", "3.jpg", "v.mp4")
    touch(tmp_path / "b", "1.jpg", "2.JPG", "3.png", "v.mp4")
    touch(tmp_path / "c", "1.jpg", "2.jpg", "v.mp4")
    touch(tmp_path / "d", "a.mp3")
    assert route(tmp_path / "a")["slide_source"] == "pptx-deferred"
    assert route(tmp_path / "b")["slide_source"] == "photos-deferred"
    assert route(tmp_path / "c")["slide_source"] == "keyframes-deferred"
    assert route(tmp_path / "d")["slide_source"] == "none"


def test_deferred_step_not_runnable(tmp_path):
    touch(tmp_path, "a.pptx", "v.srt")
    plan = route(tmp_path)
    deferred = [s for s in plan["steps"] if not s["runnable"]]
    assert plan["slide_source"] == "pptx-deferred"
    assert len(deferred) == 1 and plan["steps"][-1] is deferred[0]
    assert deferred[0]["argv"] == ["tutor-any-lecture"]
    assert deferred[0]["reads"] == [str(tmp_path.resolve() / "a.pptx")]
    assert deferred[0]["writes"] == []


def test_panopto_extract_routes_to_panopto(tmp_path):
    touch(tmp_path, "v.mp4")
    (tmp_path / "extract.json").write_bytes(fx("panopto", "plain.json").read_bytes())
    steps = route(tmp_path)["steps"]
    assert steps[0]["argv"][1:4] == ["acquire", "panopto", "--extract"]
    assert steps[0]["argv"][4] == str(tmp_path.resolve() / "extract.json")
    assert not any("transcribe" in s["argv"] for s in steps)
    assert not any(s["argv"][1:3] == ["acquire", "local"] for s in steps)


def test_tool_results_wrapper_routes_to_panopto(tmp_path):
    inner = fx("panopto", "plain.json").read_text(encoding="utf-8")
    wrapper = json.dumps([{"type": "text", "text": inner}], ensure_ascii=False)
    (tmp_path / "saved.json").write_text(wrapper, encoding="utf-8", newline="\n")
    assert kinds(route(tmp_path)["steps"]) == [["acquire", "panopto"]]


def test_whisper_json_is_imported(tmp_path):
    seg = {"start": 0.0, "end": 2.0, "text": "hello"}
    touch(tmp_path / "a")
    (tmp_path / "a" / "w.json").write_text(json.dumps({"segments": [seg]}), encoding="utf-8", newline="\n")
    touch(tmp_path / "b")
    (tmp_path / "b" / "w.json").write_text(json.dumps([seg]), encoding="utf-8", newline="\n")
    assert kinds(route(tmp_path / "a")["steps"]) == [["acquire", "import"]]
    assert kinds(route(tmp_path / "b")["steps"]) == [["acquire", "import"]]

    # a dict that has both a segments list and a transcript string is imported, not sent to panopto
    touch(tmp_path / "c")
    (tmp_path / "c" / "w.json").write_text(json.dumps({"segments": [seg], "transcript": "x"}), encoding="utf-8", newline="\n")
    assert kinds(route(tmp_path / "c")["steps"]) == [["acquire", "import"]]


def test_other_json_is_not_a_transcript(tmp_path):
    touch(tmp_path, "v.mp4", "empty.json")
    (tmp_path / "plan.json").write_text('{"course": "C", "unit": "U1"}\n', encoding="utf-8", newline="\n")
    (tmp_path / "list.json").write_text("[]\n", encoding="utf-8", newline="\n")
    plan = route(tmp_path)
    root = tmp_path.resolve()
    assert plan["files"]["transcript"] == []
    assert plan["files"]["other"] == [str(root / "empty.json"), str(root / "list.json"), str(root / "plan.json")]
    assert plan["questions"] == []
    assert any(s["argv"][1:3] == ["acquire", "local"] for s in plan["steps"])


def test_ambiguous_class_gets_question_not_step(tmp_path):
    touch(tmp_path / "a", "a.mp4", "b.mp3")
    plan = route(tmp_path / "a")
    root = (tmp_path / "a").resolve()
    assert [q["about"] for q in plan["questions"]] == ["media"]
    assert plan["questions"][0]["candidates"] == [str(root / "a.mp4"), str(root / "b.mp3")]
    assert not any(s["argv"][1:3] == ["acquire", "local"] for s in plan["steps"])
    assert plan["questions"][0]["argv"] == [
        ["tutor-any-lecture", "acquire", "local", "--file", str(root / "a.mp4"), "--unit", "<unit>"],
        ["tutor-any-lecture", "acquire", "local", "--file", str(root / "b.mp3"), "--unit", "<unit>"],
    ]

    touch(tmp_path / "b", "v.mp4", "x.srt", "y.vtt", "s1.pdf", "s2.pdf")
    plan = route(tmp_path / "b")
    root = (tmp_path / "b").resolve()
    assert [q["about"] for q in plan["questions"]] == ["transcript", "pdf"]
    assert plan["slide_source"] == "pdf"
    assert plan["steps"] == []
    # Task 25: the one recording in the folder gives each candidate import its duration.
    v = str(root / "v.mp4")
    assert plan["questions"][0]["argv"] == [
        ["tutor-any-lecture", "acquire", "import", "--file", str(root / "x.srt"), "--media", v, "--unit", "<unit>"],
        ["tutor-any-lecture", "acquire", "import", "--file", str(root / "y.vtt"), "--media", v, "--unit", "<unit>"],
    ]
    assert plan["questions"][1]["argv"] == [
        ["tutor-any-lecture", "slides", "--pdf", str(root / "s1.pdf"), "--unit", "<unit>"],
        ["tutor-any-lecture", "slides", "--pdf", str(root / "s2.pdf"), "--unit", "<unit>"],
    ]

    # a Panopto extract among the candidates keeps its own command in the parallel argv list
    touch(tmp_path / "c", "x.srt")
    (tmp_path / "c" / "extract.json").write_bytes(fx("panopto", "plain.json").read_bytes())
    plan = route(tmp_path / "c")
    root = (tmp_path / "c").resolve()
    assert plan["questions"][0]["candidates"] == [str(root / "extract.json"), str(root / "x.srt")]
    assert [a[1:3] for a in plan["questions"][0]["argv"]] == [["acquire", "panopto"], ["acquire", "import"]]
    assert plan["questions"][0]["argv"][0][4] == str(root / "extract.json")
    assert plan["steps"] == []


def test_unit_in_argv_and_writes(tmp_path):
    folder = tmp_path / "materials"
    touch(folder, "v.srt", "a.pdf")
    unit = tmp_path / "courses" / "C" / "U1"

    steps = route(folder)["steps"]
    assert all(s["argv"][s["argv"].index("--unit") + 1] == "<unit>" for s in steps)
    assert steps[0]["writes"] == ["<unit>/sources/transcript.json", "<unit>/sources/source.json"]
    assert steps[1]["writes"] == ["<unit>/sources/slides/pages.json", "<unit>/sources/source.json"]

    steps = route(folder, unit)["steps"]
    u = unit.resolve()
    assert all(s["argv"][s["argv"].index("--unit") + 1] == str(u) for s in steps)
    assert steps[0]["writes"] == [str(u / "sources" / "transcript.json"), str(u / "sources" / "source.json")]
    assert steps[1]["writes"] == [str(u / "sources" / "slides" / "pages.json"), str(u / "sources" / "source.json")]
    assert not unit.exists()


def test_slides_step_always_writes_source(tmp_path):
    # Task 25: slides --pdf records its digest in source.json, existing or not.
    touch(tmp_path, "v.srt", "a.pdf")
    steps = route(tmp_path)["steps"]
    assert steps[1]["writes"] == ["<unit>/sources/slides/pages.json", "<unit>/sources/source.json"]


def test_slides_first_may_write_source(tmp_path):
    touch(tmp_path, "a.pdf")
    plan = route(tmp_path)
    assert kinds(plan["steps"]) == [["slides", "--pdf"]]
    assert plan["steps"][0]["writes"] == ["<unit>/sources/slides/pages.json", "<unit>/sources/source.json"]


def test_missing_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        route(tmp_path / "nope")
    assert main(["acquire", "route", "--folder", str(tmp_path / "nope"), "--unit", str(tmp_path / "unit")]) == 1


def test_cli_route_prints_plan(tmp_path, capsys):
    folder = tmp_path / "课程 资料" / "第1周"
    touch(folder, "v.mp4", "a.pdf")
    unit = tmp_path / "unit"
    assert main(["acquire", "route", "--folder", str(folder), "--unit", str(unit)]) == 0
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1
    plan = json.loads(out)
    assert set(plan) == {"files", "slide_source", "steps", "questions"}
    assert plan["steps"][0]["argv"][:3] == ["tutor-any-lecture", "slides", "--pdf"]
    assert plan["steps"][0]["argv"][3] == str(folder.resolve() / "a.pdf")
    assert plan["steps"][0]["argv"][-1] == str(unit.resolve())
    assert not unit.exists()


def test_cli_route_requires_unit(tmp_path):
    with pytest.raises(SystemExit) as e:
        main(["acquire", "route", "--folder", str(tmp_path)])
    assert e.value.code == 2


def test_dot_files_and_subfolders_are_skipped(tmp_path):
    touch(tmp_path, ".hidden.srt", ".DS_Store", "a.pdf")
    touch(tmp_path / "sub", "v.mp4")
    (tmp_path / "x.srt").mkdir()   # a folder with a transcript suffix is still a folder
    plan = route(tmp_path)
    root = tmp_path.resolve()
    listed = [f for fs in plan["files"].values() for f in fs]
    assert listed == [str(root / "a.pdf")]
    assert kinds(plan["steps"]) == [["slides", "--pdf"]]
    assert plan["questions"] == []


def test_panopto_step_writes_include_chapters(tmp_path):
    (tmp_path / "extract.json").write_bytes(fx("panopto", "plain.json").read_bytes())
    steps = route(tmp_path)["steps"]
    assert kinds(steps) == [["acquire", "panopto"]]
    assert steps[0]["writes"] == [
        "<unit>/sources/transcript.json", "<unit>/sources/chapters.json", "<unit>/sources/source.json",
    ]


def test_deferred_steps_read_their_files(tmp_path):
    touch(tmp_path / "photos", "1.jpg", "2.png", "3.heic", "v.mp4")
    touch(tmp_path / "frames", "a.mp4", "b.mkv", "c.mp3", "x.srt")
    photos = route(tmp_path / "photos")
    frames = route(tmp_path / "frames")
    p_root, f_root = (tmp_path / "photos").resolve(), (tmp_path / "frames").resolve()
    assert photos["slide_source"] == "photos-deferred" and frames["slide_source"] == "keyframes-deferred"
    p_deferred = [s for s in photos["steps"] if not s["runnable"]]
    f_deferred = [s for s in frames["steps"] if not s["runnable"]]
    assert len(p_deferred) == 1 and len(f_deferred) == 1
    assert p_deferred[0]["reads"] == [str(p_root / n) for n in ("1.jpg", "2.png", "3.heic")]
    # Keyframes come from video files only, never from audio.
    assert f_deferred[0]["reads"] == [str(f_root / "a.mp4"), str(f_root / "b.mkv")]


def test_no_media_question_when_transcript_exists(tmp_path):
    touch(tmp_path, "a.mp4", "b.mp4", "c.mp3", "x.srt")
    plan = route(tmp_path)
    assert plan["questions"] == []
    assert kinds(plan["steps"])[0] == ["acquire", "import"]
    assert not any(s["argv"][1:3] == ["acquire", "local"] for s in plan["steps"])


# ---- Task 25: media for the import, unsafe names ---------------------------------


def test_import_step_carries_the_media_file(tmp_path):
    touch(tmp_path, "v.mp4", "v.srt")
    root = tmp_path.resolve()
    step = route(tmp_path)["steps"][0]
    assert step["argv"] == [
        "tutor-any-lecture", "acquire", "import", "--file", str(root / "v.srt"),
        "--media", str(root / "v.mp4"), "--unit", "<unit>",
    ]
    assert step["reads"] == [str(root / "v.srt"), str(root / "v.mp4")]

    # Two recordings: which one is unknown, so no --media.
    touch(tmp_path / "two", "a.mp4", "b.m4a", "x.srt")
    assert "--media" not in route(tmp_path / "two")["steps"][0]["argv"]
    # A Panopto extract takes no --media.
    touch(tmp_path / "pan", "v.mp4")
    (tmp_path / "pan" / "extract.json").write_bytes(fx("panopto", "plain.json").read_bytes())
    assert "--media" not in route(tmp_path / "pan")["steps"][0]["argv"]


@pytest.mark.skipif(sys.platform == "win32", reason="these characters are not allowed in Windows file names")
def test_unsafe_file_names_are_not_planned(tmp_path):
    touch(tmp_path, "$(touch x).mp4", "ok.vtt")
    plan = route(tmp_path)
    root = tmp_path.resolve()
    odd = str(root / "$(touch x).mp4")
    assert [s["argv"][1:5] for s in plan["steps"]] == [["acquire", "import", "--file", str(root / "ok.vtt")]]
    assert not any(odd in s["argv"] or odd in s["reads"] for s in plan["steps"])
    assert plan["files"]["other"] == [odd] and plan["files"]["video"] == []
    assert [q["about"] for q in plan["questions"]] == ["unsafe-name"]
    q = plan["questions"][0]
    assert q["candidates"] == [odd]
    assert q["text"] == ("These file names contain characters that are unsafe on a command line; "
                         "rename them, then run the route again.")


@pytest.mark.skipif(sys.platform == "win32", reason="these characters are not allowed in Windows file names")
@pytest.mark.parametrize("name", ["a`b`.srt", 'q"x.pdf', "back\\slash.mp3", "semi;colon.vtt", "pipe|x.mp4",
                                  "amp&x.mp4", "lt<x.mp4", "gt>x.mp4", "tab\tx.srt"])
def test_each_unsafe_character_is_caught(tmp_path, name):
    touch(tmp_path, name)
    plan = route(tmp_path)
    assert plan["steps"] == [] and plan["files"]["other"] == [str(tmp_path.resolve() / name)]
    assert [q["about"] for q in plan["questions"]] == ["unsafe-name"]
