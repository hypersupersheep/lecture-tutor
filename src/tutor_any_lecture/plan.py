"""The plan.json schema: what a unit teaches, in which languages, and which concepts are tracked."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

GOALS = ("deep", "exam", "quick")
OUTPUT_TARGETS = ("markdown", "obsidian")
TRACKED_MAX = 5
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")


class PlanError(Exception):
    """plan.json is malformed. The message names the offending key or value."""


@dataclass
class Plan:
    course: str
    unit: str
    goal: str
    content_type: str
    note_language: str
    lecture_language: str
    duration_s: float | None
    outputs: list[str]
    sections: list[dict]
    concepts: list[dict]
    tracked: list[str]
    output_target: str


FIELDS = (
    "course", "unit", "goal", "content_type", "note_language", "lecture_language",
    "duration_s", "outputs", "sections", "concepts", "tracked", "output_target",
)


def _check_language(key: str, value) -> None:
    if not isinstance(value, str):
        raise PlanError(f"plan.json: {key} must be a string, got {value!r}")
    if value.lower() == "auto":
        raise PlanError(f"plan.json: {key} must be a concrete language code, not {value!r}")
    if not LANGUAGE_RE.match(value):
        raise PlanError(f"plan.json: {key} must be a lowercase primary subtag such as 'en' or 'zh', got {value!r}")


def _check_tracked(concepts, tracked) -> None:
    if not isinstance(concepts, list):
        raise PlanError("plan.json: concepts must be a list")
    if not isinstance(tracked, list):
        raise PlanError("plan.json: tracked must be a list")
    ids = []
    for n, concept in enumerate(concepts):
        if not isinstance(concept, dict) or "id" not in concept:
            raise PlanError(f"plan.json: concept {n} has no \"id\"")
        ids.append(concept["id"])
    distinct: list = []
    for cid in tracked:
        if cid not in ids:
            raise PlanError(f"plan.json: tracked names {cid!r}, which is not a concept id")
        if cid in distinct:
            raise PlanError(f"plan.json: tracked names {cid!r} twice")
        distinct.append(cid)
    want = min(TRACKED_MAX, len(concepts))
    if len(distinct) != want:
        raise PlanError(f"plan.json: tracked must hold exactly {want} concept ids, got {len(distinct)}")


def load_plan(path) -> Plan:
    """Read and check plan.json. A missing file raises FileNotFoundError; a bad one, PlanError."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise PlanError(f"plan.json: invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise PlanError("plan.json: the top level must be an object")
    missing = [key for key in FIELDS if key not in data]
    if missing:
        raise PlanError(f"plan.json: missing key(s): {', '.join(missing)}")

    _check_language("note_language", data["note_language"])
    _check_language("lecture_language", data["lecture_language"])
    if data["goal"] not in GOALS:
        raise PlanError(f"plan.json: goal must be one of {', '.join(GOALS)}, got {data['goal']!r}")
    if data["output_target"] not in OUTPUT_TARGETS:
        raise PlanError(
            f"plan.json: output_target must be one of {', '.join(OUTPUT_TARGETS)}, got {data['output_target']!r}"
        )
    duration = data["duration_s"]
    # bool is a subclass of int, but true/false is not a duration.
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float))):
        raise PlanError(f"plan.json: duration_s must be a number or null, got {duration!r}")
    _check_tracked(data["concepts"], data["tracked"])

    fields = {key: data[key] for key in FIELDS}
    fields["duration_s"] = None if duration is None else float(duration)
    return Plan(**fields)
