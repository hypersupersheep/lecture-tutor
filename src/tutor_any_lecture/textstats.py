"""Language-aware text measures: units (CJK characters or words), n-grams, overlap.

Pure functions, standard library only. Code, LaTeX and URLs never count as prose.
"""

from __future__ import annotations

import re

CJK_LANGS = {"zh", "ja", "ko"}
CJK_RE = re.compile(r"[㐀-䶿一-鿿぀-ヿ가-힯]")
WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
ALNUM_RE = re.compile(r"[^\W_]")

_FENCE_OPEN_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"(`+).+?\1")

DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
BRACKET_MATH_RE = re.compile(r"\\\[.*?\\\]", re.DOTALL)
PAREN_MATH_RE = re.compile(r"\\\(.*?\\\)", re.DOTALL)
# Inline $…$ on one line: opening $ before a non-space, closing $ after a non-space and
# not before a digit, so "$5 and $10" is left alone.
INLINE_MATH_RE = re.compile(r"\$(?=\S)[^$\n]*?(?<=\S)\$(?!\d)")
MD_LINK_URL_RE = re.compile(r"(!?\[[^\]\n]*\])\([^)\n]*\)")
ANGLE_URL_RE = re.compile(r"<https?://[^>\s]*>")
BARE_URL_RE = re.compile(r"https?://\S+")


def is_cjk_language(lang: str) -> bool:
    """True when the primary subtag of `lang` is zh, ja or ko ("zh-CN" yes, "auto" no)."""
    primary = re.split(r"[-_]", (lang or "").lower(), maxsplit=1)[0]
    return primary in CJK_LANGS


def fenced_lines(lines: list[str]) -> list[bool]:
    """For each line, whether it belongs to a fenced code block (its fences included).

    The one fence rule of the package: a fence opens on a line matching ^\\s*(```|~~~)
    and closes on the next line that, after its leading whitespace, starts with the same
    three characters (an indented or longer fence closes it too), or at the end of the text.
    """
    out: list[bool] = []
    fence: str | None = None
    for line in lines:
        if fence is not None:
            out.append(True)
            if line.lstrip().startswith(fence):
                fence = None
            continue
        m = _FENCE_OPEN_RE.match(line)
        if m:
            fence = m.group(1)
        out.append(m is not None)
    return out


def strip_code(md: str) -> str:
    """Drop fenced code blocks whole and delete inline code spans.

    Every line outside a fenced block is kept, so the result has one line per such line.
    """
    lines = md.split("\n")
    return "\n".join(
        INLINE_CODE_RE.sub("", line) for line, fenced in zip(lines, fenced_lines(lines)) if not fenced
    )


def strip_markup(text: str) -> str:
    """Remove code, LaTeX and URLs; Markdown link text stays."""
    text = strip_code(text)
    text = DISPLAY_MATH_RE.sub(" ", text)
    text = BRACKET_MATH_RE.sub(" ", text)
    text = PAREN_MATH_RE.sub(" ", text)
    text = INLINE_MATH_RE.sub(" ", text)
    text = MD_LINK_URL_RE.sub(r"\1", text)
    text = ANGLE_URL_RE.sub(" ", text)
    text = BARE_URL_RE.sub(" ", text)
    return text


def units(text: str, lang: str) -> int:
    """CJK characters for CJK languages, words otherwise, after strip_markup."""
    clean = strip_markup(text)
    if is_cjk_language(lang):
        return len(CJK_RE.findall(clean))
    return len(WORD_RE.findall(clean))


def ngrams(text: str, lang: str) -> set[str]:
    """CJK: character 3-grams over letters and digits. Otherwise: word 2-grams."""
    low = text.lower()
    if is_cjk_language(lang):
        chars = "".join(ALNUM_RE.findall(low))
        return {chars[i : i + 3] for i in range(len(chars) - 2)}
    words = WORD_RE.findall(low)
    return {f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)}


def containment(a: str, b: str, lang: str) -> float:
    """|A∩B| / |A| over n-grams; 0.0 when A is empty."""
    na, nb = ngrams(a, lang), ngrams(b, lang)
    if not na:
        return 0.0
    return len(na & nb) / len(na)


def _char_norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def char_jaccard(a: str, b: str) -> float:
    """Jaccard of character 3-grams, lowercased, whitespace collapsed, punctuation kept.

    When both texts are too short for a 3-gram: 1.0 if they are equal, else 0.0.
    """
    na, nb = _char_norm(a), _char_norm(b)
    ga = {na[i : i + 3] for i in range(len(na) - 2)}
    gb = {nb[i : i + 3] for i in range(len(nb) - 2)}
    union = ga | gb
    if not union:
        return 1.0 if na == nb else 0.0
    return len(ga & gb) / len(union)
