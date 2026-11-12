import json

import pytest

from tutor_any_lecture.plan import PlanError, load_plan


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
