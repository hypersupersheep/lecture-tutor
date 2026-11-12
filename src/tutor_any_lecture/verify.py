"""The delivery gate: nine checks over one unit folder, written to verify.json.

``run_verify(unit)`` reads only files inside the unit and the packaged
``data/banned_phrases.txt``. The checks always come in the same order and under the
same names; a check whose output is not in plan.json is a PASS entry marked skipped.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

from .cards import load_cards, validate_cards
from .checks import CheckResult
from .citations import parse, resolve
from .conceptmap import load_map, validate_map
from .items import load_items, validate_items
from .notecheck import check_note, marker_sections
from .plan import load_plan
from .slides import load_pages, max_label
from .source import SourceInfo

# _strip_code is package-internal: verify removes code exactly as check_note and units() do.
from .textstats import BRACKET_MATH_RE, DISPLAY_MATH_RE, INLINE_MATH_RE, PAREN_MATH_RE, _strip_code
from .transcript import Transcript
from .unit import UnitPaths

REPORT_PASS = "Automated checks passed; not visually reviewed."
REPORT_FAIL = "Automated checks failed."
SKIPPED = "skipped: not in plan.outputs"
MISSING_TRANSCRIPT = "sources/transcript.json missing"
DURATION_UNKNOWN = "duration unknown: time citations not range-checked"
SEVERITY = {"PASS": 0, "WARN": 1, "FAIL": 2}

# "\$" is a literal currency sign: hidden behind this placeholder while math is removed.
_DOLLAR_PLACEHOLDER = ""

NOT_COVERED_SLIDE_RE = re.compile(r"slide\s+(\d+)", re.IGNORECASE)

# terms
NOTE_CALLOUT_RE = re.compile(r"^\s*>\s*\[!NOTE\]", re.IGNORECASE)
CALLOUT_TAG_RE = re.compile(r"\[![A-Za-z]+\][+-]?")
LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")
URL_RE = re.compile(r"<https?://[^>\s]*>|https?://\S+")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>\n]*>")
LATIN_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ɏḀ-ỿ]+")

# numbers: a quantity with a unit, or a currency sign and the first digit after it.
NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?\s?(?:%|(?:percent|bps?|years?|months?|weeks?|days?|hours?|minutes?)\b)|[£$€¥]\s?\d",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- text views


def _code_and_math_free(md: str) -> tuple[str, str]:
    """(code_free, note_text): the note without code, then also without math.

    Code goes as in check_note: fenced blocks whole, inline spans deleted. Math goes as
    units() excludes it: $$…$$, \\[…\\], \\(…\\), then inline $…$ by the pandoc rule.
    """
    code_free = _strip_code(md)
    text = code_free.replace("\\$", _DOLLAR_PLACEHOLDER)
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


def _check_citations(cits, pages, duration, transcript, slides_only) -> dict:
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


def _check_coverage(cits, pages, md) -> dict:
    covered: set[int] = set()
    for c in cits:
        if c.kind != "slide":
            continue
        a = int(c.start)
        b = int(c.end) if c.end is not None else a
        covered.update(range(min(a, b), max(a, b) + 1))
    not_covered = "\n".join(marker_sections(md)["not-covered"])
    covered.update(int(n) for n in NOT_COVERED_SLIDE_RE.findall(not_covered))
    details = [
        f"slide {n} is neither cited nor listed in the not-covered section"
        for n in sorted({_slide_number(p) for p in pages})
        if n not in covered
    ]
    return _entry("coverage", "FAIL" if details else "PASS", details)


def _normalise(text: str) -> str:
    return " ".join(text.casefold().replace("-", " ").split())


def _terms_text(note_text: str) -> str:
    lines = note_text.split("\n")
    kept: list[str] = []
    i = 0
    while i < len(lines):
        if NOTE_CALLOUT_RE.match(lines[i]):
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    text = "\n".join(kept)
    text = HTML_COMMENT_RE.sub(" ", text)
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
            assignment = json.loads(p.assignment.read_text(encoding="utf-8"))
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
    md = p.explanation.read_text(encoding="utf-8")
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
        _check_citations(cits, pages, duration, transcript, slides_only),
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
