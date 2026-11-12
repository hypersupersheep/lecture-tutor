"""Citations in a note: (slide 15), (13:42–14:05), (~13:40), ([13:42](URL)) and mixes.

`parse` finds them, `resolve` checks them against the slide count and the duration.
Pure functions, standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TIME = r"\d{1,2}:\d{2}(?::\d{2})?"
TIME_RE = re.compile(TIME)
# A time token: a bare timestamp, or a Markdown link whose text is the timestamp.
# The URL is ignored; it contains no spaces or parentheses.


def _token(n: str) -> str:
    return rf"(?:\[(?P<{n}l>{TIME})\]\([^()\s]*\)|(?P<{n}b>{TIME}))"


DASH = r"\s*[-–]\s*"
PART_RE = re.compile(
    rf"(?P<slide>slides?\s+(?P<s1>\d+)(?:{DASH}(?P<s2>\d+))?)"
    rf"|(?P<time>(?P<tilde>~)?\s*{_token('a')}(?:{DASH}{_token('z')})?)",
    re.IGNORECASE,
)
SEP_RE = re.compile(r"\s*[,，]\s*")
LINK = r"\[[^\]\n]*\]\([^()\s]*\)"
# A parenthesised group on one line; a Markdown link inside it keeps its own parentheses.
GROUP_RE = re.compile(rf"\((?P<a>(?:{LINK}|[^()（）\n])*)\)|（(?P<b>(?:{LINK}|[^()（）\n])*)）")


@dataclass
class Citation:
    kind: str  # "slide" or "time"
    start: float | str
    end: float | str | None
    estimated: bool
    raw: str
    line: int


def _seconds(t: str) -> float:
    parts = [int(p) for p in t.split(":")]
    if len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return float(parts[0] * 60 + parts[1])


def _parse_group(content: str, raw: str, line: int) -> list[Citation]:
    """All parts of one group, or [] when its content is not a citation list."""
    out: list[Citation] = []
    pos = len(content) - len(content.lstrip())  # leading whitespace is allowed
    while True:
        m = PART_RE.match(content, pos)
        if not m:
            return []
        if m.group("slide"):
            s2 = m.group("s2")
            out.append(Citation("slide", m.group("s1"), s2, False, raw, line))
        else:
            start = m.group("al") or m.group("ab")
            end = m.group("zl") or m.group("zb")
            out.append(
                Citation(
                    "time",
                    _seconds(start),
                    _seconds(end) if end else None,
                    m.group("tilde") is not None,
                    raw,
                    line,
                )
            )
        if not content[m.end() :].strip():
            return out
        sep = SEP_RE.match(content, m.end())
        if not sep:
            return []
        pos = sep.end()


def parse(md: str) -> list[Citation]:
    """Every citation in `md`, in document order. Code is not skipped here."""
    out: list[Citation] = []
    for g in GROUP_RE.finditer(md):
        content = g.group("a") if g.group("a") is not None else g.group("b")
        line = md.count("\n", 0, g.start()) + 1
        out.extend(_parse_group(content, g.group(0), line))
    return out


def _fmt_duration(d: float) -> str:
    total = int(d)
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _as_written(raw: str, seconds: float) -> str:
    for tok in TIME_RE.findall(raw):
        if _seconds(tok) == seconds:
            return tok
    return _fmt_duration(seconds)


def resolve(cits: list[Citation], max_slide: int | None, duration: float | None) -> list[str]:
    """Problems with the citations, in citation order (start before end)."""
    problems: list[str] = []
    for c in cits:
        if c.kind == "slide":
            if max_slide is None:
                continue
            n = max(int(c.start), int(c.end)) if c.end is not None else int(c.start)
            if n > max_slide:
                problems.append(f"slide {n} > {max_slide}")
        elif duration is not None:
            for t in (c.start, c.end):
                if t is not None and t > duration + 2:
                    problems.append(f"{_as_written(c.raw, t)} > duration {_fmt_duration(duration)}")
    return problems
