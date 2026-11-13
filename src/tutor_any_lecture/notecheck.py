"""Structure and length checks for explanation.md, scaled by goal and duration.

Pure functions, standard library only. Three text views are built once:
W (the note with code removed), P (W without marker sections: the lecture prose)
and the marker bodies of W.
"""

from __future__ import annotations

import math
import re

from .checks import CheckResult
from .citations import Citation, parse
from .textstats import INLINE_CODE_RE, fenced_lines, is_cjk_language, strip_code, units

THRESHOLDS = {
    "length_per_min": {"deep": {"cjk": (44, 89), "words": (26, 53)},
                       "exam": {"cjk": (30, 70), "words": (18, 42)},
                       "quick": {"cjk": (10, 25), "words": (6, 15)}},
    # The upper length bound, in total units, is never below this: a short lecture may have real paragraphs.
    "length_ceiling_min": {"cjk": 800, "words": 400},
    "timestamps_per_min": {"deep": 0.67, "exam": 0.5, "quick": 0.2},
    "quotes_per_min": {"deep": 0.22, "exam": 0.15, "quick": 0.07},
    "h2_per_90min": 16,
    "thin_section": {"cjk": 150, "words": 90},
    "long_paragraph": {"cjk": 300, "words": 180},
    "quotes_per_paragraph": 3,
    "quote_min_chars": 15,
    "bold_max": 15,
    "highlights_max": 8,
    "bullet_share_max": 0.10,
    # Quoted characters per unit of prose, for a CJK note of a non-CJK lecture, by quote_density.
    "cross_language_quote_ratio": {"light": (0.15, 0.6), "standard": (0.4, 1.2), "dense": (1.0, 2.0)},
    "same_language_quote_share": (0.10, 0.40),
}

GOALS = ("deep", "exam", "quick")
QUOTE_DENSITIES = tuple(THRESHOLDS["cross_language_quote_ratio"])
MARKER_NAMES = ("pretest", "check", "not-covered", "errata")
SINGLE_MARKERS = ("pretest", "not-covered", "errata")
CALLOUT_TYPES = {"NOTE", "IMPORTANT", "WARNING", "CAUTION"}

