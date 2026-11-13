"""The delivery gate: nine checks over one unit folder, written to verify.json.

``run_verify(unit)`` reads only files inside the unit and the packaged
``data/banned_phrases.txt``. The checks always come in the same order and under the
same names; a check whose output is not in plan.json is a PASS entry marked skipped.
"""

from __future__ import annotations

import json
import re
import unicodedata
from bisect import bisect_right
from importlib import resources
from pathlib import Path

from .cards import load_cards, validate_cards
from .checks import CheckResult
from .citations import format_seconds, parse, resolve
from .conceptmap import load_map, validate_map
from .items import load_items, validate_items
from .notecheck import check_note, cited_quotes, marker_sections, strip_marker_sections
from .plan import load_plan, read_json, read_text
from .slides import load_pages, max_label
from .source import SourceInfo

# verify removes code exactly as check_note and units() do.
from .textstats import (
    BRACKET_MATH_RE,
    CJK_RE,
    DISPLAY_MATH_RE,
    INLINE_CODE_RE,
    INLINE_MATH_RE,
    MD_LINK_URL_RE,
    PAREN_MATH_RE,
    strip_code,
)
from .transcript import Transcript
from .unit import UnitPaths

REPORT_PASS = "Automated checks passed; not visually reviewed."
REPORT_FAIL = "Automated checks failed."
SKIPPED = "skipped: not in plan.outputs"
MISSING_TRANSCRIPT = "sources/transcript.json missing"
DURATION_UNKNOWN = "duration unknown: time citations not range-checked"
SEVERITY = {"PASS": 0, "WARN": 1, "FAIL": 2}

# "\$" is a literal currency sign: hidden behind this placeholder while math is removed.
_DOLLAR_PLACEHOLDER = "\ue000"

# "slides N–M" (en dash or hyphen-minus) is a range when N <= M; "slide N" takes one number.
# Any number of them on a line.
NOT_COVERED_SLIDE_RE = re.compile(r"slides\s+(\d+)\s*[–-]\s*(\d+)|slides?\s+(\d+)", re.IGNORECASE)

# terms
NOTE_CALLOUT_RE = re.compile(r"^\s*>\s*\[!NOTE\]", re.IGNORECASE)
CALLOUT_TAG_RE = re.compile(r"\[![A-Za-z]+\][+-]?")
LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")
URL_RE = re.compile(r"<https?://[^>\s]*>|https?://\S+")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>\n]*>")
LATIN_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ɏḀ-ỿ]+")

# quote_source: editorial marks split a quote; a cited time looks this far either side.
EDITORIAL_RE = re.compile(r"…|\.\.\.|\[[^\]\n]*\]")
NOT_LETTER_OR_DIGIT_RE = re.compile(r"[\W_]+")
CJK_SPACE_RE = re.compile(rf" (?={CJK_RE.pattern})|(?<={CJK_RE.pattern}) ")
# In normalised text a word ends at a space, at a CJK character or at either end.
_CJK_CHARS = CJK_RE.pattern[1:-1]
WORD_EDGE_BEFORE = rf"(?<![^ {_CJK_CHARS}])"
WORD_EDGE_AFTER = rf"(?![^ {_CJK_CHARS}])"
QUOTE_WINDOW_S = 60
QUOTE_MIN_WORDS = 3
QUOTE_MIN_CJK_CHARS = 6
QUOTE_SHOWN_CHARS = 40

# numbers: a quantity with a unit, or a currency sign and the first digit after it.
NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?\s?(?:%|(?:percent|bps?|years?|months?|weeks?|days?|hours?|minutes?)\b)|[£$€¥]\s?\d",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- text views


def _without_note_callouts(text: str) -> str:
    """``text`` without its NOTE callouts (tutor additions), each from its tag line to the last '>' line."""
    lines = text.split("\n")
    kept: list[str] = []
    i = 0
    while i < len(lines):
        if NOTE_CALLOUT_RE.match(lines[i]):
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept)


def _code_and_math_free(md: str) -> tuple[str, str]:
    """(code_free, note_text): the note without code; then the lecture prose without math.

    Code goes as in check_note: fenced blocks whole, inline spans deleted. note_text, which
    the terms and numbers checks read, also leaves out the four marker sections and the
    NOTE callouts. Math goes as units() excludes it: $$…$$, \\[…\\], \\(…\\), then inline
    $…$ by the pandoc rule.
    """
    code_free = strip_code(md)
    text = _without_note_callouts(strip_marker_sections(code_free)).replace("\\$", _DOLLAR_PLACEHOLDER)
    for pattern in (DISPLAY_MATH_RE, BRACKET_MATH_RE, PAREN_MATH_RE, INLINE_MATH_RE):
        text = pattern.sub(" ", text)
    return code_free, text.replace(_DOLLAR_PLACEHOLDER, "\\$")


