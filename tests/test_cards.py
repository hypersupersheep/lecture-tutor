import hashlib
import json

import pytest

from conftest import status_of
from tutor_any_lecture.cards import (
    Card, add_misses, export_tsv, guid, load_cards, tag, validate_cards,
)
from tutor_any_lecture.cli import main
from tutor_any_lecture.profile import set_value
from tutor_any_lecture.progress import Attempt, log_attempt
from tutor_any_lecture.unit import UnitPaths

# ---- local helpers ---------------------------------------------------------

ITEM_IDS = [f"c{i}-{v}" for i in range(1, 6) for v in "ABCDE"]  # 25 ids, c1-A … c5-E
PHASES = ["post", "d1", "d7", "d21"]


def card(front, back="A short answer.", citation="(slide 1)", id="k1", concept="c1", kind="core"):
    """One Card; keyword arguments override fields."""
    return Card(id=id, concept=concept, front=front, back=back, citation=citation, kind=kind)


def cards(n):
    """n core cards k1 … kn whose fronts share no character 3-gram."""
    return [card(f"Q{i}?", id=f"k{i}") for i in range(1, n + 1)]


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def unit_with_cards(tmp_path, n=3):
    """A unit folder (its name is not plan.unit) with plan.json and n core cards, no `kind` key."""
    u = tmp_path / "课程 资料" / "第1周"
    u.mkdir(parents=True)
    write_json(u / "plan.json", {
        "course": "C", "unit": "U1", "goal": "deep", "content_type": "concept",
        "note_language": "en", "lecture_language": "en", "duration_s": 180,
        "outputs": ["explanation", "pretest", "quiz", "cards", "map"], "sections": [],
        "concepts": [{"id": f"c{i}", "name": f"Concept {i}", "type": "definition",
                      "citations": [f"(slide {i})"]} for i in range(1, 6)],
        "tracked": ["c1", "c2", "c3", "c4", "c5"], "output_target": "markdown",
    })
    write_json(u / "cards.json", [
        {"id": f"k{i}", "concept": "c1", "front": f"Q{i}?", "back": f"A{i}.", "citation": "(slide 1)"}
        for i in range(1, n + 1)
    ])
    return u


def unit_with_misses(tmp_path, misses=14):
    """(unit, workspace): 2 core cards, 26 items, `misses` qualifying attempts and 6 that must not count."""
    u = unit_with_cards(tmp_path, n=2)

    def item(id, concept, variant):
        return {"id": id, "concept": concept, "kind": "apply", "prompt": f"Prompt {id}?",
                "answer": f"Answer {id}.", "rubric": "R.", "citation": f"(slide {concept[1]})",
                "difficulty": 2, "variant": variant}

    write_json(u / "items.json", {
        "tracked": {f"c{i}": {v: item(f"c{i}-{v}", f"c{i}", v) for v in "ABCDE"} for i in range(1, 6)},
        "practice": [item("p1", "c1", None)],
    })
    ws = tmp_path / "ws"

    def log(item_id, unit="U1", phase="post", score=0):
        variant = None if item_id == "p1" else item_id[-1]
        log_attempt(Attempt(ts="2026-11-20T10:00:00+00:00", course="C", unit=unit, item_id=item_id,
                            variant=variant, concept=item_id[:2], phase=phase, score=score,
                            confidence=2, citation="(slide 1)", exposure="unknown"), ws)

    for k, item_id in enumerate(ITEM_IDS[:misses]):
        log(item_id, phase=PHASES[k % 4], score=(0, 0.5)[k % 2])
    log(ITEM_IDS[0], phase="d7")        # second miss on the same item: still one card
    log(ITEM_IDS[-3], score=1)          # answered correctly
    log(ITEM_IDS[-2], phase="pre")      # a pretest miss is not a miss card
    log("p1", phase="practice")         # nor is a practice miss
    log(ITEM_IDS[-1], unit="U2")        # another unit of the same course
    log("c9-A")                         # an id that is not in items.json
    return u, ws


# ---- the plan's five tests -------------------------------------------------

def test_header_exact(tmp_path):
    p = export_tsv(unit_with_cards(tmp_path, n=3))
    assert p.read_text(encoding="utf-8").splitlines()[:6] == [
        "#separator:tab", "#html:true", "#notetype:Basic",
        "#deck:C::U1", "#tags column:3", "#guid column:4",
    ]


