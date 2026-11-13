"""The progress log: one JSON line per quiz attempt, unit scores, gain, retention, the due list and the page."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .items import find_item, load_items
from .plan import load_plan, safe_name
from .unit import UnitPaths

PHASES = ("pre", "post", "d1", "d7", "d21", "practice")
SCORES = (0, 0.5, 1)
CONFIDENCES = (1, 2, 3)
EXPOSURES = ("none", "attended", "watched", "unknown")

# Phases shown on the page and in the headline, with their headline labels.
TRACKED_PHASES = ("pre", "post", "d7")
HEADLINE_LABELS = {"pre": "pre", "post": "post", "d7": "day 7"}
# Review phases: days after the first post attempt, and whether the review is optional.
REVIEWS = (("d1", 1, True), ("d7", 7, False), ("d21", 21, True))
# The order of entries due on the same day: the post quiz first, then the reviews.
DUE_ORDER = {"post": 0, **{phase: n for n, (phase, _, _) in enumerate(REVIEWS, start=1)}}
STRIP_COLUMNS = 21
STRIP_MARKS = (("pre", "○"), ("post", "●"), ("d7", "◆"))  # later marks win a shared column


@dataclass
class Attempt:
    ts: str
    course: str
    unit: str
    item_id: str
    variant: str | None
    concept: str
    phase: str
    score: float
    confidence: int
    citation: str
    exposure: str


def _progress_dir(workspace: Path) -> Path:
    return Path(workspace) / "progress"


def _course_file(workspace: Path, course: str, suffix: str) -> Path:
    """``<workspace>/progress/<course><suffix>``; PlanError when ``course`` is not a safe folder name."""
    return _progress_dir(workspace) / f"{safe_name(course, 'course')}{suffix}"


def log_attempt(a: Attempt, workspace: Path) -> Path:
    """Append ``a`` as one JSON line to ``<workspace>/progress/<course>.jsonl`` and return that path."""
    # Check every value set before touching the disk, so a bad attempt leaves no trace.
    # bool is a subclass of int (True == 1) and 2.0 == 2, so the types are checked as well.
    for name, value in (("score", a.score), ("confidence", a.confidence)):
        if isinstance(value, bool):
            raise ValueError(f"attempt {name} must be a number, not {value!r}")
    if not isinstance(a.confidence, int):
        raise ValueError(f"attempt confidence must be an integer, got {a.confidence!r}")
    for name, value, allowed in (
        ("phase", a.phase, PHASES),
        ("score", a.score, SCORES),
        ("confidence", a.confidence, CONFIDENCES),
        ("exposure", a.exposure, EXPOSURES),
    ):
        if value not in allowed:
            raise ValueError(f"attempt {name} must be one of {', '.join(map(str, allowed))}, got {value!r}")
    path = _course_file(workspace, a.course, ".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(dataclasses.asdict(a), ensure_ascii=False) + "\n")
    return path


def load_attempts(course: str, workspace: Path) -> list[Attempt]:
    """The attempts of ``<workspace>/progress/<course>.jsonl`` in file order; a missing file gives []."""
    path = _course_file(workspace, course, ".jsonl")
    if not path.exists():
        return []
    # Split on "\n" only: str.splitlines() also breaks at U+2028/U+2029/U+0085, which
    # json.dumps(ensure_ascii=False) leaves raw inside string values.
    return [
        Attempt(**json.loads(line))
        for line in path.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]


def log_from_unit(
    unit: Path, item_id: str, phase: str, score: float, confidence: int, exposure: str, workspace: Path
) -> Attempt:
    """Log one attempt at ``item_id``; course, unit, variant, concept and citation come from the unit's files."""
    paths = UnitPaths(unit)
    plan = load_plan(paths.plan)
    item = find_item(load_items(paths.items), item_id)
    a = Attempt(
        ts=datetime.now().astimezone().isoformat(timespec="seconds"),
        course=plan.course,
        unit=plan.unit,
        item_id=item.id,
        variant=item.variant,
        concept=item.concept,
        phase=phase,
        score=score,
        confidence=confidence,
        citation=item.citation,
        exposure=exposure,
    )
    log_attempt(a, workspace)
    return a


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values)


def _phase_means(attempts) -> dict[str, float]:
    """Mean score per phase, phases in order of first appearance."""
    by_phase: dict[str, list[float]] = {}
    for a in attempts:
        by_phase.setdefault(a.phase, []).append(a.score)
    return {phase: _mean(scores) for phase, scores in by_phase.items()}