def _slide_number(page) -> int:
    return int(page.label) if page.label is not None else page.n


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


# ---------------------------------------------------------------- folding


def _entry(name: str, status: str, details: list[str]) -> dict:
    return {"name": name, "status": status, "details": details}


def _fold(name: str, results: list[CheckResult]) -> dict:
    """One entry: the worst sub-result, with each non-PASS detail as "<sub-name>: <detail>"."""
    status = max((r.status for r in results), key=SEVERITY.__getitem__, default="PASS")
    details: list[str] = []
    for r in results:
        if r.status == "PASS":
            continue
        if r.details:
            details.extend(f"{r.name}: {d}" for d in r.details)
        else:
            details.append(r.name)
    return _entry(name, status, details)


def _skipped(name: str) -> dict:
    return _entry(name, "PASS", [SKIPPED])


def _error_detail(file_name: str, e: Exception) -> str:
    message = str(e)
    return message if message.startswith(file_name) else f"{file_name}: {message}"


# ---------------------------------------------------------------- checks


def _citation_problems(cits, pages, duration, transcript, slides_only) -> dict:
    details = resolve(cits, max_label(pages) if pages else None, duration)
    if transcript is None:
        if slides_only:
            details += [f"time citation in a slides-only unit: {c.raw}" for c in cits if c.kind == "time"]
        else:
            details.append(MISSING_TRANSCRIPT)
    if details:
        return _entry("citations", "FAIL", details)
    if duration is None and any(c.kind == "time" for c in cits):
        return _entry("citations", "WARN", [DURATION_UNKNOWN])
    return _entry("citations", "PASS", [])


def _check_citations(cits, pages, duration, transcript, slides_only, md: str) -> dict:
    """The citation problems, then the quote_source sub-result folded in as "quote_source: <detail>"."""
    entry = _citation_problems(cits, pages, duration, transcript, slides_only)
    quotes = _check_quote_source(md, transcript, pages)
    if quotes.status != "PASS":
        folded = _fold("citations", [quotes])
        entry["status"] = max(entry["status"], folded["status"], key=SEVERITY.__getitem__)
        entry["details"] += folded["details"]
    return entry


# ---------------------------------------------------------------- quote_source


