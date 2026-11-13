import json
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
