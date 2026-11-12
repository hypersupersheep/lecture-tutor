import pytest
from conftest import fx, names_by_status, status_of

from tutor_any_lecture.notecheck import check_note, marker_sections, strip_marker_sections
from tutor_any_lecture.textstats import units

BAD_NOTE = fx("notes", "bad_note.md").read_text(encoding="utf-8")
QUICK_NOTE_1200_WORDS_90MIN = fx("notes", "quick_note_1200_words_90min.md").read_text(encoding="utf-8")

MARKED = """## Part one

Prose one.

<!-- tal:check -->
1. First question?
<details><summary>Answer</summary>Because.</details>
<!-- /tal:check -->

## Part two

Prose two.

<!-- tal:check -->
1. Second question?
<details><summary>Answer</summary>Indeed.</details>
<!-- /tal:check -->
"""

F = "`" * 3
CODE_NOTE = (
    "## A\n\nText (slide 1).\n\n"
    + F
    + "python\n# 1.2 not a heading\n#### nor this\nprint(\"a string literal that is long enough\")\n<!-- tal:check -->\n"
    + F
    + "\n\n"
    + "Use `print(\"another long string literal here\")` now.\n"
)

# 68 CJK characters of prose (2 in the heading, 3 x 22 in the paragraph); the blockquote has
# 51 non-whitespace characters (38 without the citation), so the ratio is 0.75 (or 0.56): below 1.0
ZH_NOTE = (
    "## 复利\n\n"
    + "本金每一期都把利息并入,下一期按更大的本金计息。" * 3
    + "\n\n> Interest is added to the balance each period. (slide 2, 0:40)\n"
)


def test_fail_rules():
    r = names_by_status(check_note(BAD_NOTE, "en", "deep", 90, "markdown"))
    assert {
        "h4",
        "numbered_heading",
        "quotes_per_paragraph",
        "callout_type",
        "uncited_blockquote",
        "toc_mismatch",
        "details_missing",
        "uncited_quote",
    } <= r["FAIL"]


def test_warns_scale_with_goal():
    assert 1150 <= units(QUICK_NOTE_1200_WORDS_90MIN, "en") <= 1250
    quick = names_by_status(check_note(QUICK_NOTE_1200_WORDS_90MIN, "en", "quick", 90, "markdown"))
    assert "length" not in quick.get("WARN", set())
    deep = names_by_status(check_note(QUICK_NOTE_1200_WORDS_90MIN, "en", "deep", 90, "markdown"))
    assert "length" in deep.get("WARN", set())


def test_unknown_duration_warns():
    r = names_by_status(check_note(QUICK_NOTE_1200_WORDS_90MIN, "en", "quick", None, "markdown"))
    assert "duration" in r["WARN"] and "length" not in r["WARN"]


def test_marker_sections_repeated_check():
    s = marker_sections(MARKED)
    assert set(s) == {"pretest", "check", "not-covered", "errata"}
    assert s["check"] == [
        "1. First question?\n<details><summary>Answer</summary>Because.</details>",
        "1. Second question?\n<details><summary>Answer</summary>Indeed.</details>",
    ]
    assert s["pretest"] == [] and s["not-covered"] == [] and s["errata"] == []
    assert status_of(check_note(MARKED, "en", "deep", 90, "markdown"), "markers") == "PASS"


def test_strip_marker_sections():
    assert strip_marker_sections(MARKED) == "## Part one\n\nProse one.\n\n\n## Part two\n\nProse two.\n\n"


def test_unclosed_marker_fails():
    md = "## A\n\n<!-- tal:pretest -->\n1. Q?\n"
    assert status_of(check_note(md, "en", "deep", 90, "markdown"), "markers") == "FAIL"
    assert marker_sections(md)["pretest"] == []
    assert strip_marker_sections(md) == md


def test_code_is_ignored():
    assert "FAIL" not in names_by_status(check_note(CODE_NOTE, "en", "deep", 90, "markdown"))
    assert marker_sections(CODE_NOTE)["check"] == []
    assert strip_marker_sections(CODE_NOTE) == CODE_NOTE


def test_quote_rule_follows_lecture_language():
    assert status_of(check_note(ZH_NOTE, "zh", "deep", 90, "markdown", "en"), "quote_ratio") == "WARN"
    assert status_of(check_note(ZH_NOTE, "zh", "deep", 90, "markdown", "en"), "quote_share") == "PASS"
    assert status_of(check_note(ZH_NOTE, "zh", "deep", 90, "markdown"), "quote_ratio") == "PASS"


