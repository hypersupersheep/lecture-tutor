import dataclasses
import json

import pytest
from conftest import names_by_status, status_of

from tutor_any_lecture.cli import main
from tutor_any_lecture.items import (
    Item, assign_variants, find_item, load_items, next_items, validate_items,
)
from tutor_any_lecture.plan import Plan
from tutor_any_lecture.unit import UnitPaths

CHECKS = ["variants", "apply_share", "citation", "prompt_overlap",
          "tracked_leak", "tracked_vs_practice", "pretest_complete"]

# (concept, letter) -> (kind, prompt, answer). No prompt has an inner . ! or ?
TRACKED = {
    ("c1", "A"): ("recall", "What does it mean for interest to compound?",
                  "Interest is added to the balance and then earns interest itself"),
    ("c1", "B"): ("apply", "A deposit of 100 earns 10% a year compounded yearly, so what is the balance after two years?",
                  "121"),
    ("c1", "C"): ("transfer", "Why would a borrower pay more under monthly compounding than under yearly compounding at the same nominal rate?",
                  "Interest is charged on interest more often"),
    ("c2", "A"): ("recall", "How is the one-period discount factor defined?",
                  "One divided by one plus the rate"),
    ("c2", "B"): ("apply", "At a rate of 5% a year, what is 210 due in one year worth today?",
                  "200"),
    ("c2", "C"): ("transfer", "How should a firm compare two payments that arrive in different years?",
                  "Discount both to today and compare present values"),
    ("c3", "A"): ("recall", "What is an annuity?",
                  "A fixed number of equal payments at regular intervals"),
    ("c3", "B"): ("apply", "Three payments of 50 arrive at the end of each year and the rate is zero, so what are they worth today?",
                  "150"),
    ("c3", "C"): ("transfer", "Why might a prize winner choose a lump sum over yearly instalments with the same total?",
                  "Money now is worth more than the same money later"),
    ("c4", "A"): ("recall", "Which formula turns a nominal rate with m periods into an effective annual rate?",
                  "(1 + r/m)^m - 1"),
    ("c4", "B"): ("apply", "A card charges 1% per month, so what is its effective annual rate to the nearest tenth of a percent?",
                  "About 12 point 7 percent"),
    ("c4", "C"): ("transfer", "Two banks quote different compounding schedules, so how can a saver tell which offer is better?",
                  "Convert both offers to effective annual rates"),
    ("c5", "A"): ("recall", "What limit defines continuous compounding?",
                  "The limit of (1 + r/m)^m as m grows without bound"),
    ("c5", "B"): ("apply", "With continuous compounding at 3% a year, what does 200 grow to in four years?",
                  "200 times e to the 0 point 12, about 225 point 5"),
    ("c5", "C"): ("transfer", "When might a model treat interest as accruing every instant instead of each month?",
                  "When periods are very short or the maths is simpler in continuous time"),
}
PRACTICE = [
    ("p1", "c1", "apply", "A balance doubles in eight years; roughly what yearly rate does that imply?",
     "About nine percent, by the rule of 72"),
    ("p2", "c3", "which_method", "Which tool values a level stream of payments most quickly?",
     "The annuity formula"),
]


def item(id, concept, kind, prompt, answer, variant):
    """Local helper: one Item; the citation names the concept's slide."""
    return Item(id=id, concept=concept, kind=kind, prompt=prompt, answer=answer,
                rubric="Full marks for the key idea", citation=f"(slide {concept[1:]})",
                difficulty=2, variant=variant)


def bank(tracked=TRACKED, practice=PRACTICE):
    """Local helper: a load_items-shaped dict built from the tables above."""
    out = {"tracked": {}, "practice": []}
    for (cid, letter), (kind, prompt, answer) in tracked.items():
        out["tracked"].setdefault(cid, {})[letter] = item(f"{cid}-{letter}", cid, kind, prompt, answer, letter)
    out["practice"] = [item(id, cid, kind, prompt, answer, None) for id, cid, kind, prompt, answer in practice]
    return out


def plan(concepts, lang):
    """Local helper: a Plan whose concepts are all tracked."""
    return Plan(course="C", unit="U1", goal="deep", content_type="concept", note_language=lang,
                lecture_language=lang, duration_s=180.0,
                outputs=["explanation", "pretest", "quiz", "cards", "map"], sections=[],
                concepts=[{"id": c, "name": c, "type": "definition", "citations": ["(slide 1)"]} for c in concepts],
                tracked=list(concepts), output_target="markdown")


