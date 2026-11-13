import json
import re
import tempfile
from importlib import resources

from tutor_any_lecture.cli import main
from tutor_any_lecture.selftest import run_selftest

SAMPLE_FILES = [
    "lecture.vtt", "slides.pdf", "plan.json", "explanation.md",
    "items.json", "cards.json", "map.json",
]
GATE_ENTRIES = ["citations", "coverage", "items", "cards", "map"]


def test_selftest_passes():
    assert run_selftest()["ok"] is True


def test_selftest_keep_leaves_unit(tmp_path):
    unit = tmp_path / "unit"
    assert main(["selftest", "--keep", str(unit)]) == 0
    assert (unit / "verify.json").exists()
    assert (unit / "explanation.md").exists()


def test_sample_in_package():
    sample = resources.files("tutor_any_lecture").joinpath("data", "sample")
    assert [n for n in SAMPLE_FILES if not sample.joinpath(n).is_file()] == []


def test_sample_gate_entries_pass(tmp_path):
    unit = tmp_path / "课程 资料" / "unit"
    result = run_selftest(unit)
    assert result["ok"] is True
    assert [s["name"] for s in result["steps"]] == [
        "import", "slides", "items assign", "cards export", "map mermaid", "verify",
    ]
    checks = json.loads((unit / "verify.json").read_text(encoding="utf-8"))["checks"]
    status = {c["name"]: c["status"] for c in checks}
    assert [n for n in GATE_ENTRIES if status[n] != "PASS"] == []


def test_selftest_refuses_nonempty_dir(tmp_path):
    mine = tmp_path / "plan.json"
    mine.write_text("mine\n", encoding="utf-8", newline="\n")
    assert main(["selftest", "--keep", str(tmp_path)]) == 3
    assert mine.read_text(encoding="utf-8") == "mine\n"
    assert not (tmp_path / "sources").exists()


# ---- the sample models good work ----

SAMPLE_TOPICS = ["Simple and compound interest", "Growth over n years", "Compounding frequency"]


def sample_json(name: str):
    sample = resources.files("tutor_any_lecture").joinpath("data", "sample")
    return json.loads(sample.joinpath(name).read_text(encoding="utf-8"))


def test_sample_note_has_one_h2_per_topic(tmp_path):
    unit = tmp_path / "unit"
    assert run_selftest(unit)["ok"] is True
    md = (unit / "explanation.md").read_text(encoding="utf-8")
    h2 = [line[3:].strip() for line in md.split("\n") if line.startswith("## ")]
    assert h2 == ["Pretest", *SAMPLE_TOPICS]
    assert [s["title"] for s in sample_json("plan.json")["sections"]] == SAMPLE_TOPICS


def test_sample_gate_has_no_warnings(tmp_path):
    unit = tmp_path / "unit"
    assert run_selftest(unit)["ok"] is True
    result = json.loads((unit / "verify.json").read_text(encoding="utf-8"))
    assert [(c["name"], c["details"]) for c in result["checks"] if c["status"] != "PASS"] == []
    assert result["warnings"] == 0


def test_sample_effective_rate_has_a_numeric_variant():
    answers = [item["answer"] for item in sample_json("items.json")["tracked"]["effective_rate"].values()]
    assert [a for a in answers if re.search(r"\d+(?:\.\d+)?%", a)] != []


# ---- failure paths and cleanup ----

STEP_NAMES = ["import", "slides", "items assign", "cards export", "map mermaid", "verify"]


def fail_cards_export(monkeypatch, seen: list | None = None) -> None:
    """Make the "cards export" step raise RuntimeError; record the unit folder it was given."""

    def boom(unit):
        if seen is not None:
            seen.append(unit)
        raise RuntimeError("boom")

    monkeypatch.setattr("tutor_any_lecture.selftest.export_tsv", boom)


def test_selftest_stops_at_the_first_failing_step(monkeypatch, tmp_path):
    fail_cards_export(monkeypatch)
    result = run_selftest(tmp_path / "unit")
    assert result["ok"] is False
    assert [s["name"] for s in result["steps"]] == STEP_NAMES[:4]
    assert [s["ok"] for s in result["steps"]] == [True, True, True, False]
    assert not (tmp_path / "unit" / "verify.json").exists()


def test_selftest_reports_the_exception_name(monkeypatch, tmp_path):
    fail_cards_export(monkeypatch)
    assert run_selftest(tmp_path / "unit")["steps"][-1]["detail"] == "RuntimeError: boom"
    assert main(["selftest"]) == 1


def test_selftest_removes_its_folder_after_a_failure(monkeypatch):
    seen: list = []
    fail_cards_export(monkeypatch, seen)
    assert run_selftest()["ok"] is False
    assert len(seen) == 1
    assert not seen[0].exists() and not seen[0].parent.exists()


def test_selftest_ignores_cleanup_errors(monkeypatch):
    real = tempfile.TemporaryDirectory
    kwargs_seen: list[dict] = []

    def spy(*args, **kwargs):
        kwargs_seen.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr("tutor_any_lecture.selftest.tempfile.TemporaryDirectory", spy)
    assert run_selftest()["ok"] is True
    assert [k.get("ignore_cleanup_errors") for k in kwargs_seen] == [True]