def unit_scores(attempts) -> dict[str, dict[str, float]]:
    """For each unit, the mean score of each phase; practice attempts are ignored."""
    by_unit: dict[str, list[Attempt]] = {}
    for a in attempts:
        if a.phase != "practice":
            by_unit.setdefault(a.unit, []).append(a)
    return {unit: _phase_means(atts) for unit, atts in by_unit.items()}


def paired_scores(attempts, first: str, second: str) -> dict[str, dict[str, float]]:
    """For each unit, the mean ``first`` and ``second`` scores over the concepts attempted in both phases.

    A concept's score in a phase is the mean of its attempts there. A unit with no such concept is left out.
    """
    by_unit: dict[str, dict[str, dict[str, list[float]]]] = {}
    for a in attempts:
        if a.phase in (first, second):
            by_unit.setdefault(a.unit, {}).setdefault(a.concept, {}).setdefault(a.phase, []).append(a.score)
    out: dict[str, dict[str, float]] = {}
    for unit, concepts in by_unit.items():
        both = [phases for phases in concepts.values() if first in phases and second in phases]
        if both:
            out[unit] = {phase: _mean(_mean(c[phase]) for c in both) for phase in (first, second)}
    return out


def normalized_gain(scores) -> float | None:
    """(mean post - mean pre) / (1 - mean pre) over the units with pre and post and pre < 1.

    ``scores`` is ``paired_scores(attempts, "pre", "post")``, so each unit compares the same concepts.
    """
    units = [s for s in scores.values() if "pre" in s and "post" in s and s["pre"] < 1]
    if not units:
        return None
    pre = _mean(s["pre"] for s in units)
    post = _mean(s["post"] for s in units)
    return (post - pre) / (1 - pre)


def retention(scores) -> float | None:
    """mean d7 / mean post over the units with both; None when none qualifies or the mean post is 0.

    ``scores`` is ``paired_scores(attempts, "post", "d7")``, so each unit compares the same concepts.
    """
    units = [s for s in scores.values() if "post" in s and "d7" in s]
    if not units:
        return None
    post = _mean(s["post"] for s in units)
    if post == 0:
        return None
    return _mean(s["d7"] for s in units) / post


def _first_days(attempts, phase: str) -> dict[str, date]:
    """Each unit's first day with an attempt in ``phase``: the date as written in ts, no timezone conversion."""
    first: dict[str, date] = {}
    for a in attempts:
        if a.phase == phase:
            day = datetime.fromisoformat(a.ts).date()
            if a.unit not in first or day < first[a.unit]:
                first[a.unit] = day
    return first


def due(attempts, today: date) -> list[dict]:
    """What is due by ``today`` and not yet attempted.

    The post quiz of a unit with a pre attempt and no post attempt, due on its first pre
    day; then d1, d7 and d21 after each unit's first post day. The optional d1 lapses
    once the unit's d7 is due or done.
    """
    done: dict[str, set[str]] = {}
    for a in attempts:
        done.setdefault(a.unit, set()).add(a.phase)
    post_day = _first_days(attempts, "post")
    out = []
    for unit, start in _first_days(attempts, "pre").items():
        if unit not in post_day and start <= today:
            out.append({"unit": unit, "phase": "post", "due": start.isoformat(), "optional": False})
    for unit, start in post_day.items():
        d7_reached = "d7" in done[unit] or start + timedelta(days=7) <= today
        for phase, days, optional in REVIEWS:
            when = start + timedelta(days=days)
            if phase == "d1" and d7_reached:
                continue
            if phase not in done[unit] and when <= today:
                out.append({"unit": unit, "phase": phase, "due": when.isoformat(), "optional": optional})
    out.sort(key=lambda e: (e["due"], e["unit"], DUE_ORDER[e["phase"]]))
    return out


def confident_but_wrong(attempts) -> list[Attempt]:
    """Attempts answered with confidence 3 and scored 0, in input order."""
    return [a for a in attempts if a.confidence == 3 and a.score == 0]