def test_guid_stable_across_runs(tmp_path):
    u = unit_with_cards(tmp_path, n=3)
    a = export_tsv(u).read_text(encoding="utf-8")
    b = export_tsv(u).read_text(encoding="utf-8")
    assert a == b
    assert guid("C", "U1", "k") == hashlib.sha256("C|U1|k".encode()).hexdigest()[:16]
    assert guid("C", "U1", "k1") == hashlib.sha256(b"C|U1|k1").hexdigest()[:16]
    rows = a.splitlines()[6:]
    assert len(rows) == 3
    assert rows[0].split("\t") == ["Q1?", "A1.<br><small>(slide 1)</small>", "C::U1::c1", guid("C", "U1", "k1")]
    assert a.endswith("\n") and not a.endswith("\n\n")


def test_cap_quick():
    assert status_of(validate_cards(cards(11), "quick", "en"), "count") == "FAIL"


def test_near_duplicates():
    assert status_of(
        validate_cards([card("What is a martingale?"), card("What is a martingale ?")], "deep", "en"),
        "duplicates",
    ) == "FAIL"


def test_misses_capped_and_idempotent(tmp_path):
    u, ws = unit_with_misses(tmp_path, misses=14)
    assert add_misses(u, "C", ws) == 10 and add_misses(u, "C", ws) == 0


# ---- validate_cards --------------------------------------------------------

def test_validate_returns_four_named_results():
    results = validate_cards(cards(3), "deep", "en")
    assert [r.name for r in results] == ["count", "duplicates", "citation", "back_length"]
    assert [r.status for r in results] == ["PASS"] * 4
    assert all(r.details == [] for r in results)


def test_cap_counts_core_only():
    assert status_of(validate_cards(cards(26), "deep", "en"), "count") == "FAIL"
    assert status_of(validate_cards(cards(25), "deep", "en"), "count") == "PASS"
    assert status_of(validate_cards(cards(10), "quick", "en"), "count") == "PASS"
    with_miss = cards(25) + [card("Extra", id="c1-A|miss", kind="miss")]
    assert status_of(validate_cards(with_miss, "deep", "en"), "count") == "PASS"


def test_duplicates_ignore_miss_cards():
    pair = [card("What is a martingale?"), card("What is a martingale ?", id="c1-A|miss", kind="miss")]
    assert status_of(validate_cards(pair, "deep", "en"), "duplicates") == "PASS"


def test_long_back_warns():
    assert status_of(validate_cards([card("Q?", back="x" * 351)], "deep", "en"), "back_length") == "WARN"
    assert status_of(validate_cards([card("Q?", back="x" * 350)], "deep", "en"), "back_length") == "PASS"


def test_missing_citation_fails():
    results = validate_cards([card("Q?", citation=" ", id="c1-A|miss", kind="miss")], "deep", "en")
    assert status_of(results, "citation") == "FAIL"


# ---- cards.json, tag, TSV fields -------------------------------------------

def test_load_cards_defaults_kind(tmp_path):
    u = unit_with_cards(tmp_path, n=3)
    loaded = load_cards(UnitPaths(u).cards_json)
    assert [(c.id, c.kind) for c in loaded] == [("k1", "core"), ("k2", "core"), ("k3", "core")]


@pytest.mark.parametrize("payload", [
    {"cards": []},
    ["k1"],
    [{"id": "k1", "concept": "c1", "front": "Q?", "back": "A."}],
    [{"id": "k1", "concept": "c1", "front": "Q?", "back": "A.", "citation": "(slide 1)", "kind": "bonus"}],
    [{"id": "k1", "concept": "c1", "front": "Q?", "back": "A.", "citation": "(slide 1)", "deck": "X"}],
    [{"id": 1, "concept": "c1", "front": "Q?", "back": "A.", "citation": "(slide 1)"}],
])
def test_load_cards_rejects_malformed(tmp_path, payload):
    p = tmp_path / "cards.json"
    write_json(p, payload)
    with pytest.raises(ValueError):
        load_cards(p)


def test_tag_replaces_spaces():
    assert tag("C", "Week 1", "stopping time") == "C::Week_1::stopping_time"


