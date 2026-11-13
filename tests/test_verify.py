import json
import shutil

from conftest import fx
from tutor_any_lecture.cli import main
from tutor_any_lecture.unit import UnitPaths
from tutor_any_lecture.verify import run_verify

CHECK_NAMES = ["citations", "coverage", "terms", "numbers", "structure",
               "items", "cards", "map", "banned_phrases"]


# ---------------------------------------------------------------- local helpers


def copy_fixture(name, tmp_path):
    """A copy of a fixture unit; tests never run verify on the committed folders."""
    dst = tmp_path / name
    shutil.copytree(fx("units", name), dst)
    return dst


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def drop_duration(u):
    paths = UnitPaths(u)
    plan = _read_json(paths.plan)
    plan["duration_s"] = None
    _write_json(paths.plan, plan)
    source = _read_json(paths.source)
    source["duration"] = None
    _write_json(paths.source, source)


def append_to_note(u, text):
    path = UnitPaths(u).explanation
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")


def set_outputs(u, outputs):
    path = UnitPaths(u).plan
    plan = _read_json(path)
    plan["outputs"] = outputs
    _write_json(path, plan)


def entry(r, name):
    return next(c for c in r["checks"] if c["name"] == name)


# ---------------------------------------------------------------- tests


def test_ok_unit_passes(tmp_path):
    r = run_verify(copy_fixture("ok", tmp_path))
    assert r["overall"] == "PASS" and r["report"] == "Automated checks passed; not visually reviewed."


def test_bad_unit_fails_named_checks(tmp_path):
    r = run_verify(copy_fixture("bad", tmp_path))
    assert r["overall"] == "FAIL"
    assert {"citations", "coverage", "items"} <= {c["name"] for c in r["checks"] if c["status"] == "FAIL"}
    assert r["report"] == "Automated checks failed."


def test_cli_exit_codes(tmp_path):
    assert main(["verify", "--unit", str(copy_fixture("bad", tmp_path))]) == 1