def test_h2_count_cap_scales_with_duration():
    def note(n):
        return "\n\n".join(f"## Part {i}\n\nSome prose." for i in range(n)) + "\n"

    # cap = max(16, ceil(16 * duration_min / 90)): 16 at 90 minutes, 32 at 180
    assert status_of(check_note(note(16), "en", "deep", 90, "markdown"), "h2_count") == "PASS"
    assert status_of(check_note(note(17), "en", "deep", 90, "markdown"), "h2_count") == "WARN"
    assert status_of(check_note(note(32), "en", "deep", 180, "markdown"), "h2_count") == "PASS"
    assert status_of(check_note(note(33), "en", "deep", 180, "markdown"), "h2_count") == "WARN"


def test_unknown_goal_raises():
    with pytest.raises(ValueError):
        check_note("## A\n\nText.\n", "en", "fast", 90, "markdown")


def details_of(results, name):
    """Local helper: the details of the result called ``name``."""
    return next(r.details for r in results if r.name == name)


def test_marker_problem_reports_raw_line():
    # line 1 heading; lines 2-8 a fenced block (five code lines); line 9 an unclosed marker
    md = "# Title\n" + F + "python\n" + "x = 1\n" * 5 + F + "\n<!-- tal:check -->\n1. Q?\n"
    assert md.split("\n")[8] == "<!-- tal:check -->"
    results = check_note(md, "en", "deep", 90, "markdown")
    assert details_of(results, "markers") == ["line 9: <!-- tal:check --> is never closed"]



# ---- rules that had no test (Task 21) ---------------------------------------


def test_nested_marker_is_a_problem():
    md = ("## A\n\nText.\n\n<!-- tal:check -->\n<!-- tal:pretest -->\n1. Q?\n"
          "<!-- /tal:pretest -->\n<!-- /tal:check -->\n")
    results = check_note(md, "en", "deep", 90, "markdown")
    assert status_of(results, "markers") == "FAIL"
    assert "line 5: <!-- tal:check --> is not closed before the next marker" in details_of(results, "markers")


def test_unknown_marker_name_is_a_problem():
    md = "## A\n\n<!-- tal:quiz -->\n1. Q?\n<!-- /tal:quiz -->\n"
    assert details_of(check_note(md, "en", "deep", 90, "markdown"), "markers") == [
        "line 3: unknown marker <!-- tal:quiz -->",
        "line 5: unknown marker <!-- /tal:quiz -->",
    ]


def test_close_without_open_is_a_problem():
    md = "## A\n\nText.\n<!-- /tal:check -->\n"
    assert details_of(check_note(md, "en", "deep", 90, "markdown"), "markers") == [
        "line 4: <!-- /tal:check --> closes nothing"
    ]


def test_second_errata_section_is_a_problem():
    section = "<!-- tal:errata -->\n> [!CAUTION]\n> The slide says 5%. (slide 1)\n<!-- /tal:errata -->\n"
    md = "## A\n\nText.\n\n" + section + "\n" + section
    assert details_of(check_note(md, "en", "deep", 90, "markdown"), "markers") == [
        "line 10: second 'errata' section"
    ]


def test_toc_mismatch_on_obsidian_target():
    md = "- [[#Present]]\n- [[#Missing|shown]]\n\n## Present\n\nText.\n"
    results = check_note(md, "en", "deep", 90, "obsidian")
    assert details_of(results, "toc_mismatch") == ["TOC link [[#Missing]] matches no H2"]
    fixed = md.replace("[[#Missing|shown]]", "[[#Present|again]]")
    assert status_of(check_note(fixed, "en", "deep", 90, "obsidian"), "toc_mismatch") == "PASS"


def test_duplicate_heading_slugs_get_suffixes():
    md = ("- [Intro](#intro)\n- [Intro again](#intro-1)\n- [Third](#intro-2)\n\n"
          "## Intro\n\nA.\n\n## Intro\n\nB.\n")
    assert details_of(check_note(md, "en", "deep", 90, "markdown"), "toc_mismatch") == [
        "TOC link #intro-2 matches no H2"
    ]
