"""Slides: PDF pages → sources/slides/pages.json, footer labels, and slide terms."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .source import SourceInfo, sha256_file
from .transcript import AcquireError
from .unit import UnitPaths

# A footer such as "3/12" or " 3 / 12 " on the last non-empty line of a page.
FOOTER_RE = re.compile(r"^\s*(\d+)\s*/\s*\d+\s*$")


@dataclass
class Page:
    n: int  # 1-based PDF page number
    label: str | None
    text: str
    image: str | None = None


def _last_nonempty_line(text: str) -> str | None:
    for line in reversed(text.split("\n")):
        if line.strip():
            return line
    return None


def _footer_label(text: str) -> str | None:
    last = _last_nonempty_line(text)
    if last is None:
        return None
    m = FOOTER_RE.match(last)
    return m.group(1) if m else None


def extract_pdf(pdf: Path, unit: Path, images: bool = False) -> list[Page]:
    """Read every page of ``pdf`` into the unit's pages.json (and page images when asked).

    The PDF is opened and its text read before anything is created in the unit, so an
    unreadable file (not a PDF, damaged, encrypted) raises ``AcquireError`` and writes nothing.
    """
    pdf = Path(pdf)
    if not pdf.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf}")

    import importlib.metadata

    import pdfplumber  # imported here so the rest of this module stays cheap to import

    try:
        doc = pdfplumber.open(pdf)
    # pdfplumber and pdfminer raise many unrelated types on a bad file (PdfminerException,
    # PSEOF, KeyError, zlib.error, ...); this try holds only the pdfplumber calls.
    except Exception as e:
        raise AcquireError(f"{pdf.name} is not a readable PDF") from e
    with doc:
        try:
            texts = [page.extract_text() or "" for page in doc.pages]
        except Exception as e:
            raise AcquireError(f"{pdf.name} is not a readable PDF") from e

        paths = UnitPaths(unit).ensure()
        slides_dir = paths.pages.parent
        pages: list[Page] = []
        for n, (page, text) in enumerate(zip(doc.pages, texts), start=1):
            image = None
            if images:
                image = f"page-{n:03d}.png"
                # Rendering (pypdfium2 and Pillow) raises many unrelated types, as opening does.
                try:
                    page.to_image(resolution=110).save(slides_dir / image)
                except Exception as e:
                    raise AcquireError(f"could not render page {n} of {pdf.name}") from e
            pages.append(Page(n, _footer_label(text), text, image))

    payload = [dataclasses.asdict(p) for p in pages]
    paths.pages.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    if not paths.source.exists():
        SourceInfo(
            kind="slides-only",
            title=pdf.stem,
            url=None,
            platform=None,
            duration=None,
            lecture_language=None,
            acquisition="slides",
            health={},
            tool_versions={"pdfplumber": importlib.metadata.version("pdfplumber")},
            inputs_sha256={pdf.name: sha256_file(pdf)},
        ).write(paths.source)
    return pages


def load_pages(unit: Path) -> list[Page]:
    """The pages stored in the unit's pages.json, or ``[]`` when there is none."""
    path = UnitPaths(unit).pages
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Page(d["n"], d["label"], d["text"], d.get("image")) for d in data]


def max_label(pages: list[Page]) -> int:
    """The highest slide number: the footer label when present, else the page number."""
    return max((int(p.label) if p.label is not None else p.n for p in pages), default=0)


def _strip_outer(chunk: str) -> str:
    """Drop leading and trailing characters that are not letters or digits."""
    start, end = 0, len(chunk)
    while start < end and not chunk[start].isalnum():
        start += 1
    while end > start and not chunk[end - 1].isalnum():
        end -= 1
    return chunk[start:end]


def _term_class(token: str) -> int | None:
    """1: inner capital or a digit (GBM, Black-Scholes, L2); 2: a word of 6+ letters; else None."""
    if any(c.isupper() for c in token[1:]) or any(c.isdigit() for c in token):
        return 1
    if token.isalpha() and len(token) >= 6:
        return 2
    return None


def term_list(pages: list[Page]) -> list[str]:
    """Distinctive slide terms, uncapped: class 1 in first-seen order, then class 2."""
    seen: set[str] = set()
    by_class: dict[int, list[str]] = {1: [], 2: []}
    for page in pages:
        lines = page.text.split("\n")
        # Skip the footer line ("3/12"), tested on the text itself rather than page.label.
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip():
                if FOOTER_RE.match(lines[i]):
                    lines = lines[:i] + lines[i + 1:]
                break
        for line in lines:
            for chunk in line.split():
                token = _strip_outer(chunk)
                if not token:
                    continue
                cls = _term_class(token)
                if cls is None:
                    continue  # unclassed tokens are not recorded, so they never block a later spelling
                key = token.casefold()
                if key in seen:
                    continue
                seen.add(key)
                by_class[cls].append(token)
    return by_class[1] + by_class[2]


def slide_terms(pages: list[Page], limit_chars: int = 200) -> str:
    """Slide terms joined by ", ", at most ``limit_chars`` long, never cutting a term."""
    out = ""
    for term in term_list(pages):
        candidate = f"{out}, {term}" if out else term
        if len(candidate) > limit_chars:
            break
        out = candidate
    return out
