import json

import pytest

from tutor_any_lecture.cli import main
from tutor_any_lecture.plan import PlanError, load_plan, safe_name


def write_plan(folder, concepts=5, tracked=5, drop=(), **fields):
    """Local helper: write folder/plan.json with concrete values and return its path."""
    folder.mkdir(parents=True, exist_ok=True)
    plan = {
        "course": "C", "unit": "U1", "goal": "deep", "content_type": "concept",
        "note_language": "en", "lecture_language": "en", "duration_s": 180,
        "outputs": ["explanation", "pretest", "quiz", "cards", "map"], "sections": [],
        "concepts": [{"id": f"c{i}", "name": f"Concept {i}", "type": "definition",
                      "citations": [f"(slide {i})"]} for i in range(1, concepts + 1)],
        "tracked": [f"c{i}" for i in range(1, tracked + 1)],
        "output_target": "markdown",
    }
    plan.update(fields)
    for key in drop:
        del plan[key]
    path = folder / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def test_tracked_must_be_five(tmp_path):
    path = write_plan(tmp_path, concepts=7, tracked=4)
    with pytest.raises(PlanError):
        load_plan(path)


def test_auto_language_rejected(tmp_path):
    good = load_plan(write_plan(tmp_path / "good"))
    assert (good.note_language, good.output_target, good.duration_s) == ("en", "markdown", 180.0)
    assert load_plan(write_plan(tmp_path / "few", concepts=3, tracked=3)).tracked == ["c1", "c2", "c3"]
    auto = write_plan(tmp_path / "auto", note_language="Auto")
    with pytest.raises(PlanError):
        load_plan(auto)
    auto2 = write_plan(tmp_path / "auto2", lecture_language="auto")
    with pytest.raises(PlanError):
        load_plan(auto2)


def test_missing_key_rejected(tmp_path):
    path = write_plan(tmp_path, drop=("output_target",))
    with pytest.raises(PlanError):
        load_plan(path)


# ---- names, languages and unreadable files (Task 21) ------------------------


def one_line_error(capsys):
    """Local helper: the captured stderr, asserting it is exactly one line and stdout is empty."""
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("\n") and captured.err.count("\n") == 1
    return captured.err


@pytest.mark.parametrize("value", ["a/b", "a\\b", "..", ".", "a:b", " a", "a ", "a.", "a\tb", ""])
def test_safe_name_rejects_unsafe_names(value):
    with pytest.raises(PlanError):
        safe_name(value, "course")


def test_safe_name_accepts_spaces_and_cjk():
    for value in ("课程 资料", "第1周", "CS 101 - Intro"):
        assert safe_name(value, "course") == value


def test_load_plan_rejects_unsafe_course(tmp_path):
    path = write_plan(tmp_path, course="CS 101: Intro")
    with pytest.raises(PlanError) as e:
        load_plan(path)
    assert str(e.value).startswith("plan.json: course name")


def test_language_with_trailing_newline_is_rejected(tmp_path):
    path = write_plan(tmp_path, note_language="en\n")
    with pytest.raises(PlanError):
        load_plan(path)


def test_cli_plan_not_utf8_is_one_line(tmp_path, capsys):
    unit = tmp_path / "课程 资料" / "第1周"
    unit.mkdir(parents=True)
    (unit / "plan.json").write_bytes(b"\xff\xfe")
    assert main(["verify", "--unit", str(unit)]) == 1
    assert one_line_error(capsys).startswith("plan.json")



@pytest.mark.parametrize(
    "key, value",
    [
        ("goal", "fast"),
        ("output_target", "html"),
        ("note_language", "EN"),
        ("duration_s", "90"),
        ("tracked", ["c1", "c2", "c3", "c4", "c9"]),
        ("tracked", ["c1", "c1", "c2", "c3", "c4"]),
    ],
    ids=["bad-goal", "bad-output-target", "malformed-language", "duration-not-number",
         "unknown-tracked-id", "duplicate-tracked-id"],
)
def test_load_plan_faults(tmp_path, key, value):
    path = write_plan(tmp_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan[key] = value
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(PlanError):
        load_plan(path)
