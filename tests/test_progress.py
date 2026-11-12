import json
from datetime import date, datetime

import pytest

from tutor_any_lecture.cli import main
from tutor_any_lecture.plan import PlanError
from tutor_any_lecture.profile import set_value
from tutor_any_lecture.progress import (
    Attempt,
    confident_but_wrong,
    due,
    load_attempts,
    log_attempt,
    normalized_gain,
    render_progress,
    retention,
    unit_scores,
)

# ---- local helpers ---------------------------------------------------------

VARIANT = {"pre": "A", "post": "B", "d7": "C"}
DAY = {"pre": "2026-11-20", "post": "2026-11-20", "d7": "2026-11-27"}


def attempt(**over):
    """One valid Attempt; keyword arguments override fields."""
    base = dict(
        ts="2026-11-20T10:00:00+00:00", course="C", unit="u1", item_id="c1-B",
        variant="B", concept="c1", phase="post", score=1, confidence=2,
        citation="(01:00)", exposure="unknown",
    )
    base.update(over)
    return Attempt(**base)


def mk(unit, pre=(), post=(), d7=()):
    """Tracked attempts for one unit: the i-th score of a phase belongs to concept c<i>."""
    out = []
    for phase, scores in (("pre", pre), ("post", post), ("d7", d7)):
        for i, s in enumerate(scores, start=1):
            out.append(
                attempt(
                    ts=f"{DAY[phase]}T10:00:00+00:00", unit=unit,
                    item_id=f"c{i}-{VARIANT[phase]}", variant=VARIANT[phase],
                    concept=f"c{i}", phase=phase, score=s,
                )
            )
    return out


def mk_post(unit, day):
    """Five post attempts, all on `day`."""
    return [
        attempt(ts=f"{day.isoformat()}T10:00:00+00:00", unit=unit, item_id=f"c{i}-B", concept=f"c{i}")
        for i in range(1, 6)
    ]


def write_attempts(ws, attempts=None):
    """Log attempts into workspace `ws`; default: unit u1 with pre 0.2 / post 0.9 / d7 0.7."""
    if attempts is None:
        attempts = mk(unit="u1", pre=[0, 0, 1, 0, 0], post=[1, 1, 1, 0.5, 1], d7=[1, 0.5, 1, 0.5, 0.5])
    for a in attempts:
        log_attempt(a, ws)


