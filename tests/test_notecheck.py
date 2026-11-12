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