def _fmt(x: float | None) -> str:
    """Two decimals, half up; rounding to 6 decimals first keeps float noise from flipping a tie."""
    if x is None:
        return "—"
    return str(Decimal(str(round(x, 6))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _strip(pre: float | None, post: float | None, d7: float | None) -> str:
    """A 21-cell 0-100 strip with ○ pre, ● post and ◆ d7; a later mark wins a shared cell."""
    cells = ["·"] * STRIP_COLUMNS
    values = {"pre": pre, "post": post, "d7": d7}
    for phase, mark in STRIP_MARKS:
        v = values[phase]
        if v is not None:
            cells[min(STRIP_COLUMNS - 1, max(0, int(round(v * 20, 6) + 0.5)))] = mark
    return "".join(cells)


def _fence(lines: list[str]) -> str:
    return "\n".join(["```text", *lines, "```"])


def _headline(scores: dict[str, dict[str, float]], tracked: list[str], gains, retained) -> str:
    if not tracked:
        return "No tracked attempts yet."
    parts = []
    for phase in TRACKED_PHASES:
        means = [scores[u][phase] for u in tracked if phase in scores[u]]
        if means:
            parts.append(f"{HEADLINE_LABELS[phase]} {_fmt(_mean(means))}")
    line = f"Across {len(tracked)} units: " + " → ".join(parts)
    gain = normalized_gain(gains)
    if gain is not None:
        line += f"; normalized gain {_fmt(gain)}"
    ret = retention(retained)
    if ret is not None:
        line += f"; retention {_fmt(ret)}"
    return line + "."


def _unit_row(unit: str, s: dict[str, float], gains, retained) -> str:
    """One table row: the phase means, then gain and retention over the paired concepts."""
    pre, post, d7 = s.get("pre"), s.get("post"), s.get("d7")
    gain = normalized_gain({unit: gains[unit]}) if unit in gains else None
    ret = retention({unit: retained[unit]}) if unit in retained else None
    cells = [unit.replace("|", "\\|"), *(_fmt(x) for x in (pre, post, d7, gain, ret))]
    return "| " + " | ".join(cells) + " |"


def _concept_lines(attempts, unit: str) -> list[str]:
    by_concept: dict[str, list[Attempt]] = {}
    for a in attempts:
        if a.unit == unit and a.phase in TRACKED_PHASES:
            by_concept.setdefault(a.concept, []).append(a)
    lines = []
    for concept in sorted(by_concept):
        means = _phase_means(by_concept[concept])
        lines.append(f"{_strip(means.get('pre'), means.get('post'), means.get('d7'))}  {concept}")
    return lines


def render_progress(course: str, workspace: Path, today: date) -> Path:
    """Write the progress page ``<workspace>/progress/<course>.md`` and return its path.

    A course with no log raises FileNotFoundError and writes nothing.
    """
    if not _course_file(workspace, course, ".jsonl").exists():
        raise FileNotFoundError(f"no progress log for course {course!r}")
    attempts = load_attempts(course, workspace)
    scores = unit_scores(attempts)
    gains = paired_scores(attempts, "pre", "post")
    retained = paired_scores(attempts, "post", "d7")
    tracked = [u for u, s in scores.items() if any(p in s for p in TRACKED_PHASES)]

    blocks = [f"# Progress — {course}", _headline(scores, tracked, gains, retained)]
    if tracked:
        table = ["| unit | pre | post | d7 | gain | retention |", "|---|---|---|---|---|---|"]
        table += [_unit_row(u, scores[u], gains, retained) for u in tracked]
        strips = [f"{_strip(*(scores[u].get(p) for p in TRACKED_PHASES))}  {u}" for u in tracked]
        blocks += [
            "## Units",
            "\n".join(table),
            "Each strip runs from 0 to 100 in 21 columns: ○ pre, ● post, ◆ day 7.",
            _fence(strips),
            "## By concept",
        ]
        for u in tracked:
            blocks += [f"### {u}", _fence(_concept_lines(attempts, u))]

    due_lines = [
        f"- {e['unit']}: {e['phase']}{' (optional)' if e['optional'] else ''}, due {e['due']}"
        for e in due(attempts, today)
    ]
    blocks += ["## Due today", "\n".join(due_lines) or "None."]
    wrong_lines = [
        f"- {a.unit}: {a.item_id} ({a.concept}), {a.phase}, {a.citation}" for a in confident_but_wrong(attempts)
    ]
    blocks += ["## Confident but wrong", "\n".join(wrong_lines) or "None."]

    path = _course_file(workspace, course, ".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8", newline="\n")
    return path