def _quote_norm(text: str) -> str:
    """NFKC, casefold, every run of non-letters-or-digits one space, stripped; no space next to CJK."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = NOT_LETTER_OR_DIGIT_RE.sub(" ", text).strip()
    return CJK_SPACE_RE.sub("", text)


def _joined(texts) -> tuple[str, list[int]]:
    """``_quote_norm`` of the texts joined by spaces, and where each text starts in it.

    Built piece by piece, so the result equals ``_quote_norm(" ".join(texts))``.
    """
    out = ""
    starts: list[int] = []
    for t in texts:
        n = _quote_norm(t)
        if out and n and not (CJK_RE.match(out[-1]) or CJK_RE.match(n[0])):
            out += " "
        starts.append(len(out))
        out += n
    return out, starts


def _quote_parts(quote: str) -> list[str]:
    """The normalised parts between editorial marks, without the parts too short to check.

    Inline code keeps its text (only the backticks go) and a Markdown link is read as its
    text: neither is an editorial mark.
    """
    text = INLINE_CODE_RE.sub(lambda m: NOT_LETTER_OR_DIGIT_RE.sub(" ", m.group(0).strip("`")), quote)
    text = MD_LINK_URL_RE.sub(lambda m: m.group(1).lstrip("!")[1:-1], text)
    parts = []
    for raw in EDITORIAL_RE.split(text):
        part = _quote_norm(raw)
        if CJK_RE.search(part):
            long_enough = len(part.replace(" ", "")) >= QUOTE_MIN_CJK_CHARS
        else:
            long_enough = len(part.split()) >= QUOTE_MIN_WORDS
        if long_enough:
            parts.append(part)
    return parts


def _part_at(part: str, text: str) -> int:
    """Where ``part`` starts in the normalised ``text``, or -1.

    A part in a CJK script may start anywhere; any other part matches only as a run of
    whole words, so "rest rate is now fix" is not in "the interest rate is now fixed".
    """
    if CJK_RE.search(part):
        return text.find(part)
    m = re.search(WORD_EDGE_BEFORE + re.escape(part) + WORD_EDGE_AFTER, text)
    return m.start() if m else -1


class _QuoteSources:
    """The transcript and the slides, normalised once for every quote of a note."""

    def __init__(self, transcript, pages) -> None:
        self.segments = transcript.segments if transcript is not None else None
        self.pages = pages
        if self.segments is not None:
            self.all_text, self.starts = _joined(s.text for s in self.segments)
        else:
            self.all_text, self.starts = "", []
        self.slide_texts = [(_slide_number(p), _quote_norm(p.text)) for p in pages]

    def cited(self, c) -> str | None:
        """The text at one citation; None for a time when the unit has no transcript."""
        if c.kind == "slide":
            lo, hi = _span(c.start, c.end)
            return _joined(p.text for p in self.pages if lo <= _slide_number(p) <= hi)[0]
        if self.segments is None:
            return None
        lo = c.start - QUOTE_WINDOW_S
        hi = (c.end if c.end is not None else c.start) + QUOTE_WINDOW_S
        return _joined(s.text for s in self.segments if s.start <= hi and s.end >= lo)[0]

    def find(self, part: str) -> str | None:
        """Where ``part`` is: "at m:ss" in the transcript, else "on slide N", else None."""
        pos = _part_at(part, self.all_text)
        if pos >= 0:
            return f"at {format_seconds(self.segments[bisect_right(self.starts, pos) - 1].start)}"
        for n, text in self.slide_texts:
            if _part_at(part, text) >= 0:
                return f"on slide {n}"
        return None


def _check_quote_source(md: str, transcript, pages) -> CheckResult:
    """Every cited quote is found at the place it cites (WARN when only elsewhere, FAIL when nowhere)."""
    sources = _QuoteSources(transcript, pages)
    details: list[str] = []
    worst = "PASS"
    for quote, cits in cited_quotes(md):
        parts = _quote_parts(quote)
        places = [t for t in (sources.cited(c) for c in cits) if t is not None]
        if not parts or not places:
            continue  # nothing to check, or only times in a unit without a transcript
        missing = [part for part in parts if not any(_part_at(part, place) >= 0 for place in places)]
        if not missing:
            continue
        shown = quote if len(quote) <= QUOTE_SHOWN_CHARS else quote[:QUOTE_SHOWN_CHARS] + "…"
        cited = ", ".join(_dedupe([c.raw for c in cits]))
        found = [sources.find(part) for part in missing]
        if all(found):
            details.append(f"quote '{shown}' is not at {cited}; found {found[0]}")
            worst = max(worst, "WARN", key=SEVERITY.__getitem__)
        else:
            details.append(f"quote '{shown}' cited {cited} is not in the transcript or the slides")
            worst = "FAIL"
    return CheckResult("quote_source", worst, details)


def _span(start, end) -> tuple[int, int]:
    """The inclusive slide range from ``start`` to ``end`` (or ``start`` alone), in either order."""
    a = int(start)
    b = int(end) if end else a
    return min(a, b), max(a, b)


def _check_coverage(cits, pages, md) -> dict:
    # Ranges are kept as (low, high) pairs, so a huge range costs nothing.
    spans = [_span(c.start, c.end) for c in cits if c.kind == "slide"]
    not_covered = "\n".join(marker_sections(md)["not-covered"])
    for first, last, single in NOT_COVERED_SLIDE_RE.findall(not_covered):
        if single:
            spans.append(_span(single, None))
        else:
            # "slides 5–3" is not a range: it lists slide 5.
            spans.append(_span(first, last) if int(first) <= int(last) else _span(first, None))
    details = [
        f"slide {n} is neither cited nor listed in the not-covered section"
        for n in sorted({_slide_number(p) for p in pages})
        if not any(lo <= n <= hi for lo, hi in spans)
    ]
    return _entry("coverage", "FAIL" if details else "PASS", details)


def _normalise(text: str) -> str:
    return " ".join(text.casefold().replace("-", " ").split())


def _terms_text(note_text: str) -> str:
    text = HTML_COMMENT_RE.sub(" ", note_text)
    text = HTML_TAG_RE.sub(" ", text)
    text = CALLOUT_TAG_RE.sub(" ", text)
    text = LINK_TARGET_RE.sub("]", text)
    return URL_RE.sub(" ", text)


def _terms(text: str) -> list[str]:
    """Runs of 2+ Capitalized words joined by one space or hyphen, and words with an
    internal capital that lie in no such run, in document order."""
    words = list(LATIN_WORD_RE.finditer(text))
    found: list[tuple[int, str]] = []
    in_run: set[int] = set()
    i = 0
    while i < len(words):
        j = i
        if words[i].group()[0].isupper():
            while (
                j + 1 < len(words)
                and words[j + 1].group()[0].isupper()
                and text[words[j].end() : words[j + 1].start()] in (" ", "-")
            ):
                j += 1
        if j > i:
            found.append((words[i].start(), text[words[i].start() : words[j].end()]))
            in_run.update(range(i, j + 1))
        i = j + 1
    for k, w in enumerate(words):
        if k not in in_run and any(ch.isupper() for ch in w.group()[1:]):
            found.append((w.start(), w.group()))
    return _dedupe([term for _, term in sorted(found)])


def _check_terms(note_text: str, sources: str) -> dict:
    haystack = _normalise(sources)
    details = [
        f"not in the transcript or slides: {term}"
        for term in _terms(_terms_text(note_text))
        if _normalise(term) not in haystack
    ]
    return _entry("terms", "WARN" if details else "PASS", details)


def _numbers(text: str) -> list[str]:
    return _dedupe(["".join(m.group().lower().split()) for m in NUMBER_RE.finditer(text)])


def _check_numbers(note_text: str, sources: str) -> dict:
    in_note, in_sources = _numbers(note_text), _numbers(sources)
    details = [f"in the sources, not in the note: {n}" for n in in_sources if n not in in_note]
    details += [f"in the note, not in the sources: {n}" for n in in_note if n not in in_sources]
    return _entry("numbers", "WARN" if details else "PASS", details)


def _check_items(p: UnitPaths, plan, md: str, lang: str) -> dict:
    if "quiz" not in plan.outputs and "pretest" not in plan.outputs:
        return _skipped("items")
    if not p.items.exists():
        return _entry("items", "FAIL", ["items.json missing"])
    try:
        items = load_items(p.items)
    except ValueError as e:
        return _entry("items", "FAIL", [_error_detail("items.json", e)])
    assignment = None
    if p.assignment.exists():
        try:
            assignment = read_json(p.assignment, "assignment.json")
        except ValueError as e:
            return _entry("items", "FAIL", [_error_detail("assignment.json", e)])
    try:
        results = validate_items(items, plan, md, lang, assignment)
    except ValueError as e:
        return _entry("items", "FAIL", [_error_detail("assignment.json", e)])
    entry = _fold("items", results)
    if assignment is None:
        entry["status"] = "FAIL"
        entry["details"].append("assignment.json missing")
    return entry


def _check_cards(p: UnitPaths, plan, lang: str) -> dict:
    if "cards" not in plan.outputs:
        return _skipped("cards")
    if not p.cards_json.exists():
        return _entry("cards", "FAIL", ["cards.json missing"])
    try:
        cards = load_cards(p.cards_json)
    except ValueError as e:
        return _entry("cards", "FAIL", [_error_detail("cards.json", e)])
    return _fold("cards", validate_cards(cards, plan.goal, lang))


def _check_map(p: UnitPaths, plan) -> dict:
    if "map" not in plan.outputs:
        return _skipped("map")
    if not p.map.exists():
        return _entry("map", "FAIL", ["map.json missing"])
    try:
        m = load_map(p.map)
    except ValueError as e:
        return _entry("map", "FAIL", [_error_detail("map.json", e)])
    return _fold("map", validate_map(m))


def _banned_phrases() -> list[str]:
    text = resources.files("tutor_any_lecture").joinpath("data", "banned_phrases.txt").read_text(encoding="utf-8")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _check_banned(md: str) -> dict:
    low = md.casefold()
    details = [f"banned phrase: {phrase}" for phrase in _banned_phrases() if phrase.casefold() in low]
    return _entry("banned_phrases", "WARN" if details else "PASS", details)


# ---------------------------------------------------------------- the gate


def run_verify(unit: Path) -> dict:
    """Run the nine checks on ``unit``, write verify.json and return the same object.

    A missing or invalid plan.json, or a missing explanation.md, propagates and
    writes nothing.
    """
    unit = Path(unit)
    p = UnitPaths(unit)
    plan = load_plan(p.plan)
    md = read_text(p.explanation, "explanation.md")
    source = SourceInfo.read(p.source) if p.source.exists() else None
    transcript = Transcript.from_json(p.transcript) if p.transcript.exists() else None
    pages = load_pages(unit)

    slides_only = transcript is None and source is not None and source.kind == "slides-only"
    if slides_only:
        duration = None
    elif plan.duration_s is not None:
        duration = plan.duration_s
    elif source is not None:
        duration = source.duration
    else:
        duration = None
    lang = plan.note_language
    code_free, note_text = _code_and_math_free(md)
    cits = parse(code_free)
    sources = "\n".join([transcript.text() if transcript is not None else ""] + [pg.text for pg in pages])

    checks = [
        _check_citations(cits, pages, duration, transcript, slides_only, md),
        _check_coverage(cits, pages, md),
        _check_terms(note_text, sources),
        _check_numbers(note_text, sources),
        _fold(
            "structure",
            check_note(
                md,
                lang,
                plan.goal,
                duration / 60 if duration is not None else None,
                plan.output_target,
                lecture_lang=plan.lecture_language,
            ),
        ),
        _check_items(p, plan, md, lang),
        _check_cards(p, plan, lang),
        _check_map(p, plan),
        _check_banned(md),
    ]
    overall = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS"
    result = {
        "checks": checks,
        "overall": overall,
        "warnings": sum(1 for c in checks if c["status"] == "WARN"),
        "report": REPORT_PASS if overall == "PASS" else REPORT_FAIL,
    }
    p.verify.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result