def test_tabs_and_newlines_become_br(tmp_path):
    u = unit_with_cards(tmp_path, n=1)
    write_json(UnitPaths(u).cards_json, [
        {"id": "k1", "concept": "c1", "front": "Q\tone", "back": "line one\r\nline two", "citation": "(slide 2)"},
    ])
    lines = export_tsv(u).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 7
    assert lines[6].split("\t")[:2] == ["Q<br>one", "line one<br>line two<br><small>(slide 2)</small>"]


# ---- miss cards ------------------------------------------------------------

def test_miss_cards_built_from_items(tmp_path):
    u, ws = unit_with_misses(tmp_path, misses=3)
    assert add_misses(u, "C", ws) == 3
    loaded = load_cards(UnitPaths(u).cards_json)
    assert [c.id for c in loaded] == ["k1", "k2", "c1-A|miss", "c1-B|miss", "c1-C|miss"]
    assert loaded[2] == Card(id="c1-A|miss", concept="c1", front="Prompt c1-A?",
                             back="Answer c1-A.", citation="(slide 1)", kind="miss")
    rows = UnitPaths(u).cards_tsv.read_text(encoding="utf-8").splitlines()[6:]
    assert len(rows) == 5
    assert rows[2].split("\t") == [
        "Prompt c1-A?", "Answer c1-A.<br><small>(slide 1)</small>", "C::U1::c1",
        hashlib.sha256("C|U1|c1-A|miss".encode()).hexdigest()[:16],
    ]
    assert add_misses(u, "C", ws) == 0
    assert len(load_cards(UnitPaths(u).cards_json)) == 5


def test_add_misses_rejects_other_course(tmp_path):
    u, ws = unit_with_misses(tmp_path, misses=3)
    with pytest.raises(ValueError):
        add_misses(u, "Other", ws)
    assert len(load_cards(UnitPaths(u).cards_json)) == 2
    assert not UnitPaths(u).cards_tsv.exists()


# ---- CLI -------------------------------------------------------------------

