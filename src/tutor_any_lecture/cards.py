"""Anki cards: the cards.json schema, the card checks, the TSV export and the miss cards.

cards.json is a top-level JSON list of objects with the ``Card`` field names; ``kind``
is optional and defaults to "core". The agent writes the core cards; ``add_misses``
appends one "miss" card per item answered wrongly after the lecture.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .checks import CheckResult
from .items import find_item, load_items
from .plan import load_plan, read_json
from .progress import load_attempts
from .textstats import DISPLAY_MATH_RE, INLINE_CODE_RE, INLINE_MATH_RE, char_jaccard, fenced_lines
from .unit import UnitPaths

KINDS = ("core", "miss")
CORE_CAP = 25
QUICK_CAP = 10
MISS_CAP = 10
DUPLICATE_THRESHOLD = 0.8
BACK_MAX = 350
MISS_PHASES = ("post", "d1", "d7", "d21")
# "\\$" is a literal dollar sign: hidden behind this placeholder while math is converted.
_DOLLAR_PLACEHOLDER = "\ue000"
TSV_HEADER = (
    "#separator:tab",
    "#html:true",
    "#notetype:Basic",
    "#deck:{course}::{unit}",
    "#tags column:3",
    "#guid column:4",
)


@dataclass
class Card:
    id: str
    concept: str
    front: str
    back: str
    citation: str
    kind: str = "core"


CARD_FIELDS = tuple(f.name for f in dataclasses.fields(Card))
REQUIRED_FIELDS = tuple(name for name in CARD_FIELDS if name != "kind")


# ---------------------------------------------------------------- cards.json


def _card(obj, n: int) -> Card:
    where = f"cards.json: entry {n}"
    if not isinstance(obj, dict):
        raise ValueError(f"{where} is not an object")
    missing = [k for k in REQUIRED_FIELDS if k not in obj]
    if missing:
        raise ValueError(f"{where} is missing {', '.join(missing)}")
    extra = sorted(k for k in obj if k not in CARD_FIELDS)
    if extra:
        raise ValueError(f"{where} has unknown keys {', '.join(extra)}")
    for key, value in obj.items():
        if not isinstance(value, str):
            raise ValueError(f"{where} ({obj.get('id')!r}): {key} is not a string")
    card = Card(**obj)
    if card.kind not in KINDS:
        raise ValueError(f"{where} ({card.id!r}): kind must be core or miss, got {card.kind!r}")
    return card


def load_cards(path: Path) -> list[Card]:
    """The cards of cards.json in file order. A missing file raises FileNotFoundError; a bad one, ValueError."""
    data = read_json(path, "cards.json")
    if not isinstance(data, list):
        raise ValueError("cards.json: the top level must be a list of card objects")
    return [_card(obj, n) for n, obj in enumerate(data)]


def _write_cards(path: Path, cards: list[Card]) -> None:
    text = json.dumps([dataclasses.asdict(c) for c in cards], ensure_ascii=False, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- names


def guid(course: str, unit: str, key: str) -> str:
    """A stable Anki GUID: sha256 rather than the built-in hash, which changes between runs."""
    return hashlib.sha256(f"{course}|{unit}|{key}".encode("utf-8")).hexdigest()[:16]


def tag(course: str, unit: str, concept: str) -> str:
    """The Anki tag of a card; Anki splits tags at spaces, so spaces become underscores."""
    return f"{course}::{unit}::{concept}".replace(" ", "_")


# ---------------------------------------------------------------- checks


def _result(name: str, bad_status: str, offences: list[str]) -> CheckResult:
    return CheckResult(name, bad_status if offences else "PASS", offences)


def validate_cards(cards, goal: str, lang: str) -> list[CheckResult]:
    """The four card checks, always in this order: count, duplicates, citation, back_length.

    ``lang`` is unused: the duplicate rule is the same character 3-gram Jaccard in every language.
    """
    core = [c for c in cards if c.kind == "core"]

    cap = QUICK_CAP if goal == "quick" else CORE_CAP
    count = [f"{len(core)} core cards, cap {cap}"] if len(core) > cap else []

    duplicates = []
    for i, x in enumerate(core):
        for y in core[i + 1 :]:
            score = char_jaccard(x.front, y.front)
            if score >= DUPLICATE_THRESHOLD:
                duplicates.append(f"{x.id} ~ {y.id}: {score:.2f}")

    citation = [f"{c.id}: no citation" for c in cards if not c.citation.strip()]
    back_length = [f"{c.id}: back has {len(c.back)} characters" for c in cards if len(c.back) > BACK_MAX]

    return [
        _result("count", "FAIL", count),
        _result("duplicates", "FAIL", duplicates),
        _result("citation", "FAIL", citation),
        _result("back_length", "WARN", back_length),
    ]


# ---------------------------------------------------------------- export


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _math(text: str) -> str:
    """$$…$$ becomes \\[…\\] and $…$ becomes \\(…\\), Anki's MathJax delimiters; \\$ is a plain $."""
    text = text.replace("\\$", _DOLLAR_PLACEHOLDER)
    text = DISPLAY_MATH_RE.sub(lambda m: "\\[" + m.group()[2:-2] + "\\]", text)
    text = INLINE_MATH_RE.sub(lambda m: "\\(" + m.group()[1:-1] + "\\)", text)
    return text.replace(_DOLLAR_PLACEHOLDER, "$")