ITEMS = bank()
# 8 of 17 items in APPLY_KINDS: the C variants of c2 to c5 become recall
ITEMS_MOSTLY_RECALL = bank(tracked={**TRACKED, **{(c, "C"): ("recall",) + TRACKED[(c, "C")][1:]
                                                  for c in ("c2", "c3", "c4", "c5")}})
# c2-A reworded from the prose sentence "A discount factor converts a future amount into its value today"
ITEMS_COPYING_NOTE = bank(tracked={**TRACKED, ("c2", "A"): (
    "recall", "A discount factor converts a future amount into what?", "Its value today")})
PLAN = plan(["c1", "c2", "c3", "c4", "c5"], "en")

NOTE = """# Compound interest

## Growth of a deposit

Interest compounds when each period's interest joins the balance and starts to earn interest of its own (slide 1, 0:20). Over two years at ten percent, a deposit gains twenty-one percent rather than twenty (slide 1, 0:45).

## Discounting

A discount factor converts a future amount into its value today (slide 2, 1:05). At five percent, one unit due next year is worth about 95 cents now (slide 2, 1:30).

## Annuities

A level stream of payments made at regular dates is called an annuity (slide 3, 2:00). Its value is the sum of the discounted payments (slide 3, 2:20).

## Effective rates

The effective annual rate states the yearly growth once compounding within the year is counted (slide 4, 2:40). Monthly charges of one percent add up to more than twelve percent over a year (slide 4, 3:00).

## Continuous compounding

Letting the number of periods grow without bound gives continuous compounding, with growth factor e to the power rt (slide 5, 3:20).

<!-- tal:check -->
1. A balance doubles in eight years; roughly what yearly rate does that imply?
<details><summary>Answer</summary>About nine percent, by the rule of 72</details>
2. Which tool values a level stream of payments most quickly?
<details><summary>Answer</summary>The annuity formula</details>
<!-- /tal:check -->
"""

ZH_PLAN = plan(["c1"], "zh")
ZH_NOTE = "## 复利\n\n本金每一期都把利息并入下一期的本金(slide 1, 0:20)。利率越高,复利的效果越明显(slide 1, 0:40)。\n"
ZH_ITEMS_COPYING = bank(
    tracked={("c1", "A"): ("recall", "本金每一期都把利息并入下一期的本金吗？", "是"),
             ("c1", "B"): ("apply", "存入100元,年利率10%,按年复利,两年后余额是多少？", "121元"),
             ("c1", "C"): ("transfer", "为什么按月计息的贷款比按年计息的贷款更贵？", "利滚利的次数更多")},
    practice=[])


def pre_items(items, assignment):
    """Local helper: the pre variant of each assigned concept, in sorted concept-id order."""
    return [items["tracked"][cid][a["pre"]] for cid, a in sorted(assignment["concepts"].items())]


def with_pretest(md, printed):
    """Local helper: md with a pretest section printing these items first."""
    rows = "".join(f"{n}. {it.prompt}\n<details><summary>Answer</summary>{it.answer}</details>\n"
                   for n, it in enumerate(printed, 1))
    return f"<!-- tal:pretest -->\n{rows}<!-- /tal:pretest -->\n\n{md}"


def items_to_json(items):
    """Local helper: the on-disk form of a load_items-shaped dict."""
    return {"tracked": {cid: {letter: dataclasses.asdict(it) for letter, it in v.items()}
                        for cid, v in items["tracked"].items()},
            "practice": [dataclasses.asdict(it) for it in items["practice"]]}


def write_json(path, obj):
    """Local helper."""
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def unit_with_items(tmp_path, items=ITEMS, note=NOTE):
    """Local helper: a unit folder (name differs from plan.unit) with plan.json, items.json, explanation.md."""
    u = tmp_path / "课程 资料" / "第1周"
    u.mkdir(parents=True)
    p = UnitPaths(u)
    write_json(p.plan, dataclasses.asdict(PLAN))
    write_json(p.items, items_to_json(items))
    p.explanation.write_text(note, encoding="utf-8", newline="\n")
    return u


def test_assignment_deterministic():
    a = assign_variants(ITEMS, "C|U1")
    b = assign_variants(ITEMS, "C|U1")
    assert a == b and set(a["concepts"]["c1"].values()) == {"A", "B", "C"}


def test_apply_share_below_half_fails():
    assert status_of(validate_items(ITEMS_MOSTLY_RECALL, PLAN, NOTE, "en"), "apply_share") == "FAIL"