def unit_dir(tmp_path):
    """A unit folder whose name differs from plan.unit, with plan.json and items.json.

    Course "C", unit "U1"; one tracked concept "c1" with variants A, B, C (ids "c1-A",
    "c1-B", "c1-C"); one practice item "p1" (variant None); every item has citation
    "(slide 2, 01:00)". The layout is the one load_plan and load_items read.
    """
    u = tmp_path / "课程 资料" / "第1周"
    u.mkdir(parents=True)
    plan = {
        "course": "C", "unit": "U1", "goal": "deep", "content_type": "concept",
        "note_language": "en", "lecture_language": "en", "duration_s": 180,
        "outputs": ["explanation", "pretest", "quiz", "cards", "map"], "sections": [],
        "concepts": [{"id": "c1", "name": "Concept one", "type": "definition", "citations": ["(slide 2, 01:00)"]}],
        "tracked": ["c1"], "output_target": "markdown",
    }

    def item(id, variant, kind):
        return {
            "id": id, "concept": "c1", "kind": kind, "prompt": f"Prompt {id}?", "answer": "A.",
            "rubric": "R.", "citation": "(slide 2, 01:00)", "difficulty": 2, "variant": variant,
        }

    items = {
        "tracked": {"c1": {v: item(f"c1-{v}", v, "apply") for v in "ABC"}},
        "practice": [item("p1", None, "recall")],
    }
    for name, obj in (("plan.json", plan), ("items.json", items)):
        (u / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return u


# ---- scores ----------------------------------------------------------------


def test_gain_and_retention():
    att = mk(unit="u1", pre=[0, 0, 1, 0, 0], post=[1, 1, 1, 0.5, 1], d7=[1, 0.5, 1, 0.5, 0.5])
    s = unit_scores(att)
    assert s["u1"] == {"pre": 0.2, "post": 0.9, "d7": 0.7}
    assert normalized_gain(s) == pytest.approx(0.875)
    assert retention(s) == pytest.approx(0.7 / 0.9)


def test_pre_perfect_excluded():
    assert normalized_gain({"u": {"pre": 1.0, "post": 1.0}}) is None


def test_practice_excluded_and_confident_but_wrong():
    p = attempt(item_id="p1", variant=None, phase="practice", score=0, confidence=3)
    att = mk(unit="u1", pre=[0, 1]) + [p]
    assert unit_scores(att) == {"u1": {"pre": 0.5}}
    assert confident_but_wrong(att) == [p]


# ---- due list --------------------------------------------------------------


def test_due_dates():
    att = mk_post(unit="u1", day=date(2026, 11, 20))
    d = due(att, date(2026, 11, 27))
    assert {(x["phase"], x["optional"]) for x in d} == {("d1", True), ("d7", False)}


def test_due_entry_keys_and_order():
    att = mk_post(unit="u1", day=date(2026, 11, 20))
    att.append(attempt(ts="2026-11-21T09:00:00+00:00", item_id="c1-D", variant="D", phase="d1"))
    assert due(att, date(2026, 12, 11)) == [
        {"unit": "u1", "phase": "d7", "due": "2026-11-27", "optional": False},
        {"unit": "u1", "phase": "d21", "due": "2026-12-11", "optional": True},
    ]
    assert due(att, date(2026, 11, 26)) == []


def test_due_uses_date_as_written_in_ts():
    att = [attempt(ts="2026-11-20T23:30:00-08:00")]
    assert [x["due"] for x in due(att, date(2026, 11, 21))] == ["2026-11-21"]


# ---- log -------------------------------------------------------------------


def test_log_rejects_bad_score(tmp_path):
    with pytest.raises(ValueError):
        log_attempt(attempt(score=0.7), tmp_path)
    assert not (tmp_path / "progress" / "C.jsonl").exists()


def test_log_round_trip_null_variant(tmp_path):
    a = attempt(item_id="p1", variant=None, phase="practice", score=0, confidence=3, citation="(第2页, 01:00)")
    p = log_attempt(a, tmp_path)
    assert p == tmp_path / "progress" / "C.jsonl"
    raw = p.read_text(encoding="utf-8")
    assert '"variant": null' in raw and "第2页" in raw and raw.endswith("\n")
    assert load_attempts("C", tmp_path) == [a]
    assert load_attempts("Other", tmp_path) == []


def test_log_round_trip_unicode_line_separators(tmp_path):
    # json.dumps(ensure_ascii=False) writes U+2028, U+2029 and U+0085 raw; they must not split a record.
    a = attempt(citation="a b c\x85d", concept="x y")
    log_attempt(a, tmp_path)
    log_attempt(attempt(), tmp_path)
    assert load_attempts("C", tmp_path) == [a, attempt()]


# ---- page ------------------------------------------------------------------


def test_render_headline(tmp_path):
    write_attempts(tmp_path)
    p = render_progress("C", tmp_path, date(2026, 11, 27))
    assert p.read_text(encoding="utf-8").splitlines()[2].startswith(
        "Across 1 units: pre 0.20 → post 0.90 → day 7 0.70"
    )


def test_render_page_content(tmp_path):
    write_attempts(tmp_path)
    log_attempt(attempt(item_id="p1", variant=None, phase="practice", score=0, confidence=3), tmp_path)
    p = render_progress("C", tmp_path, date(2026, 11, 27))
    assert p == tmp_path / "progress" / "C.md"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["# Progress — C", ""]
    assert lines[2] == "Across 1 units: pre 0.20 → post 0.90 → day 7 0.70; normalized gain 0.88; retention 0.78."
    assert "| unit | pre | post | d7 | gain | retention |" in lines
    assert "| u1 | 0.20 | 0.90 | 0.70 | 0.88 | 0.78 |" in lines
    assert "····○·········◆···●··  u1" in lines
    by_concept = lines[lines.index("## By concept"):lines.index("## Due today")]
    assert [x for x in by_concept if x.startswith(("○", "●", "◆", "·"))] == [
        "○···················◆  c1",
        "○·········◆·········●  c2",
        "····················◆  c3",
        "○·········◆··········  c4",
        "○·········◆·········●  c5",
    ]
    assert lines[lines.index("## Due today") + 2] == "- u1: d1 (optional), due 2026-11-21"
    assert lines[lines.index("## Confident but wrong") + 2] == "- u1: p1 (c1), practice, (01:00)"


def test_headline_omits_missing_parts(tmp_path):
    write_attempts(tmp_path, mk(unit="u1", pre=[0, 0, 1, 0, 0], post=[1, 1, 1, 0.5, 1]))
    lines = render_progress("C", tmp_path, date(2026, 11, 20)).read_text(encoding="utf-8").splitlines()
    assert lines[2] == "Across 1 units: pre 0.20 → post 0.90; normalized gain 0.88."
    assert "| u1 | 0.20 | 0.90 | — | 0.88 | — |" in lines
    assert lines[lines.index("## Due today") + 2] == "None."


def test_render_without_attempts(tmp_path):
    lines = render_progress("C", tmp_path, date(2026, 11, 20)).read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["# Progress — C", "", "No tracked attempts yet."]
    assert "## Units" not in lines and "## By concept" not in lines
    assert lines[lines.index("## Confident but wrong") + 2] == "None."


# ---- CLI -------------------------------------------------------------------


def test_cli_log_records_plan_names(tmp_path, capsys):
    u = unit_dir(tmp_path)
    ws = tmp_path / "ws"
    code = main([
        "progress", "log", "--unit", str(u), "--item", "c1-B", "--phase", "post",
        "--score", "0.5", "--confidence", "2", "--exposure", "watched", "--workspace", str(ws),
    ])
    assert code == 0
    (a,) = load_attempts("C", ws)
    assert (a.course, a.unit) == ("C", "U1") and u.name != a.unit
    assert (a.item_id, a.variant, a.concept, a.citation) == ("c1-B", "B", "c1", "(slide 2, 01:00)")
    assert (a.phase, a.score, a.confidence, a.exposure) == ("post", 0.5, 2, "watched")
    assert datetime.fromisoformat(a.ts).utcoffset() is not None
    assert json.loads(capsys.readouterr().out)["unit"] == "U1"


def test_cli_log_practice_item_has_null_variant(tmp_path):
    u = unit_dir(tmp_path)
    ws = tmp_path / "ws"
    code = main([
        "progress", "log", "--unit", str(u), "--item", "p1", "--phase", "practice",
        "--score", "0", "--confidence", "3", "--workspace", str(ws),
    ])
    assert code == 0
    (a,) = load_attempts("C", ws)
    assert a.variant is None and a.exposure == "unknown" and a.score == 0


def test_cli_log_unknown_item_exits_2(tmp_path, capsys):
    u = unit_dir(tmp_path)
    ws = tmp_path / "ws"
    code = main([
        "progress", "log", "--unit", str(u), "--item", "nope", "--phase", "post",
        "--score", "1", "--confidence", "2", "--workspace", str(ws),
    ])
    assert code == 2
    assert "nope" in capsys.readouterr().err
    assert load_attempts("C", ws) == []


def test_cli_log_takes_no_course(tmp_path):
    u = unit_dir(tmp_path)
    with pytest.raises(SystemExit) as e:
        main([
            "progress", "log", "--course", "C", "--unit", str(u), "--item", "c1-B",
            "--phase", "post", "--score", "1", "--confidence", "2", "--workspace", str(tmp_path / "ws"),
        ])
    assert e.value.code == 2


def test_cli_due_prints_json(tmp_path, capsys):
    write_attempts(tmp_path, mk_post(unit="u1", day=date(2026, 11, 20)))
    code = main(["progress", "due", "--course", "C", "--date", "2026-11-27", "--workspace", str(tmp_path)])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == [
        {"unit": "u1", "phase": "d1", "due": "2026-11-21", "optional": True},
        {"unit": "u1", "phase": "d7", "due": "2026-11-27", "optional": False},
    ]


def test_cli_workspace_defaults_to_profile(tmp_cfg, tmp_path, capsys):
    ws = tmp_path / "my ws"
    set_value("workspace", str(ws))
    write_attempts(ws, mk_post(unit="u1", day=date(2026, 11, 20)))
    assert main(["progress", "due", "--course", "C", "--date", "2026-11-27"]) == 0
    assert [x["phase"] for x in json.loads(capsys.readouterr().out)] == ["d1", "d7"]


def test_cli_render_writes_page(tmp_path, capsys):
    write_attempts(tmp_path)
    assert main(["progress", "render", "--course", "C", "--workspace", str(tmp_path)]) == 0
    page = tmp_path / "progress" / "C.md"
    assert page.read_text(encoding="utf-8").splitlines()[0] == "# Progress — C"
    assert capsys.readouterr().out.strip() == str(page)


# ---- unsafe names and malformed files (Task 21) -----------------------------


def test_progress_refuses_unsafe_course(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(PlanError):
        log_attempt(attempt(course="../x"), ws)
    with pytest.raises(PlanError):
        render_progress("../x", ws, date(2026, 11, 20))
    with pytest.raises(PlanError):
        load_attempts("../x", ws)
    outside = [p for p in tmp_path.rglob("*") if p != ws and ws / "progress" not in (p, *p.parents)]
    assert outside == []


def test_cli_progress_log_malformed_items_is_one_line(tmp_path, capsys):
    u = unit_dir(tmp_path)
    (u / "items.json").write_text("{", encoding="utf-8", newline="\n")
    ws = tmp_path / "ws"
    code = main([
        "progress", "log", "--unit", str(u), "--item", "c1-B", "--phase", "post",
        "--score", "1", "--confidence", "2", "--workspace", str(ws),
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("\n") and captured.err.count("\n") == 1
    assert captured.err.startswith("items.json:")
    assert not ws.exists()


@pytest.mark.parametrize("field, value", [("score", True), ("confidence", True), ("confidence", 2.0)])
def test_log_rejects_bool_and_float_values(tmp_path, field, value):
    with pytest.raises(ValueError):
        log_attempt(attempt(**{field: value}), tmp_path)
    assert not (tmp_path / "progress" / "C.jsonl").exists()



# ---- rules that had no test (Task 21) ---------------------------------------


@pytest.mark.parametrize("field, value", [("phase", "d3"), ("confidence", 4), ("exposure", "seen")])
def test_log_rejects_bad_phase_confidence_exposure(tmp_path, field, value):
    with pytest.raises(ValueError):
        log_attempt(attempt(**{field: value}), tmp_path)
    assert not (tmp_path / "progress" / "C.jsonl").exists()


def test_table_escapes_pipe_in_unit_name(tmp_path):
    write_attempts(tmp_path, mk(unit="a|b", pre=[0], post=[1]))
    lines = render_progress("C", tmp_path, date(2026, 11, 20)).read_text(encoding="utf-8").splitlines()
    assert "| a\\|b | 0.00 | 1.00 | — | 1.00 | — |" in lines


def test_cli_bare_progress_is_usage():
    with pytest.raises(SystemExit) as e:
        main(["progress"])
    assert e.value.code == 2


RENDERED_PAGE = """# Progress — C

Across 1 units: pre 0.00 → post 1.00; normalized gain 1.00.

## Units

| unit | pre | post | d7 | gain | retention |
|---|---|---|---|---|---|
| u1 | 0.00 | 1.00 | — | 1.00 | — |

Each strip runs from 0 to 100 in 21 columns: ○ pre, ● post, ◆ day 7.

```text
○···················●  u1
```

## By concept

### u1

```text
○···················●  c1
```

## Due today

- u1: d1 (optional), due 2026-11-21

## Confident but wrong

- u1: p1 (c1), practice, (0:30)
"""


def test_rendered_page_layout(tmp_path):
    write_attempts(tmp_path, [
        attempt(item_id="c1-A", variant="A", phase="pre", score=0),
        attempt(item_id="c1-B", variant="B", phase="post", score=1, confidence=3),
        attempt(item_id="p1", variant=None, phase="practice", score=0, confidence=3, citation="(0:30)"),
    ])
    page = render_progress("C", tmp_path, date(2026, 11, 21))
    assert page.read_text(encoding="utf-8") == RENDERED_PAGE
