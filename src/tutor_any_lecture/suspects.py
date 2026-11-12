"""ASR suspects: transcript words that look like a misheard slide term.

Flag only, never fix: the transcript is read and left byte-identical. The agent turns
sources/suspects.json into the errata table of the note.
"""

from __future__ import annotations

import difflib
import json
import unicodedata
from pathlib import Path

from .slides import Page, load_pages, term_list
from .transcript import Transcript
from .unit import UnitPaths

THRESHOLD = 0.8
CJK_RANGES = ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF))


def norm(s: str) -> str:
    """Compare form: NFKD, combining marks removed, casefolded (ignores case and diacritics)."""
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if unicodedata.combining(c) == 0).casefold()


def _is_cjk(c: str) -> bool:
    cp = ord(c)
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


def _tokens(text: str) -> list[str]:
    """Latin words and CJK 2-4-grams, in order of occurrence.

    A run is a maximal stretch of letters of one script (CJK or not). Digits,
    punctuation and whitespace end a run, and so does a change of script.
    Punctuation inside the CJK ranges (U+30FB "・", U+30A0 "゠") ends a run too.
    """
    runs: list[tuple[str, bool]] = []
    current: list[str] = []
    current_cjk = False
    for c in text:
        cjk = _is_cjk(c) and not unicodedata.category(c).startswith("P")
        if cjk or c.isalpha():
            if current and cjk != current_cjk:
                runs.append(("".join(current), current_cjk))
                current = []
            current.append(c)
            current_cjk = cjk
        elif current:
            runs.append(("".join(current), current_cjk))
            current = []
    if current:
        runs.append(("".join(current), current_cjk))

    tokens: list[str] = []
    for run, cjk in runs:
        if not cjk:
            tokens.append(run)
            continue
        for start in range(len(run)):
            for size in (2, 3, 4):
                if start + size <= len(run):
                    tokens.append(run[start:start + size])
    return tokens


def _best_match(key: str, matchers: list[tuple[str, difflib.SequenceMatcher]]) -> tuple[str, float]:
    """The slide term closest to ``key`` and its ratio; ties go to the earlier term.

    Each matcher holds one normalised term as its second sequence. Terms whose quick
    upper bounds are already below the threshold are skipped: they cannot be flagged,
    and a best ratio below the threshold is never reported.
    """
    best_term, best = matchers[0][0], -1.0
    for term, matcher in matchers:
        matcher.set_seq1(key)
        if matcher.real_quick_ratio() < THRESHOLD or matcher.quick_ratio() < THRESHOLD:
            continue
        ratio = matcher.ratio()
        if ratio > best:
            best_term, best = term, ratio
    return best_term, best


def flag_suspects(transcript: Transcript, pages: list[Page], lang: str) -> list[dict]:
    """Transcript tokens close to, but not found in, the slides.

    ``lang`` is kept for the interface; tokens are chosen by script, so it has no effect in M1.
    """
    terms = term_list(pages)
    if not terms:
        return []
    # Token first, term second, as in SequenceMatcher(None, norm(token), norm(term), autojunk=False).
    matchers = [(t, difflib.SequenceMatcher(None, "", norm(t), autojunk=False)) for t in terms]
    slide_text = norm("\n".join(p.text for p in pages))

    # One computation per distinct normalised token: None means "not a suspect".
    cache: dict[str, tuple[str, float] | None] = {}
    found: list[dict] = []
    for segment in transcript.segments:
        reported: set[str] = set()
        for token in _tokens(segment.text):
            key = norm(token)
            if key in reported:
                continue
            if key not in cache:
                if key in slide_text:
                    cache[key] = None
                else:
                    term, ratio = _best_match(key, matchers)
                    cache[key] = (term, ratio) if ratio >= THRESHOLD else None
            hit = cache[key]
            if hit is None:
                continue
            reported.add(key)
            found.append({"time": float(segment.start), "heard": token, "nearest": hit[0], "ratio": round(hit[1], 3)})
    return found


def write_suspects(unit: Path) -> list[dict]:
    """Flag the unit's transcript against its slides and write sources/suspects.json."""
    paths = UnitPaths(unit)
    if not paths.transcript.is_file():
        raise FileNotFoundError(f"transcript not found: {paths.transcript}; run an acquisition first")
    transcript = Transcript.from_json(paths.transcript)
    pages = load_pages(unit)
    found = flag_suspects(transcript, pages, transcript.language or "")
    paths.suspects.parent.mkdir(parents=True, exist_ok=True)
    paths.suspects.write_text(json.dumps(found, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return found
