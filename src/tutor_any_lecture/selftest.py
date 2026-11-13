"""Run the bundled sample unit through the offline pipeline, up to the delivery gate.

``run_selftest`` copies the sample shipped in ``data/sample/`` into a unit folder and
runs import → slides → items assign → cards export → map mermaid → verify on it. It
needs no ASR, no network, no profile and no config dir, so it also runs from an
installed wheel on a fresh machine.
"""

from __future__ import annotations

import json
import tempfile
from importlib import resources
from pathlib import Path
from shutil import rmtree

from .acquire.importer import import_transcript
from .cards import export_tsv
from .conceptmap import load_map, to_mermaid
from .items import assign_variants, load_items
from .plan import load_plan
from .slides import extract_pdf
from .unit import UnitPaths
from .verify import run_verify

# Sample files copied to the unit root, and the inputs copied to <unit>/sources/.
ROOT_FILES = ("plan.json", "explanation.md", "items.json", "cards.json", "map.json")
SOURCE_FILES = ("lecture.vtt", "slides.pdf")


def _read_sample() -> dict[str, bytes]:
    """Every sample file's bytes, by name. Raises FileNotFoundError when one is missing."""
    sample = resources.files("tutor_any_lecture").joinpath("data", "sample")
    out: dict[str, bytes] = {}
    for name in SOURCE_FILES + ROOT_FILES:
        f = sample.joinpath(name)
        if not f.is_file():
            raise FileNotFoundError(f"sample file missing from the package: data/sample/{name}")
        out[name] = f.read_bytes()
    return out


def _copy_sample(files: dict[str, bytes], unit: Path) -> None:
    (unit / "sources").mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = unit / "sources" / name if name in SOURCE_FILES else unit / name
        target.write_bytes(data)


def _run_steps(unit: Path) -> list[dict]:
    """Run the six steps in order and stop at the first one that fails."""
    paths = UnitPaths(unit)
    state: dict = {}

    def import_step() -> tuple[bool, str]:
        # The plan is loaded once, here, and reused by "items assign".
        state["plan"] = plan = load_plan(paths.plan)
        h = import_transcript(unit / "sources" / "lecture.vtt", unit, float(plan.duration_s), False)
        verdict = "healthy" if h.ok else "unhealthy"
        return h.ok, f"transcript {verdict} (coverage {h.coverage:.2f}, repetition {h.repetition:.2f})"

    def slides_step() -> tuple[bool, str]:
        pages = extract_pdf(unit / "sources" / "slides.pdf", unit)
        return bool(pages), f"{len(pages)} pages"

    def assign_step() -> tuple[bool, str]:
        plan = state["plan"]
        obj = assign_variants(load_items(paths.items), f"{plan.course}|{plan.unit}")
        paths.assignment.write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return paths.assignment.is_file(), paths.assignment.name

    def cards_step() -> tuple[bool, str]:
        path = export_tsv(unit)
        return path.exists(), path.name

    def map_step() -> tuple[bool, str]:
        paths.mermaid.write_text(to_mermaid(load_map(paths.map)), encoding="utf-8", newline="\n")
        return paths.mermaid.is_file(), paths.mermaid.name

    def verify_step() -> tuple[bool, str]:
        result = run_verify(unit)
        ok = result["overall"] == "PASS"
        failed = [c["name"] for c in result["checks"] if c["status"] == "FAIL"]
        detail = result["report"] if ok else f"{result['report']} FAIL: {', '.join(failed)}"
        return ok, detail

    steps: list[dict] = []
    for name, step in (
        ("import", import_step),
        ("slides", slides_step),
        ("items assign", assign_step),
        ("cards export", cards_step),
        ("map mermaid", map_step),
        ("verify", verify_step),
    ):
        try:
            ok, detail = step()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        steps.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            break
    return steps


def _run(files: dict[str, bytes], unit: Path) -> dict:
    _copy_sample(files, unit)
    steps = _run_steps(unit)
    return {"ok": len(steps) == 6 and all(s["ok"] for s in steps), "steps": steps}


def run_selftest(tmp: Path | None = None) -> dict:
    """Generate the sample unit and run the offline pipeline on it.

    With ``tmp``, the unit is generated in that folder (created if missing) and left
    there; a ``tmp`` that exists and is not an empty directory raises FileExistsError
    before anything is written. Without it, a temporary folder is used and removed.
    """
    if tmp is not None:
        tmp = Path(tmp)
        if tmp.exists() and (not tmp.is_dir() or any(tmp.iterdir())):
            raise FileExistsError(f"{tmp} exists and is not empty; pick a new or empty folder")
    files = _read_sample()
    if tmp is not None:
        tmp.mkdir(parents=True, exist_ok=True)
        return _run(files, tmp)
    d = Path(tempfile.mkdtemp(prefix="tutor-any-lecture-selftest-"))
    try:
        return _run(files, d / "unit")
    finally:
        # A cleanup that fails (a file Windows still holds open, a folder that refuses
        # removal) never changes the result: what cannot be removed stays in the system
        # temp folder.
        try:
            rmtree(d)
        except OSError:
            pass