def test_cli_json_and_pass_exit(tmp_path, capsys):
    code = main(["verify", "--unit", str(copy_fixture("ok", tmp_path)), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.endswith("\n") and out.count("\n") == 1
    r = json.loads(out)
    assert r["overall"] == "PASS" and [c["name"] for c in r["checks"]] == CHECK_NAMES


def test_unknown_duration_degrades(tmp_path):
    u = copy_fixture("ok", tmp_path)
    drop_duration(u)
    r = run_verify(u)
    assert r["overall"] == "PASS"
    assert next(c for c in r["checks"] if c["name"] == "citations")["status"] == "WARN"


def test_slides_only_unit_passes(tmp_path):
    r = run_verify(copy_fixture("slides_only", tmp_path))
    assert r["overall"] == "PASS"


def test_slides_only_time_citation_fails(tmp_path):
    u = copy_fixture("slides_only", tmp_path)
    append_to_note(u, "\n\nThe balance is updated once a month (0:30).\n")
    assert entry(run_verify(u), "citations")["status"] == "FAIL"


def test_code_is_not_a_citation(tmp_path):
    u = copy_fixture("slides_only", tmp_path)
    append_to_note(u, "\n\nCall `rev(1:20)` to reverse a vector.\n\n```r\ntotal <- sum(1:10)\n```\n")
    assert entry(run_verify(u), "citations")["status"] == "PASS"


def test_missing_transcript_fails(tmp_path):
    u = copy_fixture("ok", tmp_path)
    UnitPaths(u).transcript.unlink()
    c = entry(run_verify(u), "citations")
    assert c["status"] == "FAIL" and "sources/transcript.json missing" in c["details"]


def test_nine_checks_in_order(tmp_path):
    u = copy_fixture("bad", tmp_path)
    r = run_verify(u)
    assert [c["name"] for c in r["checks"]] == CHECK_NAMES
    assert r["warnings"] == sum(c["status"] == "WARN" for c in r["checks"])
    assert json.loads(UnitPaths(u).verify.read_text(encoding="utf-8")) == r


def test_structure_folds_sub_results(tmp_path):
    u = copy_fixture("ok", tmp_path)
    append_to_note(u, "\n\n#### Too deep\n\nA short paragraph (slide 1).\n")
    c = entry(run_verify(u), "structure")
    assert c["status"] == "FAIL" and any(d.startswith("h4: ") for d in c["details"])


def test_outputs_skip_checks(tmp_path):
    u = copy_fixture("ok", tmp_path)
    set_outputs(u, ["explanation"])
    paths = UnitPaths(u)
    for f in (paths.items, paths.assignment, paths.cards_json, paths.map):
        f.unlink()
    r = run_verify(u)
    assert r["overall"] == "PASS"
    for name in ("items", "cards", "map"):
        assert entry(r, name) == {"name": name, "status": "PASS", "details": ["skipped: not in plan.outputs"]}


def test_listed_output_missing_file_fails(tmp_path):
    u = copy_fixture("ok", tmp_path)
    paths = UnitPaths(u)
    for f in (paths.items, paths.cards_json, paths.map):
        f.unlink()
    r = run_verify(u)
    assert {"items", "cards", "map"} <= {c["name"] for c in r["checks"] if c["status"] == "FAIL"}


def test_inline_math_is_not_currency(tmp_path):
    u = copy_fixture("ok", tmp_path)
    before = entry(run_verify(u), "numbers")
    append_to_note(u, "\n\nThe count doubles at each step, $2^n$ in total (slide 1).\n")
    assert entry(run_verify(u), "numbers") == before


def test_terms_numbers_and_banned_phrases_warn(tmp_path):
    u = copy_fixture("ok", tmp_path)
    append_to_note(u, "\n\nIn practice the Monte Carlo run took 3 days, a tapestry of GBM output (slide 1).\n")
    r = run_verify(u)
    assert r["overall"] == "PASS"
    assert entry(r, "terms") == {"name": "terms", "status": "WARN", "details": [
        "not in the transcript or slides: Monte Carlo", "not in the transcript or slides: GBM"]}
    assert entry(r, "numbers") == {"name": "numbers", "status": "WARN", "details": [
        "in the note, not in the sources: 3days"]}
    assert entry(r, "banned_phrases") == {"name": "banned_phrases", "status": "WARN", "details": [
        "banned phrase: tapestry"]}


def test_malformed_files_fail_their_checks(tmp_path):
    u = copy_fixture("ok", tmp_path)
    paths = UnitPaths(u)
    paths.map.write_text("{", encoding="utf-8", newline="\n")
    paths.cards_json.write_text('{"id": "card-1"}\n', encoding="utf-8", newline="\n")
    paths.assignment.write_text("not json\n", encoding="utf-8", newline="\n")
    r = run_verify(u)
    for name, file_name in (("items", "assignment.json"), ("cards", "cards.json"), ("map", "map.json")):
        c = entry(r, name)
        assert c["status"] == "FAIL" and len(c["details"]) == 1 and c["details"][0].startswith(file_name + ": ")


def test_cli_table_ends_with_report(tmp_path, capsys):
    code = main(["verify", "--unit", str(copy_fixture("bad", tmp_path))])
    lines = capsys.readouterr().out.splitlines()
    assert code == 1
    assert lines[0] == "FAIL  citations" and "      slide 9 > 3" in lines
    assert lines[-1] == "Automated checks failed."



def five_slide_unit(tmp_path, not_covered):
    """Local helper: the ok unit with slides 4 and 5 added and this not-covered line."""
    u = copy_fixture("ok", tmp_path)
    pages_path = UnitPaths(u).pages
    pages = _read_json(pages_path)
    pages += [{"n": n, "label": str(n), "text": f"Extra slide {n}", "image": None} for n in (4, 5)]
    _write_json(pages_path, pages)
    path = UnitPaths(u).explanation
    md = path.read_text(encoding="utf-8")
    assert "- slide 3\n" in md
    path.write_text(md.replace("- slide 3\n", not_covered), encoding="utf-8", newline="\n")
    return u


def test_not_covered_accepts_ranges(tmp_path):
    assert entry(run_verify(five_slide_unit(tmp_path / "a", "- slides 3–5\n")), "coverage") == {
        "name": "coverage", "status": "PASS", "details": []}
    assert entry(run_verify(five_slide_unit(tmp_path / "b", "- slide 3, slides 4-5\n")), "coverage")[
        "status"] == "PASS"
    assert entry(run_verify(five_slide_unit(tmp_path / "c", "")), "coverage") == {
        "name": "coverage", "status": "FAIL", "details": [
            f"slide {n} is neither cited nor listed in the not-covered section" for n in (3, 4, 5)]}



def test_coverage_expands_slide_ranges(tmp_path):
    def unit(name, extra):
        u = copy_fixture("ok", tmp_path / name)
        path = UnitPaths(u).explanation
        md = path.read_text(encoding="utf-8").replace("- slide 3\n", "")
        path.write_text(md + extra, encoding="utf-8", newline="\n")
        return u

    assert entry(run_verify(unit("bare", "")), "coverage")["details"] == [
        "slide 3 is neither cited nor listed in the not-covered section"]
    cited = unit("cited", "\nThe limit case is continuous compounding (slides 2–3).\n")
    assert entry(run_verify(cited), "coverage") == {"name": "coverage", "status": "PASS", "details": []}


def test_escaped_dollar_is_currency(tmp_path):
    u = copy_fixture("ok", tmp_path)
    # Unescaped, "$5 a month, or $" would read as inline math and vanish.
    append_to_note(u, "\n\nThe fee is \\$5 a month, or \\$x for the year (slide 1).\n")
    assert "in the note, not in the sources: $5" in entry(run_verify(u), "numbers")["details"]


# ---------------------------------------------------------------- quote_source (Task 23)


def quote_source_details(r):
    """Local helper: the quote_source details folded into the citations entry, prefix removed."""
    return [d[len("quote_source: "):] for d in entry(r, "citations")["details"] if d.startswith("quote_source: ")]


def add_segment(u, start, end, text):
    """Local helper: append one segment to the unit's transcript.json."""
    path = UnitPaths(u).transcript
    data = _read_json(path)
    data["segments"].append({"start": start, "end": end, "text": text})
    _write_json(path, data)


def test_invented_blockquote_fails_quote_source(tmp_path):
    u = copy_fixture("ok", tmp_path)
    append_to_note(u, "\n\n> The bank pays a bonus rate to every customer who never withdraws. (slide 1, 1:15)\n")
    c = entry(run_verify(u), "citations")
    assert c["status"] == "FAIL"
    assert quote_source_details(run_verify(u)) == [
        "quote 'The bank pays a bonus rate to every cust…' cited (slide 1, 1:15) "
        "is not in the transcript or the slides"
    ]


def test_invented_inline_quote_fails_quote_source(tmp_path):
    u = copy_fixture("ok", tmp_path)
    append_to_note(u, '\n\nThe lecturer warned that "banks always round the rate down" (slide 2, 2:40).\n')
    r = run_verify(u)
    assert entry(r, "citations")["status"] == "FAIL"
    assert quote_source_details(r) == [
        "quote 'banks always round the rate down' cited (slide 2, 2:40) is not in the transcript or the slides"
    ]


def test_quote_far_from_cited_time_warns(tmp_path):
    u = copy_fixture("ok", tmp_path)
    add_segment(u, 600.0, 630.0, "Some banks print the effective annual rate next to every advertised APR.")
    append_to_note(u, '\n\nAs the lecturer put it, "some banks print the effective annual rate" (0:30).\n')
    r = run_verify(u)
    assert entry(r, "citations")["status"] == "WARN"
    assert quote_source_details(r) == [
        "quote 'some banks print the effective annual ra…' is not at (0:30); found at 10:00"
    ]


def test_quote_on_another_slide_warns(tmp_path):
    u = copy_fixture("ok", tmp_path)
    append_to_note(u, '\n\nThe deck ends on "Continuous compounding: the limit as the period shrinks to zero" (slide 1).\n')
    r = run_verify(u)
    assert entry(r, "citations")["status"] == "WARN"
    assert quote_source_details(r) == [
        "quote 'Continuous compounding: the limit as the…' is not at (slide 1); found on slide 3"
    ]


def test_quote_with_ellipsis_and_brackets_passes(tmp_path):
    u = copy_fixture("ok", tmp_path)
    add_segment(u, 178.0, 180.0, "Remember: the balance on your statement already has interest included.")
    append_to_note(
        u,
        '\n\nThe statement shows "the balance … [that is] interest included" (2:59).\n\n'
        "> With compound interest … the interest you earned [it is] added to the balance (1:15)\n",
    )
    r = run_verify(u)
    assert entry(r, "citations") == {"name": "citations", "status": "PASS", "details": []}


def test_quote_punctuation_and_case_do_not_matter(tmp_path):
    u = copy_fixture("ok", tmp_path)
    append_to_note(
        u,
        "\n\n> WITH COMPOUND INTEREST — the interest you earned is added to the balance; "
        "and next period, it earns interest too! (1:15)\n\n"
        "The slide reads “Simple — interest on the DEPOSIT only.” (slide 1).\n",
    )
    r = run_verify(u)
    assert entry(r, "citations") == {"name": "citations", "status": "PASS", "details": []}


def test_cjk_quote_ignores_spaces(tmp_path):
    u = copy_fixture("ok", tmp_path)
    add_segment(u, 170.0, 178.0, "复利 就是 利息 也会 生出 利息。")
    append_to_note(u, "\n\n> 复利就是利息也会生出利息 (2:55)\n")
    assert quote_source_details(run_verify(u)) == []
    append_to_note(u, "\n\n> 单利就是本金永远不会变多 (2:55)\n")
    assert quote_source_details(run_verify(u)) == [
        "quote '单利就是本金永远不会变多' cited (2:55) is not in the transcript or the slides"
    ]


def test_time_only_quote_without_transcript_has_no_quote_source(tmp_path):
    u = copy_fixture("slides_only", tmp_path)
    append_to_note(u, "\n\n> The balance is updated once a month by the bank. (0:30)\n")
    c = entry(run_verify(u), "citations")
    assert c["status"] == "FAIL" and quote_source_details(run_verify(u)) == []


def test_bundled_sample_passes_quote_source(tmp_path):
    from tutor_any_lecture.selftest import run_selftest

    unit = tmp_path / "sample"
    assert run_selftest(unit)["ok"] is True
    r = _read_json(UnitPaths(unit).verify)
    assert quote_source_details(r) == []
    assert entry(r, "citations")["status"] in ("PASS", "WARN")


# ---------------------------------------------------------------- prose-only numbers and terms (Task 23)


def test_numbers_ignore_marker_sections_and_notes(tmp_path):
    u = copy_fixture("ok", tmp_path)
    before = entry(run_verify(u), "numbers")
    append_to_note(
        u,
        "\n\n<!-- tal:errata -->\n> [!CAUTION]\n> The slide says 5% a month. (slide 1)\n<!-- /tal:errata -->\n"
        "\n> [!NOTE]\n> Over 3 years the gap grows to £40 or more.\n",
    )
    assert entry(run_verify(u), "numbers") == before
    append_to_note(u, "\nOver 3 years the gap grows (slide 1).\n")
    assert "in the note, not in the sources: 3years" in entry(run_verify(u), "numbers")["details"]


def test_terms_ignore_marker_sections(tmp_path):
    u = copy_fixture("ok", tmp_path)
    before = entry(run_verify(u), "terms")
    append_to_note(
        u,
        "\n\n<!-- tal:check -->\n1. Would a Monte Carlo run of GBM paths change the answer?\n\n"
        "<details><summary>Answer</summary>\n\nNo.\n\n</details>\n<!-- /tal:check -->\n",
    )
    assert entry(run_verify(u), "terms") == before
    append_to_note(u, "\nIn the end a Monte Carlo run would agree (slide 1).\n")
    assert "not in the transcript or slides: Monte Carlo" in entry(run_verify(u), "terms")["details"]


def test_not_covered_singular_takes_one_number(tmp_path):
    u = five_slide_unit(tmp_path / "a", "- slide 3 - 5 worked examples skipped\n")
    assert entry(run_verify(u), "coverage") == {"name": "coverage", "status": "FAIL", "details": [
        f"slide {n} is neither cited nor listed in the not-covered section" for n in (4, 5)]}
    reversed_range = five_slide_unit(tmp_path / "b", "- slides 5–3\n")
    assert entry(run_verify(reversed_range), "coverage")["details"] == [
        f"slide {n} is neither cited nor listed in the not-covered section" for n in (3, 4)]
