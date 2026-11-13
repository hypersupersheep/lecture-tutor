"""The plan.json schema: what a unit teaches, in which languages, and which concepts are tracked."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

GOALS = ("deep", "exam", "quick")
OUTPUT_TARGETS = ("markdown", "obsidian")
TRACKED_MAX = 5
LANGUAGE_RE = re.compile(r"[a-z]{2,3}")  # applied with fullmatch
# Characters no folder name may hold on Windows, macOS or Linux; below U+0020 is checked apart.
UNSAFE_NAME_CHARS = frozenset('/\\:*?"<>|')
# Windows device names: no file or folder may be called one, with or without an extension.
WINDOWS_DEVICE_NAMES = frozenset(
    ["con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))]
)


class PlanError(Exception):
    """plan.json is malformed. The message names the offending key or value."""


def read_json(path, name: str, error: type[Exception] = ValueError):
    """Parse the JSON file ``path``, whose file name is ``name``; a leading byte-order mark is accepted.

    A missing file raises FileNotFoundError. Bytes that are not UTF-8 and invalid JSON
    raise ``error`` with a one-line message that starts with ``name``.
    """
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise error(f"{name}: not UTF-8 text: {e}") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise error(f"{name}: not valid JSON: {e}") from None


def read_text(path, name: str) -> str:
    """The UTF-8 text file ``path``, whose file name is ``name``, without a leading byte-order mark.

    A missing file raises FileNotFoundError; bytes that are not UTF-8 raise
    ValueError("<name>: not valid UTF-8").
    """
    try:
        return Path(path).read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(f"{name}: not valid UTF-8") from None


def safe_name(value: str, what: str) -> str:
    """Return ``value`` when it can be a folder or file name on every platform, else raise PlanError.

    ``what`` is "course" or "unit": both become folder and file names under the workspace.
    """
    ok = (
        isinstance(value, str)
        and value != ""
        and value == value.strip()
        and not any(c in UNSAFE_NAME_CHARS or c < " " for c in value)
        and value not in (".", "..")
        and not value.endswith(".")
    )
    if not ok:
        raise PlanError(
            f"{what} name {value!r} cannot be a folder name: "
            "avoid / \\ : * ? \" < > | and leading or trailing spaces or dots"
        )
    if value.split(".", 1)[0].lower() in WINDOWS_DEVICE_NAMES:
        raise PlanError(f"{what} name {value!r} cannot be a folder name: it is a Windows device name")
    return value


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
    if not LANGUAGE_RE.fullmatch(value):
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
        if not isinstance(concept["id"], str):
            raise PlanError(f"plan.json: concept {n} id must be a string, got {concept['id']!r}")
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
    if not Path(path).exists():
        raise FileNotFoundError(f"plan.json: not found in {Path(path).parent}")
    data = read_json(path, "plan.json", PlanError)
    if not isinstance(data, dict):
        raise PlanError("plan.json: the top level must be an object")
    missing = [key for key in FIELDS if key not in data]
    if missing:
        raise PlanError(f"plan.json: missing key(s): {', '.join(missing)}")

    try:
        safe_name(data["course"], "course")
        safe_name(data["unit"], "unit")
    except PlanError as e:
        raise PlanError(f"plan.json: {e}") from None
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
    outputs = data["outputs"]
    if not isinstance(outputs, list) or not all(isinstance(x, str) for x in outputs):
        raise PlanError(f"plan.json: outputs must be a list of strings, got {outputs!r}")
    _check_tracked(data["concepts"], data["tracked"])

    fields = {key: data[key] for key in FIELDS}
    fields["duration_s"] = None if duration is None else float(duration)
    return Plan(**fields)
