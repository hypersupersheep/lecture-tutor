import json

import pytest

from tutor_any_lecture.citations import link_times, link_unit, parse, resolve
from tutor_any_lecture.unit import UnitPaths


def test_parse_forms():
    kinds = [
        (c.kind, c.start, c.end, c.estimated)
        for c in parse("A (slide 15). B (13:42–14:05). C （1:02:03）. D (~13:40). E (slides 14–16, 40:38)")
    ]
    assert ("slide", "15", None, False) in kinds
    assert ("time", 822.0, 845.0, False) in kinds
    assert ("time", 3723.0, None, False) in kinds
    assert ("time", 820.0, None, True) in kinds


def test_resolve_flags_out_of_range():
    assert resolve(parse("(slide 40) (99:00)"), max_slide=32, duration=5400) == [
        "slide 40 > 32",
        "99:00 > duration 1:30:00",
    ]


def test_resolve_unknown_duration_no_time_errors():
    assert resolve(parse("(99:00)"), max_slide=None, duration=None) == []


def test_parse_linked_timestamp():
    got = [(c.kind, c.start, c.end, c.estimated) for c in parse("(slide 15, [13:42](https://youtu.be/x?t=822s))")]
    assert got == [("slide", "15", None, False), ("time", 822.0, None, False)]
    got = [
        (c.kind, c.start, c.end, c.estimated)
        for c in parse("([13:42](https://v.example/w?t=822s)–14:05) (~[13:40](https://v.example/w?t=820s))")
    ]
    assert got == [("time", 822.0, 845.0, False), ("time", 820.0, None, True)]



def test_resolve_uses_a_range_end_and_a_slide_range_maximum():
    assert resolve(parse("(slides 2–5)"), max_slide=4, duration=None) == ["slide 5 > 4"]
    assert resolve(parse("(slides 5–2)"), max_slide=4, duration=None) == ["slide 5 > 4"]
    assert resolve(parse("(slides 2–4)"), max_slide=4, duration=None) == []
    assert resolve(parse("(10:00–12:00)"), max_slide=None, duration=660) == ["12:00 > duration 11:00"]


def test_full_width_comma_separates_citations():
    got = [(c.kind, c.start, c.end) for c in parse("(slide 1，0:20)")]
    assert got == [("slide", "1", None), ("time", 20.0, None)]


def test_callout_citation_is_counted_once():
    plain = "Rounding (slide 9)\nThe bank rounds down (slide 9, 0:30).\n"
    callout = "> [!WARNING] Rounding (slide 9)\n> The bank rounds down (slide 9, 0:30).\n"
    for text in (plain, callout):
        assert [(c.kind, c.raw, c.line) for c in parse(text)] == [
            ("slide", "(slide 9)", 1),
            ("slide", "(slide 9, 0:30)", 2),
            ("time", "(slide 9, 0:30)", 2),
        ]
        assert resolve(parse(text), max_slide=3, duration=None) == ["slide 9 > 3", "slide 9 > 3"]


# ---- the tool writes the time links (Task 29, L10) ---------------------------

VIDEO = "https://www.youtube.com/watch?v=abc"

PLAIN_NOTE = """# Title

## Part one

*(slide 2, 0:40–3:10)*

The lecturer defines it (13:42). A range (13:42–14:05), an estimate (~13:40), one past the hour
（1:02:03）, a slide and a time (slide 15, 0:07) and two times (0:05, 0:09).

Not citations: (see 0:30), `rev(1:20)`, (slide 4).

```text
(0:30) inside a fence
```
"""

LINKED_NOTE = f"""# Title

## Part one

*(slide 2, [0:40]({VIDEO}&t=40s)–3:10)*

The lecturer defines it ([13:42]({VIDEO}&t=822s)). A range ([13:42]({VIDEO}&t=822s)–14:05), an estimate (~[13:40]({VIDEO}&t=820s)), one past the hour
（[1:02:03]({VIDEO}&t=3723s)）, a slide and a time (slide 15, [0:07]({VIDEO}&t=7s)) and two times ([0:05]({VIDEO}&t=5s), [0:09]({VIDEO}&t=9s)).

Not citations: (see 0:30), `rev(1:20)`, (slide 4).

```text
(0:30) inside a fence
```
"""


def url_unit(tmp_path, url=VIDEO, kind="url", note=PLAIN_NOTE):
    """Local helper: a unit folder with source.json (``kind``, ``url``) and explanation.md."""
    u = tmp_path / "课程 资料" / "第1周"
    (u / "sources").mkdir(parents=True)
    source = {
        "kind": kind, "title": "Synthetic lecture", "url": url, "platform": "youtube", "duration": 4000.0,
        "lecture_language": "en", "acquisition": "cc", "health": {}, "tool_versions": {}, "inputs_sha256": {},
    }
    (u / "sources" / "source.json").write_text(json.dumps(source) + "\n", encoding="utf-8", newline="\n")
    UnitPaths(u).explanation.write_text(note, encoding="utf-8", newline="\n")
    return u


def test_cite_link_links_plain_times(tmp_path):
    u = url_unit(tmp_path)
    assert link_unit(u) == {"path": str(UnitPaths(u).explanation), "linked": 8}
    linked = UnitPaths(u).explanation.read_text(encoding="utf-8")
    assert linked == LINKED_NOTE
    # The parser reads the linked note as the same citations.
    plain = [(c.kind, c.start, c.end, c.estimated) for c in parse(PLAIN_NOTE)]
    assert [(c.kind, c.start, c.end, c.estimated) for c in parse(linked)] == plain


def test_cite_link_url_forms():
    assert link_times("(0:30)", "https://youtu.be/abc") == ("([0:30](https://youtu.be/abc?t=30s))", 1)
    # an existing start time is replaced, other parameters stay
    assert link_times("(1:00)", "https://y.example/w?v=a&t=15s&list=x") == (
        "([1:00](https://y.example/w?v=a&list=x&t=60s))", 1)
    assert link_times("(1:00)", "https://y.example/w?t=15") == ("([1:00](https://y.example/w?t=60s))", 1)
    # parentheses and spaces in the address would end the link: they are percent-encoded
    assert link_times("(0:01)", "https://y.example/a (b)") == ("([0:01](https://y.example/a%20%28b%29?t=1s))", 1)


def test_cite_link_is_idempotent(tmp_path):
    u = url_unit(tmp_path)
    link_unit(u)
    once = UnitPaths(u).explanation.read_bytes()
    assert link_unit(u) == {"path": str(UnitPaths(u).explanation), "linked": 0}
    assert UnitPaths(u).explanation.read_bytes() == once
    assert link_times(LINKED_NOTE, VIDEO) == (LINKED_NOTE, 0)


@pytest.mark.parametrize("kind, url", [("local", None), ("transcript", None), ("platform", VIDEO), ("url", None)])
def test_cite_link_leaves_other_sources_alone(tmp_path, kind, url):
    u = url_unit(tmp_path, url=url, kind=kind)
    before = UnitPaths(u).explanation.read_bytes()
    assert link_unit(u) == {"path": str(UnitPaths(u).explanation), "linked": 0}
    assert UnitPaths(u).explanation.read_bytes() == before


def test_cite_link_without_source_changes_nothing(tmp_path):
    u = url_unit(tmp_path)
    UnitPaths(u).source.unlink()
    before = UnitPaths(u).explanation.read_bytes()
    assert link_unit(u)["linked"] == 0
    assert UnitPaths(u).explanation.read_bytes() == before