MARKER_RE = re.compile(r"^\s*<!--\s*(/?)tal:([a-z-]+)\s*-->\s*$")
H4_RE = re.compile(r"^#{4,6} ")
# An outline prefix before a space: "1.", "2)", "1.2", "1.2.3". "2008 crisis" is not one.
NUMBERED_HEADING_RE = re.compile(r"^#+ *(?:\d+[.)]|\d+(?:\.\d+)+[.)]?) ")
HEADING_RE = re.compile(r"^#{1,6} ")
CALLOUT_RE = re.compile(r"^\s*>\s*\[!([A-Za-z]+)\]")
CALLOUT_START_RE = re.compile(r"^\s*>\s*\[!")
TOC_OBSIDIAN_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\[\[#([^\]|]*)")
TOC_MARKDOWN_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\[[^\]]*\]\(#([^)]*)\)")
NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+")
PARA_BREAK_RE = re.compile(r"^(#|\||>|\s*[-*] |\s*\d+\. |---)")
INLINE_QUOTE_RE = re.compile(r'"([^"\n]*)"|“([^”\n]*)”|「([^」\n]*)」')
BLOCKQUOTE_PREFIX_RE = re.compile(r"^(\s*>)+")
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")
HIGHLIGHT_RE = re.compile(r"==[^=\n]+==")
BULLET_RE = re.compile(r"^\s*[-*+] ")
# A list item line, as the paragraph splitter breaks on it.
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.) ")
# cited_quotes holds each inline code span as <CODE_HOLD><index><CODE_HOLD> (a private-use character).
CODE_HOLD = "\ue001"
CODE_HOLD_RE = re.compile(rf"{CODE_HOLD}(\d+){CODE_HOLD}")


# ---------------------------------------------------------------- markers


Mark = tuple[int, bool, str]  # (line index, is_close, name)


def _marker_lines(lines: list[str]) -> list[Mark]:
    """(line index, is_close, name) of every marker line outside fenced code blocks."""
    out: list[Mark] = []
    for i, (line, fenced) in enumerate(zip(lines, fenced_lines(lines))):
        if fenced:
            continue
        m = MARKER_RE.match(line)
        if m:
            out.append((i, m.group(1) == "/", m.group(2)))
    return out


def _opens_section(mark: Mark, nxt: Mark | None) -> bool:
    """The pairing rule: a known open marker whose next marker line closes the same name."""
    _, close, name = mark
    return not close and name in MARKER_NAMES and nxt is not None and nxt[1] and nxt[2] == name


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """(name, open index, close index) of every section."""
    marks = _marker_lines(lines)
    return [(mark[2], mark[0], nxt[0]) for mark, nxt in zip(marks, marks[1:]) if _opens_section(mark, nxt)]


def marker_sections(md: str) -> dict[str, list[str]]:
    """The bodies of the marker sections, by name, in document order. Never raises."""
    lines = md.split("\n")
    out: dict[str, list[str]] = {name: [] for name in MARKER_NAMES}
    for name, start, end in _sections(lines):
        out[name].append("\n".join(lines[start + 1 : end]))
    return out


def strip_marker_sections(md: str) -> str:
    """`md` without its marker sections (marker lines and bodies): the lecture prose."""
    lines = md.split("\n")
    drop: set[int] = set()
    for _, start, end in _sections(lines):
        drop.update(range(start, end + 1))
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


def _marker_problems(lines: list[str], line_numbers: list[int]) -> list[str]:
    """Marker problems of ``lines``; ``line_numbers[i]`` is the note's own 1-based number of ``lines[i]``."""
    marks = _marker_lines(lines)
    problems: list[str] = []
    paired: set[int] = set()  # positions in `marks` that belong to a section
    seen: dict[str, int] = {}
    for k, mark in enumerate(marks):
        i, _, name = mark
        if _opens_section(mark, marks[k + 1] if k + 1 < len(marks) else None):
            paired.update((k, k + 1))
            seen[name] = seen.get(name, 0) + 1
            if name in SINGLE_MARKERS and seen[name] == 2:
                problems.append(f"line {line_numbers[i]}: second '{name}' section")
    for k, (i, close, name) in enumerate(marks):
        if k in paired:
            continue
        where = f"line {line_numbers[i]}"
        tag = f"<!-- {'/' if close else ''}tal:{name} -->"
        if name not in MARKER_NAMES:
            problems.append(f"{where}: unknown marker {tag}")
        elif close:
            problems.append(f"{where}: {tag} closes nothing")
        elif k + 1 < len(marks):
            problems.append(f"{where}: {tag} is not closed before the next marker")
        else:
            problems.append(f"{where}: {tag} is never closed")
    return problems


# ---------------------------------------------------------------- text helpers


def _split(lines: list[str]) -> tuple[list[list[int]], list[int]]:
    """Port of the v1 note_stats.sh splitter, by line index: $$ blocks join the current paragraph;
    headings, tables, blockquotes, list items and rules end one and belong to none.

    Returns the paragraphs and the non-blank lines that belong to none.
    """
    paras: list[list[int]] = []
    breaks: list[int] = []
    cur: list[int] = []
    in_math = False

    def flush() -> None:
        nonlocal cur
        if cur:
            paras.append(cur)
            cur = []

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("$$"):
            if s == "$$":
                in_math = not in_math
            cur.append(i)
        elif in_math:
            cur.append(i)
        elif not s:
            flush()
        elif PARA_BREAK_RE.match(line):
            flush()
            breaks.append(i)
        else:
            cur.append(i)
    flush()
    return paras, breaks


def _paragraphs(lines: list[str]) -> list[list[str]]:
    return [[lines[i] for i in para] for para in _split(lines)[0]]


def _is_quote_line(line: str) -> bool:
    return line.lstrip().startswith(">")


def _inline_quotes(line: str) -> list[str]:
    """Quoted spans of 15 or more characters on one line that is not a '>' line."""
    return [] if _is_quote_line(line) else _quoted_spans(line)


def _quoted_spans(line: str) -> list[str]:
    """Quoted spans of 15 or more characters on one line, marks paired left to right."""
    out = []
    for m in INLINE_QUOTE_RE.finditer(line):
        inner = next(g for g in m.groups() if g is not None)
        if len(inner) >= THRESHOLDS["quote_min_chars"]:
            out.append(inner)
    return out


def _blockquotes(lines: list[str]) -> list[tuple[int, int]]:
    """(start, end) index ranges, end exclusive, of maximal runs of '>' lines."""
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if _is_quote_line(lines[i]):
            j = i
            while j < len(lines) and _is_quote_line(lines[j]):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _without_citations(text: str) -> str:
    for c in parse(text):
        text = text.replace(c.raw, " ")
    return " ".join(text.split())


def _hold_inline_code(md: str) -> tuple[str, list[str]]:
    """``md`` without fenced code blocks, each inline code span replaced by a placeholder.

    The placeholder holds no quote mark and no parenthesis, so code is never read as a
    quote or a citation; ``_restore_inline_code`` puts each span back as written. One line
    is kept per line outside fenced blocks, as in strip_code.
    """
    spans: list[str] = []

    def hold(m: re.Match) -> str:
        spans.append(m.group(0))
        return f"{CODE_HOLD}{len(spans) - 1}{CODE_HOLD}"

    lines = md.split("\n")
    kept = [INLINE_CODE_RE.sub(hold, line) for line, fenced in zip(lines, fenced_lines(lines)) if not fenced]
    return "\n".join(kept), spans


def _restore_inline_code(text: str, spans: list[str]) -> str:
    return CODE_HOLD_RE.sub(lambda m: spans[int(m.group(1))], text)


def _list_items(lines: list[str], breaks: list[int]) -> list[list[int]]:
    """Each list item among ``breaks``: its bullet line, then the indented lines that continue it."""
    items: list[list[int]] = []
    for i in breaks:
        if not LIST_ITEM_RE.match(lines[i]):
            continue
        item = [i]
        j = i + 1
        while (
            j < len(lines)
            and lines[j][:1] in (" ", "\t")
            and lines[j].strip()
            and not LIST_ITEM_RE.match(lines[j])
            and not _is_quote_line(lines[j])
        ):
            item.append(j)
            j += 1
        items.append(item)
    return items


def cited_quotes(md: str) -> list[tuple[str, list[Citation]]]:
    """The quotes of the lecture prose that carry a citation, each with the citations that cover it.

    Read as check_note reads them: fenced code and the marker sections are left out, and
    code is never a quote or a citation. Inline code inside a quote stays in its text as
    written. A blockquote that is not a callout is cited inside or on its next non-empty
    line. An inline quote of 15 or more characters is cited by its paragraph; in a list
    item by the item (its bullet line and its indented continuation lines); on another
    line outside paragraphs (a table row, a heading) by that line; inside a callout by the
    whole callout. Citation groups are removed from the quote text. Blockquotes come
    first, then inline quotes, each in document order.
    """
    held, spans = _hold_inline_code(md)
    p_lines = strip_marker_sections(held).split("\n")
    out: list[tuple[str, list[Citation]]] = []
    inline: list[tuple[int, str, list[Citation]]] = []  # (line index, quote, citations)

    def add(group: list[int], quotes_on) -> None:
        """The quotes on the lines of ``group``, each cited by the citations of the whole group."""
        cits = parse("\n".join(p_lines[i] for i in group))
        if cits:
            inline.extend((i, q, cits) for i in group for q in quotes_on(p_lines[i]))

    for a, b in _blockquotes(p_lines):
        if CALLOUT_START_RE.match(p_lines[a]):
            add(list(range(a, b)), lambda line: _quoted_spans(BLOCKQUOTE_PREFIX_RE.sub("", line)))
            continue
        block = "\n".join(p_lines[a:b])
        after = next((x for x in p_lines[b:] if x.strip()), "")
        cits = parse(block) or parse(after)
        if cits:
            text = " ".join(BLOCKQUOTE_PREFIX_RE.sub("", line) for line in p_lines[a:b])
            out.append((_without_citations(text), cits))
    paras, breaks = _split(p_lines)
    items = _list_items(p_lines, breaks)
    continued = {i for item in items for i in item[1:]}  # read with their list item, not as a paragraph
    for para in paras:
        rest = [i for i in para if i not in continued]
        if rest:
            add(rest, _inline_quotes)
    for item in items:
        add(item, _inline_quotes)
    item_lines = {item[0] for item in items}
    for i in breaks:
        if i not in item_lines:  # '>' lines give no inline quotes here: they are read above
            add([i], _inline_quotes)
    inline.sort(key=lambda t: t[0])  # stable: quotes on one line keep their order
    out.extend((_without_citations(q), cits) for _, q, cits in inline)
    return [(_restore_inline_code(q, spans), cits) for q, cits in out]


def _is_toc_line(line: str) -> bool:
    return bool(TOC_OBSIDIAN_RE.match(line) or TOC_MARKDOWN_RE.match(line))


def _nonspace(s: str) -> int:
    return sum(1 for c in s if not c.isspace())


def _slug(h: str) -> str:
    return re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")


def _short(s: str, n: int = 60) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _num(x: float) -> str:
    """At most one decimal, without a trailing zero: 53, 133.3."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _result(name: str, status: str, offences: list[str]) -> CheckResult:
    return CheckResult(name, status if offences else "PASS", offences)


def _skipped(name: str, reason: str) -> CheckResult:
    return CheckResult(name, "PASS", [f"skipped: {reason}"])


# ---------------------------------------------------------------- rules


def _toc_problems(w_lines: list[str], target: str) -> list[str]:
    h2 = [line[3:].strip() for line in w_lines if line.startswith("## ")]
    problems: list[str] = []
    if target == "obsidian":
        names = set(h2)
        for line in w_lines:
            m = TOC_OBSIDIAN_RE.match(line)
            if m and m.group(1).strip() not in names:
                problems.append(f"TOC link [[#{m.group(1).strip()}]] matches no H2")
        return problems
    counts: dict[str, int] = {}
    h2_slugs: set[str] = set()
    for line in w_lines:
        if not HEADING_RE.match(line):
            continue
        base = _slug(line.lstrip("#"))
        n = counts.get(base, 0)
        counts[base] = n + 1
        slug = base if n == 0 else f"{base}-{n}"
        if line.startswith("## "):
            h2_slugs.add(slug)
    for line in w_lines:
        m = TOC_MARKDOWN_RE.match(line)
        if m and m.group(1) not in h2_slugs:
            problems.append(f"TOC link #{m.group(1)} matches no H2")
    return problems


def _details_problems(bodies: dict[str, list[str]]) -> list[str]:
    problems: list[str] = []
    for name in ("pretest", "check"):
        for body in bodies[name]:
            # numbered items outside <details>…</details>, as (line index, text)
            lines = body.split("\n")
            items: list[int] = []
            depth = 0
            for i, line in enumerate(lines):
                if depth == 0 and NUMBERED_ITEM_RE.match(line):
                    items.append(i)
                depth = max(0, depth + line.count("<details") - line.count("</details>"))
            for k, i in enumerate(items):
                end = items[k + 1] if k + 1 < len(items) else len(lines)
                first = NUMBERED_ITEM_RE.sub("", lines[i], count=1)
                segment = "\n".join([first, *lines[i + 1 : end]])
                if "<details" not in segment:
                    problems.append(f"{name}: item '{_short(lines[i])}' has no <details> answer")
    return problems


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def _check_args(goal: str, quote_density: str) -> None:
    if goal not in GOALS:
        raise ValueError(f"unknown goal {goal!r}; expected one of {', '.join(GOALS)}")
    if quote_density not in QUOTE_DENSITIES:
        raise ValueError(f"unknown quote_density {quote_density!r}; expected one of {', '.join(QUOTE_DENSITIES)}")


def _counts(p: str, p_lines: list[str], w_lines: list[str], lang: str) -> dict:
    """The raw numbers the per-minute and quote rules use, from the prose P and the note W."""
    inline_all = [q for line in p_lines for q in _inline_quotes(line)]
    blocks = [(a, b) for a, b in _blockquotes(p_lines) if not CALLOUT_START_RE.match(p_lines[a])]
    return {
        "units": units(p, lang),
        "times": sum(1 for c in parse(p) if c.kind == "time"),
        "quotes": len(inline_all) + len(blocks),
        "quote_chars": sum(_nonspace(q) for q in inline_all) + sum(
            _nonspace(BLOCKQUOTE_PREFIX_RE.sub("", line)) for a, b in blocks for line in p_lines[a:b]
        ),
        "nonspace": _nonspace(p),
        "h2": sum(1 for line in w_lines if line.startswith("## ")),
    }


def _length_window(goal: str, unit_key: str, duration_min: float) -> tuple[float, float]:
    lo, hi = THRESHOLDS["length_per_min"][goal][unit_key]
    return lo, max(hi, THRESHOLDS["length_ceiling_min"][unit_key] / duration_min)


def _h2_cap(duration_min: float) -> int:
    return max(THRESHOLDS["h2_per_90min"], math.ceil(THRESHOLDS["h2_per_90min"] * duration_min / 90))


def _is_cross(lang: str, lecture_lang: str | None) -> bool:
    """A CJK note of a non-CJK lecture: its quotes are measured as a ratio, not a share."""
    return lecture_lang is not None and is_cjk_language(lang) and not is_cjk_language(lecture_lang)


def measure_note(
    md: str,
    lang: str,
    goal: str,
    duration_min: float | None,
    lecture_lang: str | None = None,
    quote_density: str = "standard",
) -> dict:
    """What the per-minute and quote rules of ``check_note`` measure, with their limits.

    ``length``: the units of the lecture prose (the note without code and marker sections,
    counted by ``units``), in all and per minute, with the window. ``time_citations`` and
    ``quotes``: per minute, with the minimum. One of ``quote_ratio`` (a CJK note of a
    non-CJK lecture: quoted characters per CJK character of prose) and ``quote_share``
    (quoted characters over the prose's non-space characters) is set, the other is None.
    ``h2``: the number of H2 headings and the cap. Per-minute values and limits are None
    when the duration is unknown. Numbers are rounded to two decimals.
    """
    _check_args(goal, quote_density)
    cjk = is_cjk_language(lang)
    unit_key = "cjk" if cjk else "words"
    known = duration_min is not None and duration_min > 0
    w = strip_code(md)
    p = strip_marker_sections(w)
    n = _counts(p, p.split("\n"), w.split("\n"), lang)

    def per_min(count: int) -> float | None:
        return _round(count / duration_min) if known else None

    if _is_cross(lang, lecture_lang):
        ratio = {"value": _round(n["quote_chars"] / n["units"]) if n["units"] else None,
                 "window": list(THRESHOLDS["cross_language_quote_ratio"][quote_density])}
        share = None
    else:
        ratio = None
        share = {"value": _round(n["quote_chars"] / n["nonspace"]) if n["nonspace"] else None,
                 "window": list(THRESHOLDS["same_language_quote_share"])}
    return {
        "minutes": _round(duration_min) if known else None,
        "length": {
            "unit": "CJK characters" if cjk else "words",
            "total": n["units"],
            "per_min": per_min(n["units"]),
            "window": [_round(x) for x in _length_window(goal, unit_key, duration_min)] if known else None,
        },
        "time_citations": {"per_min": per_min(n["times"]), "min": THRESHOLDS["timestamps_per_min"][goal] if known else None},
        "quotes": {"per_min": per_min(n["quotes"]), "min": THRESHOLDS["quotes_per_min"][goal] if known else None},
        "quote_ratio": ratio,
        "quote_share": share,
        "h2": {"count": n["h2"], "max": _h2_cap(duration_min) if known else None},
    }


def check_note(
    md: str,
    lang: str,
    goal: str,
    duration_min: float | None,
    target: str,
    lecture_lang: str | None = None,
    quote_density: str = "standard",
) -> list[CheckResult]:
    """One CheckResult per rule, in a fixed order; `duration` is appended when unknown.

    ``quote_density`` (light, standard or dense) picks the quote-ratio window of a CJK
    note of a non-CJK lecture; the same-language share does not depend on it.
    """
    _check_args(goal, quote_density)
    cjk = is_cjk_language(lang)
    unit_key = "cjk" if cjk else "words"
    unit_name = "CJK characters" if cjk else "words"
    known = duration_min is not None and duration_min > 0

    w = strip_code(md)
    # strip_code keeps one line per line outside fenced blocks: map W's lines back to the note's.
    raw_lines = md.split("\n")
    w_line_numbers = [n for n, fenced in enumerate(fenced_lines(raw_lines), 1) if not fenced]
    p = strip_marker_sections(w)
    bodies = marker_sections(w)
    w_lines = w.split("\n")
    p_lines = p.split("\n")
    paras = _paragraphs(p_lines)

    results: list[CheckResult] = []

    # -- FAIL rules
    results.append(_result("markers", "FAIL", _marker_problems(w_lines, w_line_numbers)))
    results.append(_result("h4", "FAIL", [f"H4 or deeper: {_short(x)}" for x in w_lines if H4_RE.match(x)]))
    results.append(
        _result(
            "numbered_heading",
            "FAIL",
            [f"numbered heading: {_short(x)}" for x in w_lines if NUMBERED_HEADING_RE.match(x)],
        )
    )
    bad_callouts = []
    for line in w_lines:
        m = CALLOUT_RE.match(line)
        if m and m.group(1).upper() not in CALLOUT_TYPES:
            bad_callouts.append(f"callout type [!{m.group(1)}] is not allowed")
    results.append(_result("callout_type", "FAIL", bad_callouts))
    results.append(_result("toc_mismatch", "FAIL", _toc_problems(w_lines, target)))
    results.append(_result("details_missing", "FAIL", _details_problems(bodies)))

    para_quotes = [[q for line in para for q in _inline_quotes(line)] for para in paras]
    results.append(
        _result(
            "quotes_per_paragraph",
            "FAIL",
            [
                f"{len(qs)} quotes in paragraph '{_short(para[0])}'"
                for para, qs in zip(paras, para_quotes)
                if len(qs) > THRESHOLDS["quotes_per_paragraph"]
            ],
        )
    )

    blocks = [
        (a, b) for a, b in _blockquotes(p_lines) if not CALLOUT_START_RE.match(p_lines[a])
    ]
    uncited_blocks = []
    for a, b in blocks:
        text = "\n".join(p_lines[a:b])
        after = next((x for x in p_lines[b:] if x.strip()), "")
        if not parse(text) and not parse(after):
            uncited_blocks.append(f"blockquote '{_short(p_lines[a])}' has no citation")
    results.append(_result("uncited_blockquote", "FAIL", uncited_blocks))
    results.append(
        _result(
            "uncited_quote",
            "FAIL",
            [
                f"quote in paragraph '{_short(para[0])}' has no citation"
                for para, qs in zip(paras, para_quotes)
                if qs and not parse("\n".join(para))
            ],
        )
    )

    # -- WARN rules
    counts = _counts(p, p_lines, w_lines, lang)
    quote_count, quote_chars, p_units = counts["quotes"], counts["quote_chars"], counts["units"]

    if known:
        lo, hi = _length_window(goal, unit_key, duration_min)
        rate = p_units / duration_min
        results.append(
            _result(
                "length",
                "WARN",
                []
                if lo <= rate <= hi
                else [f"{rate:.1f} {unit_name} per minute, expected {lo}–{_num(hi)} for {goal}"],
            )
        )
        times = counts["times"]
        t_min = THRESHOLDS["timestamps_per_min"][goal]
        results.append(
            _result(
                "timestamps",
                "WARN",
                []
                if times / duration_min >= t_min
                else [f"{times / duration_min:.2f} timestamps per minute, expected at least {t_min}"],
            )
        )
        q_min = THRESHOLDS["quotes_per_min"][goal]
        results.append(
            _result(
                "quotes",
                "WARN",
                []
                if quote_count / duration_min >= q_min
                else [f"{quote_count / duration_min:.2f} quotes per minute, expected at least {q_min}"],
            )
        )
        cap, h2 = _h2_cap(duration_min), counts["h2"]
        results.append(_result("h2_count", "WARN", [] if h2 <= cap else [f"{h2} H2 headings, at most {cap}"]))
    else:
        for name in ("length", "timestamps", "quotes", "h2_count"):
            results.append(_skipped(name, "duration unknown"))

    thin = []
    heading: str | None = None
    buf: list[str] = []

    def close_section() -> None:
        if heading is None:
            return
        text = "\n".join(x for x in buf if not _is_toc_line(x))
        if not text.strip():
            return
        n = units(text, lang)
        if n < THRESHOLDS["thin_section"][unit_key]:
            thin.append(f"section '{_short(heading)}' has {n} {unit_name}")

    for line in p_lines:
        if line.startswith("## ") or line.startswith("# "):
            close_section()
            heading = line[3:].strip() if line.startswith("## ") else None
            buf = []
        else:
            buf.append(line)
    close_section()
    results.append(_result("thin_section", "WARN", thin))

    long_limit = THRESHOLDS["long_paragraph"][unit_key]
    long_paras = []
    for para in paras:
        n = units("\n".join(para), lang)
        if n > long_limit:
            long_paras.append(f"paragraph '{_short(para[0])}' has {n} {unit_name}")
    results.append(_result("long_paragraph", "WARN", long_paras))

    bold = len(BOLD_RE.findall(p))
    results.append(
        _result(
            "bold",
            "WARN",
            [] if bold <= THRESHOLDS["bold_max"] else [f"{bold} bold spans, at most {THRESHOLDS['bold_max']}"],
        )
    )
    hl = len(HIGHLIGHT_RE.findall(p))
    hl_max = THRESHOLDS["highlights_max"] if target == "obsidian" else 0
    results.append(
        _result("highlights", "WARN", [] if hl <= hl_max else [f"{hl} ==highlights==, at most {hl_max} for {target}"])
    )
    bullets = sum(1 for line in p_lines if BULLET_RE.match(line) and not _is_toc_line(line))
    share = bullets / len(p_lines)
    results.append(
        _result(
            "bullets",
            "WARN",
            []
            if share <= THRESHOLDS["bullet_share_max"]
            else [f"{bullets} bullet lines of {len(p_lines)} ({share:.0%}), at most {THRESHOLDS['bullet_share_max']:.0%}"],
        )
    )

    if _is_cross(lang, lecture_lang):
        lo, hi = THRESHOLDS["cross_language_quote_ratio"][quote_density]
        ratio_problems = []
        if p_units:
            ratio = quote_chars / p_units
            if not lo <= ratio <= hi:
                ratio_problems.append(f"quote characters / {unit_name} = {ratio:.2f}, expected {lo}–{hi}")
        results.append(_result("quote_ratio", "WARN", ratio_problems))
        results.append(_skipped("quote_share", "cross-language note uses quote_ratio"))
    else:
        results.append(_skipped("quote_ratio", "same-language note uses quote_share"))
        lo, hi = THRESHOLDS["same_language_quote_share"]
        share_problems = []
        total = counts["nonspace"]
        if total:
            qshare = quote_chars / total
            if not lo <= qshare <= hi:
                share_problems.append(f"quote characters are {qshare:.0%} of the prose, expected {lo:.0%}–{hi:.0%}")
        results.append(_result("quote_share", "WARN", share_problems))

    if not known:
        results.append(CheckResult("duration", "WARN", ["duration unknown: per-minute checks skipped"]))
    return results