def _prose(text: str) -> str:
    """Text outside fenced blocks: inline code verbatim in <code>, math converted around it."""
    out: list[str] = []
    pos = 0
    for m in INLINE_CODE_RE.finditer(text):
        out.append(_math(_escape(text[pos : m.start()])))
        ticks = len(m.group(1))
        out.append("<code>" + _escape(m.group()[ticks:-ticks]) + "</code>")
        pos = m.end()
    out.append(_math(_escape(text[pos:])))
    return "".join(out)


def _field(text: str) -> str:
    """One TSV field as Anki HTML.

    In this order: escape &, < and >; a fenced code block becomes <pre><code>…</code></pre>
    (tabs in it four spaces, so its indentation survives) and inline code <code>…</code>;
    outside code, $$…$$ and $…$ become MathJax delimiters; then line breaks and tabs become <br>.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fenced = fenced_lines(lines)
    pieces: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and fenced[j] == fenced[i]:
            j += 1
        if not fenced[i]:
            pieces.append(_prose("\n".join(lines[i:j])))
        else:
            # A run of fenced lines may hold several blocks: each opens on a fence line
            # and closes on the next line that starts with the same fence.
            block: list[str] = []
            fence = None
            for line in lines[i:j]:
                stripped = line.lstrip()
                if fence is None:
                    fence = stripped[:3]
                elif stripped.startswith(fence):
                    pieces.append(_code_block(block))
                    block, fence = [], None
                else:
                    block.append(line)
            if fence is not None:  # never closed: the block runs to the end of the field
                pieces.append(_code_block(block))
        i = j
    return "\n".join(pieces).replace("\n", "<br>").replace("\t", "<br>")


def _code_block(lines: list[str]) -> str:
    return "<pre><code>" + _escape("\n".join(lines).replace("\t", "    ")) + "</code></pre>"


def _without_trailing_marks(text: str) -> str:
    """``text`` in NFKC (full-width parentheses become ASCII ones), without trailing spaces and punctuation."""
    text = unicodedata.normalize("NFKC", text)
    end = len(text)
    while end and (text[end - 1].isspace() or unicodedata.category(text[end - 1]).startswith("P")):
        end -= 1
    return text[:end]


def ends_with_citation(back: str, citation: str) -> bool:
    """True when ``back`` already ends with ``citation``, as a miss card's item answer often does.

    Trailing spaces and punctuation are ignored on both sides, and full-width parentheses
    count as ordinary ones: "…不止一个（4:14–4:37）。" ends with "(4:14–4:37)".
    """
    cite = _without_trailing_marks(citation)
    return bool(cite) and _without_trailing_marks(back).endswith(cite)


def export_tsv(unit: Path) -> Path:
    """Write cards.tsv (an Anki import file) from cards.json and plan.json; return its path."""
    paths = UnitPaths(unit)
    plan = load_plan(paths.plan)
    cards = load_cards(paths.cards_json)
    course, unit_name = plan.course, plan.unit

    lines = [h.format(course=course, unit=unit_name) for h in TSV_HEADER]
    for c in cards:
        back = _field(c.back)
        # A back that already ends with its citation (a miss card's item answer often does) gets no second one.
        if not ends_with_citation(c.back, c.citation):
            back += f"<br><small>{_field(c.citation)}</small>"
        row = (_field(c.front), back, tag(course, unit_name, c.concept), guid(course, unit_name, c.id))
        lines.append("\t".join(row))
    paths.cards_tsv.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    return paths.cards_tsv


# ---------------------------------------------------------------- miss cards


def add_misses(unit: Path, course: str, workspace: Path) -> int:
    """Append a miss card for each item missed after the lecture (at most 10 per unit); return how many."""
    paths = UnitPaths(unit)
    plan = load_plan(paths.plan)
    if course != plan.course:
        raise ValueError(f"course {course!r} does not match plan.json course {plan.course!r}")
    items = load_items(paths.items)
    try:
        cards = load_cards(paths.cards_json)
    except FileNotFoundError:
        cards = []

    # Item ids missed in a post-lecture phase of this unit, in order of first appearance.
    candidates = dict.fromkeys(
        a.item_id
        for a in load_attempts(course, workspace)
        if a.unit == plan.unit and a.phase in MISS_PHASES and a.score < 1
    )

    ids = {c.id for c in cards}
    misses = sum(1 for c in cards if c.kind == "miss")
    added = 0
    for item_id in candidates:
        if misses >= MISS_CAP:
            break
        if f"{item_id}|miss" in ids:
            continue
        try:
            item = find_item(items, item_id)
        except KeyError:
            continue
        new = Card(id=f"{item.id}|miss", concept=item.concept, front=item.prompt, back=item.answer,
                   citation=item.citation, kind="miss")
        cards.append(new)
        ids.add(new.id)
        misses += 1
        added += 1

    _write_cards(paths.cards_json, cards)
    export_tsv(unit)
    return added
