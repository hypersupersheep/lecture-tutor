"""The unit folder contract: fixed file names inside one lecture unit."""

from __future__ import annotations

from pathlib import Path


class UnitPaths:
    """Paths of the files in a unit folder. Only ``ensure()`` touches the disk."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def transcript(self) -> Path:
        return self.root / "sources" / "transcript.json"

    @property
    def source(self) -> Path:
        return self.root / "sources" / "source.json"

    @property
    def chapters(self) -> Path:
        return self.root / "sources" / "chapters.json"

    @property
    def suspects(self) -> Path:
        return self.root / "sources" / "suspects.json"

    @property
    def pages(self) -> Path:
        return self.root / "sources" / "slides" / "pages.json"

    @property
    def plan(self) -> Path:
        return self.root / "plan.json"

    @property
    def explanation(self) -> Path:
        return self.root / "explanation.md"

    @property
    def items(self) -> Path:
        return self.root / "items.json"

    @property
    def assignment(self) -> Path:
        return self.root / "assignment.json"

    @property
    def cards_json(self) -> Path:
        return self.root / "cards.json"

    @property
    def cards_tsv(self) -> Path:
        return self.root / "cards.tsv"

    @property
    def map(self) -> Path:
        return self.root / "map.json"

    @property
    def mermaid(self) -> Path:
        return self.root / "overview.mmd"

    @property
    def verify(self) -> Path:
        return self.root / "verify.json"

    def ensure(self) -> UnitPaths:
        """Create ``sources/slides/`` (and its parents) and return ``self``."""
        (self.root / "sources" / "slides").mkdir(parents=True, exist_ok=True)
        return self