def test_cli_cards_export(tmp_path, capsys):
    u = unit_with_cards(tmp_path, n=3)
    assert main(["cards", "export", "--unit", str(u)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(UnitPaths(u).cards_tsv)}
    assert len(UnitPaths(u).cards_tsv.read_text(encoding="utf-8").splitlines()) == 9


def test_cli_cards_export_malformed_exits_1(tmp_path, capsys):
    u = unit_with_cards(tmp_path, n=3)
    write_json(UnitPaths(u).cards_json, {"cards": []})
    assert main(["cards", "export", "--unit", str(u)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.strip() != ""
    assert not UnitPaths(u).cards_tsv.exists()


def test_cli_add_misses_workspace_flag(tmp_path, capsys):
    u, ws = unit_with_misses(tmp_path, misses=3)
    assert main(["cards", "add-misses", "--unit", str(u), "--workspace", str(ws)]) == 0
    assert json.loads(capsys.readouterr().out) == {"added": 3, "path": str(UnitPaths(u).cards_tsv)}


def test_cli_add_misses_default_workspace(tmp_cfg, capsys):
    u, ws = unit_with_misses(tmp_cfg, misses=3)
    set_value("workspace", str(ws))
    assert main(["cards", "add-misses", "--unit", str(u)]) == 0
    assert json.loads(capsys.readouterr().out)["added"] == 3


def test_cli_add_misses_takes_no_course(tmp_path):
    u, ws = unit_with_misses(tmp_path, misses=3)
    with pytest.raises(SystemExit) as e:
        main(["cards", "add-misses", "--unit", str(u), "--course", "C", "--workspace", str(ws)])
    assert e.value.code == 2


def test_cli_cards_not_utf8_is_one_line(tmp_path, capsys):
    u = unit_with_cards(tmp_path, n=3)
    UnitPaths(u).cards_json.write_bytes(b"\xff\xfe")
    assert main(["cards", "export", "--unit", str(u)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("\n") and captured.err.count("\n") == 1
    assert captured.err.startswith("cards.json")
    assert not UnitPaths(u).cards_tsv.exists()



def test_cli_bare_cards_is_usage():
    with pytest.raises(SystemExit) as e:
        main(["cards"])
    assert e.value.code == 2


# ---- safe HTML, math and code (Task 23) --------------------------------------


def exported_row(tmp_path, front="Q?", back="A.", citation="(slide 1)"):
    """Local helper: export one core card and return its row's fields."""
    u = unit_with_cards(tmp_path, n=1)
    write_json(UnitPaths(u).cards_json, [
        {"id": "k1", "concept": "c1", "front": front, "back": back, "citation": citation},
    ])
    return export_tsv(u).read_text(encoding="utf-8").split("\n")[6].split("\t")


def test_export_escapes_html(tmp_path):
    row = exported_row(tmp_path, front="Is a<b when std::vector<int> v(3)? R&D", citation="(slide 1 & 2)")
    assert row[0] == "Is a&lt;b when std::vector&lt;int&gt; v(3)? R&amp;D"
    assert row[1] == "A.<br><small>(slide 1 &amp; 2)</small>"


def test_export_converts_math(tmp_path):
    assert exported_row(tmp_path / "a", front=r"$\hat{\theta} = \bar{X}$")[0] == r"\(\hat{\theta} = \bar{X}\)"
    assert exported_row(tmp_path / "b", front="$$x^2$$")[0] == r"\[x^2\]"
    assert exported_row(tmp_path / "c", front=r"costs \$5")[0] == "costs $5"
    assert exported_row(tmp_path / "d", front=r"$a<b$ but `$x$ \$y` stays")[0] == (
        r"\(a&lt;b\) but <code>$x$ \$y</code> stays")


def test_export_keeps_code_blocks(tmp_path):
    back = "Run this:\n```cpp\nif (a<b) {\n    return v[0];\n}\n```\nDone."
    row = exported_row(tmp_path, back=back)
    assert row[1] == (
        "Run this:<br><pre><code>if (a&lt;b) {<br>    return v[0];<br>}</code></pre><br>Done."
        "<br><small>(slide 1)</small>"
    )


def test_miss_card_citation_appears_once(tmp_path):
    u, ws = unit_with_misses(tmp_path, misses=1)
    path = UnitPaths(u).items
    items = json.loads(path.read_text(encoding="utf-8"))
    for variants in items["tracked"].values():
        for it in variants.values():
            it["answer"] = f"{it['answer']} {it['citation']}"
    write_json(path, items)
    assert add_misses(u, "C", ws) == 1
    rows = UnitPaths(u).cards_tsv.read_text(encoding="utf-8").splitlines()[6:]
    assert rows[2].split("\t")[1] == "Answer c1-A. (slide 1)"
    assert rows[0].split("\t")[1] == "A1.<br><small>(slide 1)</small>"


# ---- miss cards from a live run (Task 29, L4) --------------------------------


@pytest.mark.parametrize("back, citation", [
    ("关系可以不止一个（4:14–4:37）。", "(4:14–4:37)"),
    ("关系可以不止一个（4:14–4:37）", "(4:14–4:37)"),
    ("A relation may hold several outputs (4:14–4:37).", "(4:14–4:37)"),
    ("A relation may hold several outputs (4:14–4:37) . ", "(4:14–4:37)"),
    ("It is θ (slide 3)!", "（slide 3）"),
])
def test_citation_is_not_repeated_after_full_width_parentheses(tmp_path, back, citation):
    row = exported_row(tmp_path, back=back, citation=citation)
    assert "<small>" not in row[1]


def test_citation_is_added_when_the_back_ends_otherwise(tmp_path):
    row = exported_row(tmp_path, back="See (4:14–4:37) for the definition.", citation="(4:14–4:37)")
    assert row[1].endswith("<br><small>(4:14–4:37)</small>")
    row = exported_row(tmp_path / "other", back="Several (4:14).", citation="(4:14–4:37)")
    assert row[1].endswith("<br><small>(4:14–4:37)</small>")


def test_back_length_rule_covers_miss_cards():
    long_miss = card("Q?", back="x" * 351, id="c1-A|miss", kind="miss")
    results = validate_cards([card("Q?"), long_miss], "deep", "en")
    assert status_of(results, "back_length") == "WARN"
    assert next(r.details for r in results if r.name == "back_length") == ["c1-A|miss: back has 351 characters"]