def test_prompt_copied_from_note_fails():
    assert status_of(validate_items(ITEMS_COPYING_NOTE, PLAN, NOTE, "en"), "prompt_overlap") == "FAIL"


def test_cjk_overlap_uses_char_ngrams():
    assert status_of(validate_items(ZH_ITEMS_COPYING, ZH_PLAN, ZH_NOTE, "zh"), "prompt_overlap") == "FAIL"


def test_d1_without_variant_reports_missing():
    assert next_items(ITEMS, assign_variants(ITEMS, "s"), "d1") == []


def test_assign_reuses_existing_file(tmp_path):
    u = unit_with_items(tmp_path)
    path = UnitPaths(u).assignment
    assert main(["items", "assign", "--unit", str(u)]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["seed"] == "C|U1"
    edited = json.loads(path.read_text(encoding="utf-8"))
    edited["seed"] = "edited"
    write_json(path, edited)
    first = path.read_text(encoding="utf-8")
    assert main(["items", "assign", "--unit", str(u)]) == 0
    assert path.read_text(encoding="utf-8") == first
    assert main(["items", "assign", "--unit", str(u), "--force"]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["seed"] == "C|U1"


def test_clean_bank_passes():
    a = assign_variants(ITEMS, "C|U1")
    r = validate_items(ITEMS, PLAN, with_pretest(NOTE, pre_items(ITEMS, a)), "en", a)
    assert [x.name for x in r] == CHECKS
    assert names_by_status(r) == {"PASS": set(CHECKS)}
    r = validate_items(ITEMS, PLAN, NOTE, "en")
    assert names_by_status(r) == {"PASS": set(CHECKS)}
    assert [x.details for x in r if x.name == "pretest_complete"] == [["skipped: no assignment"]]
    assert [x.details for x in r if x.name == "tracked_leak"] == [["skipped: pretest part, no assignment"]]


def test_tracked_prompt_reused_as_practice_fails():
    reused = PRACTICE + [("p3", "c2", "transfer", TRACKED[("c2", "C")][1], "Discount both to today")]
    assert status_of(validate_items(bank(practice=reused), PLAN, NOTE, "en"), "tracked_vs_practice") == "FAIL"


def test_tracked_prompt_in_check_section_leaks():
    leak = NOTE + ("\n<!-- tal:check -->\n1. " + TRACKED[("c1", "B")][1]
                   + "\n<details><summary>Answer</summary>121</details>\n<!-- /tal:check -->\n")
    assert status_of(validate_items(ITEMS, PLAN, leak, "en"), "tracked_leak") == "FAIL"


def test_non_pre_variant_in_pretest_leaks():
    a = assign_variants(ITEMS, "C|U1")
    printed = pre_items(ITEMS, a)
    printed[0] = ITEMS["tracked"]["c1"][a["concepts"]["c1"]["post"]]
    md = with_pretest(NOTE, printed)
    assert status_of(validate_items(ITEMS, PLAN, md, "en", a), "tracked_leak") == "FAIL"
    assert status_of(validate_items(ITEMS, PLAN, md, "en"), "tracked_leak") == "PASS"


def test_pretest_missing_pre_prompt_warns():
    a = assign_variants(ITEMS, "C|U1")
    r = validate_items(ITEMS, PLAN, with_pretest(NOTE, pre_items(ITEMS, a)[1:]), "en", a)
    assert status_of(r, "pretest_complete") == "WARN"
    assert status_of(r, "tracked_leak") == "PASS"


def test_find_item_and_get(tmp_path, capsys):
    assert find_item(ITEMS, "c2-B").variant == "B"
    assert find_item(ITEMS, "p1").variant is None
    with pytest.raises(KeyError):
        find_item(ITEMS, "nope")
    u = unit_with_items(tmp_path)
    assert load_items(UnitPaths(u).items) == ITEMS
    assert main(["items", "get", "--unit", str(u), "--id", "p1"]) == 0
    assert json.loads(capsys.readouterr().out) == dataclasses.asdict(ITEMS["practice"][0])
    assert main(["items", "get", "--unit", str(u), "--id", "nope"]) == 2


def test_items_next_prints_phase_items_missing(tmp_path, capsys):
    with_d = dict(TRACKED)
    with_d[("c1", "D")] = ("recall", "In your own words, how does compounding change growth over time?", "It speeds it up")
    u = unit_with_items(tmp_path, items=bank(tracked=with_d))
    assert main(["items", "assign", "--unit", str(u)]) == 0
    capsys.readouterr()
    assert main(["items", "next", "--unit", str(u), "--phase", "d1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["phase"] == "d1" and [i["id"] for i in out["items"]] == ["c1-D"]
    assert out["missing"] == ["c2", "c3", "c4", "c5"]
    assert main(["items", "next", "--unit", str(u), "--phase", "pre"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [i["concept"] for i in out["items"]] == ["c1", "c2", "c3", "c4", "c5"] and out["missing"] == []


def test_malformed_assignment_structure_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="concepts"):
        validate_items(ITEMS, PLAN, NOTE, "en", {"seed": "s"})
    with pytest.raises(ValueError, match="post"):
        next_items(ITEMS, {"seed": "s", "concepts": {"c1": {"pre": "A"}}}, "post")
    u = unit_with_items(tmp_path)
    write_json(UnitPaths(u).assignment, {"seed": "s"})
    assert main(["items", "validate", "--unit", str(u)]) == 1
    assert main(["items", "next", "--unit", str(u), "--phase", "pre"]) == 1
    assert main(["items", "assign", "--unit", str(u)]) == 1


def test_validate_cli_exit_codes(tmp_path):
    u = unit_with_items(tmp_path)
    assert main(["items", "validate", "--unit", str(u)]) == 0
    write_json(UnitPaths(u).items, items_to_json(ITEMS_COPYING_NOTE))
    assert main(["items", "validate", "--unit", str(u)]) == 1


# ---- field types and unreadable files (Task 21) -----------------------------


def one_line_error(capsys):
    """Local helper: the captured stderr, asserting it is exactly one line and stdout is empty."""
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith("\n") and captured.err.count("\n") == 1
    return captured.err


def items_json_with(field, value):
    """Local helper: the on-disk ITEMS with one field of tracked item c1-A replaced."""
    obj = items_to_json(ITEMS)
    obj["tracked"]["c1"]["A"][field] = value
    return obj


def test_load_items_rejects_null_citation(tmp_path):
    path = tmp_path / "items.json"
    write_json(path, items_json_with("citation", None))
    with pytest.raises(ValueError) as e:
        load_items(path)
    assert str(e.value).endswith("citation must be a string")


def test_load_items_rejects_non_string_prompt(tmp_path):
    path = tmp_path / "items.json"
    write_json(path, items_json_with("prompt", 5))
    with pytest.raises(ValueError):
        load_items(path)


def test_cli_items_validate_bad_types_is_one_line(tmp_path, capsys):
    u = unit_with_items(tmp_path)
    write_json(UnitPaths(u).items, items_json_with("citation", None))
    assert main(["items", "validate", "--unit", str(u)]) == 1
    assert one_line_error(capsys).startswith("items.json:")


def test_cli_items_not_utf8_is_one_line(tmp_path, capsys):
    u = unit_with_items(tmp_path)
    UnitPaths(u).items.write_bytes(b"\xff\xfe")
    assert main(["items", "validate", "--unit", str(u)]) == 1
    assert one_line_error(capsys).startswith("items.json")


def test_cli_assignment_not_utf8_is_one_line(tmp_path, capsys):
    u = unit_with_items(tmp_path)
    UnitPaths(u).assignment.write_bytes(b"\xff\xfe")
    assert main(["items", "next", "--unit", str(u), "--phase", "pre"]) == 1
    assert one_line_error(capsys).startswith("assignment.json")



# ---- rules that had no test (Task 21) ---------------------------------------


def _bad_kind(obj):
    obj["tracked"]["c1"]["A"]["kind"] = "essay"


def _wrong_keys(obj):
    del obj["practice"][0]["rubric"]


def _letter_f(obj):
    obj["tracked"]["c1"]["F"] = dict(obj["tracked"]["c1"]["A"], id="c1-F", variant="F")


def _other_concept(obj):
    obj["tracked"]["c1"]["A"]["concept"] = "c2"


def _practice_variant(obj):
    obj["practice"][0]["variant"] = "A"


def _duplicate_id(obj):
    obj["practice"][1]["id"] = "p1"


@pytest.mark.parametrize(
    "fault",
    [_bad_kind, _wrong_keys, _letter_f, _other_concept, _practice_variant, _duplicate_id],
    ids=["bad-kind", "wrong-keys", "letter-outside-A-E", "variant-of-other-concept",
         "practice-variant-not-null", "duplicate-id"],
)
def test_load_items_structural_faults(tmp_path, fault):
    obj = items_to_json(ITEMS)
    fault(obj)
    path = tmp_path / "items.json"
    write_json(path, obj)
    with pytest.raises(ValueError):
        load_items(path)
