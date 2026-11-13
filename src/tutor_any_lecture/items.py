"""The items.json schema, variant assignment, phase selection and the item-bank checks.

items.json mirrors the ``load_items`` result:
``{"tracked": {concept_id: {"A": {...}, "B": {...}, ...}}, "practice": [{...}, ...]}``,
each item an object with exactly the nine ``Item`` field names.
"""

from __future__ import annotations

import dataclasses
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

from .checks import CheckResult
from .notecheck import marker_sections, strip_marker_sections
from .plan import Plan, load_plan, read_json, read_text
from .textstats import containment
from .unit import UnitPaths

KINDS = ("recall", "apply", "transfer", "predict_output", "complete_code", "which_method", "contrast")
APPLY_KINDS = tuple(k for k in KINDS if k != "recall")
LETTERS = ("A", "B", "C", "D", "E")
OVERLAP_THRESHOLD = 0.6
APPLY_SHARE_MIN = 0.5
ASSIGNED_PHASES = ("pre", "post", "d7")
OPTIONAL_PHASES = {"d1": "D", "d21": "E"}
SENTENCE_SPLIT_RE = re.compile(r"[.!?。！？\n]")
NO_NOTE = "skipped: explanation.md not written yet"
NOTE_CHECKS = ("prompt_overlap", "tracked_leak", "pretest_complete")


@dataclass
class Item:
    id: str
    concept: str
    kind: str
    prompt: str
    answer: str
    rubric: str
    citation: str
    difficulty: int
    variant: str | None


ITEM_FIELDS = frozenset(f.name for f in dataclasses.fields(Item))
# Fields the checks, the progress log and the cards use as text.
STRING_FIELDS = ("id", "concept", "prompt", "answer", "rubric", "citation")


# ---------------------------------------------------------------- loading


def _item(obj, where: str) -> Item:
    if not isinstance(obj, dict):
        raise ValueError(f"items.json: {where} is not an object")
    if set(obj) != ITEM_FIELDS:
        extra = sorted(set(obj) - ITEM_FIELDS)
        missing = sorted(ITEM_FIELDS - set(obj))
        raise ValueError(f"items.json: {where} has wrong keys (missing: {missing}, unexpected: {extra})")
    for field in STRING_FIELDS:
        if not isinstance(obj[field], str):
            raise ValueError(f"items.json: item {obj['id']!r}: {field} must be a string")
    if obj["kind"] not in KINDS:
        raise ValueError(f"items.json: {where} has unknown kind {obj['kind']!r}")
    return Item(**obj)


def load_items(path) -> dict:
    """Read and check items.json. A missing file raises FileNotFoundError; a bad one, ValueError."""
    data = read_json(path, "items.json")
    if not isinstance(data, dict) or not isinstance(data.get("tracked"), dict) or not isinstance(
        data.get("practice"), list
    ):
        raise ValueError('items.json: the top level must be an object with a "tracked" object and a "practice" list')

    out: dict = {"tracked": {}, "practice": []}
    seen: set[str] = set()

    def note_id(it: Item) -> None:
        if it.id in seen:
            raise ValueError(f"items.json: item id {it.id!r} occurs twice")
        seen.add(it.id)

    for cid, variants in data["tracked"].items():
        if not isinstance(variants, dict):
            raise ValueError(f"items.json: tracked concept {cid} is not an object")
        out["tracked"][cid] = {}
        for letter, obj in variants.items():
            if letter not in LETTERS:
                raise ValueError(f"items.json: tracked concept {cid} has letter key {letter!r}, not one of A-E")
            it = _item(obj, f"tracked item {cid}/{letter}")
            if it.variant != letter:
                raise ValueError(f"items.json: tracked item {cid}/{letter} has variant {it.variant!r}")
            if it.concept != cid:
                raise ValueError(f"items.json: tracked item {cid}/{letter} has concept {it.concept!r}")
            note_id(it)
            out["tracked"][cid][letter] = it
    for n, obj in enumerate(data["practice"]):
        it = _item(obj, f"practice item {n}")
        if it.variant is not None:
            raise ValueError(f"items.json: practice item {it.id} has variant {it.variant!r}, not null")
        note_id(it)
        out["practice"].append(it)
    return out


def find_item(items: dict, item_id: str) -> Item:
    """The item with this id among every tracked variant and the practice list."""
    for variants in items["tracked"].values():
        for it in variants.values():
            if it.id == item_id:
                return it
    for it in items["practice"]:
        if it.id == item_id:
            return it
    raise KeyError(item_id)


def _check_assignment(assignment, phases) -> None:
    """Raise ValueError naming the missing or wrong key when ``assignment`` lacks a phase letter."""
    if not isinstance(assignment, dict):
        raise ValueError("assignment.json: the top level must be an object")
    if "concepts" not in assignment:
        raise ValueError('assignment.json: no "concepts" key')
    if not isinstance(assignment["concepts"], dict):
        raise ValueError('assignment.json: "concepts" is not an object')
    for cid, letters in assignment["concepts"].items():
        if not isinstance(letters, dict):
            raise ValueError(f"assignment.json: concept {cid} is not an object")
        for phase in phases:
            if phase not in letters:
                raise ValueError(f'assignment.json: concept {cid} has no "{phase}"')
            if not isinstance(letters[phase], str):
                raise ValueError(f'assignment.json: concept {cid} "{phase}" is not a letter: {letters[phase]!r}')


# ---------------------------------------------------------------- checks


def _sentences(text: str) -> list[str]:
    return SENTENCE_SPLIT_RE.split(text)


def _best_match(prompt: str, sentences: list[str], lang: str) -> tuple[float, str]:
    """The highest containment of ``prompt`` in any sentence, and that sentence."""
    best, where = 0.0, ""
    for s in sentences:
        score = containment(prompt, s, lang)
        if score > best:
            best, where = score, s
    return best, where


def _short(s: str, n: int = 60) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _result(name: str, bad_status: str, offences: list[str]) -> CheckResult:
    return CheckResult(name, bad_status if offences else "PASS", offences)


def validate_items(
    items: dict, plan: Plan, explanation_md: str | None, lang: str, assignment=None
) -> list[CheckResult]:
    """The seven item-bank checks, in a fixed order. ``explanation_md`` is the raw note.

    With no note yet (``None``), the three checks that read it pass as skipped.
    """
    if assignment is not None:
        _check_assignment(assignment, ("pre",))
    if explanation_md is None:
        results = validate_items(items, plan, "", lang, assignment)
        return [CheckResult(r.name, "PASS", [NO_NOTE]) if r.name in NOTE_CHECKS else r for r in results]

    tracked = [(cid, letter, it) for cid, variants in items["tracked"].items() for letter, it in variants.items()]
    practice = list(items["practice"])
    everything = [it for _, _, it in tracked] + practice
    sections = marker_sections(explanation_md)
    prose = _sentences(strip_marker_sections(explanation_md))
    check = _sentences("\n".join(sections["check"]))
    pretest_text = "\n".join(sections["pretest"])
    pretest = _sentences(pretest_text)
    results: list[CheckResult] = []

    # variants: every tracked concept of the plan has at least A, B and C.
    offences = []
    for cid in plan.tracked:
        if cid not in items["tracked"]:
            offences.append(f"{cid}: tracked in plan.json but has no variants in items.json")
            continue
        lacking = [x for x in ("A", "B", "C") if x not in items["tracked"][cid]]
        if lacking:
            offences.append(f"{cid}: missing variant(s) {', '.join(lacking)}")
    results.append(_result("variants", "FAIL", offences))

    # apply_share: at least half of all items are apply/transfer-type.
    n_apply = sum(1 for it in everything if it.kind in APPLY_KINDS)
    share = n_apply / len(everything) if everything else 0.0
    offences = []
    if share < APPLY_SHARE_MIN:
        offences.append(
            f"{n_apply} of {len(everything)} items ({share:.0%}) are apply/transfer-type, "
            f"under {APPLY_SHARE_MIN:.0%}"
        )
    results.append(_result("apply_share", "FAIL", offences))

    # citation: every item cites its source.
    offences = [f"{it.id}: empty citation" for it in everything if not it.citation.strip()]
    results.append(_result("citation", "FAIL", offences))

    # prompt_overlap: no prompt is copied from a sentence of the lecture prose.
    offences = []
    for it in everything:
        score, where = _best_match(it.prompt, prose, lang)
        if score >= OVERLAP_THRESHOLD:
            offences.append(f"{it.id}: prompt overlaps the lecture prose at {score:.2f}: \"{_short(where)}\"")
    results.append(_result("prompt_overlap", "FAIL", offences))

    # tracked_leak: no tracked prompt appears in a check section, and (with an
    # assignment) no tracked prompt other than its concept's pre variant appears in the pretest.
    offences = []
    for _, _, it in tracked:
        score, where = _best_match(it.prompt, check, lang)
        if score >= OVERLAP_THRESHOLD:
            offences.append(f"{it.id}: tracked prompt leaks into a check section at {score:.2f}: \"{_short(where)}\"")
    if assignment is not None:
        for cid, letter, it in tracked:
            assigned = assignment["concepts"].get(cid)
            if assigned is not None and assigned["pre"] == letter:
                continue
            score, where = _best_match(it.prompt, pretest, lang)
            if score >= OVERLAP_THRESHOLD:
                offences.append(
                    f"{it.id}: tracked prompt that is not the pre variant leaks into the pretest "
                    f"at {score:.2f}: \"{_short(where)}\""
                )
        results.append(_result("tracked_leak", "FAIL", offences))
    elif offences:
        results.append(CheckResult("tracked_leak", "FAIL", offences))
    else:
        results.append(CheckResult("tracked_leak", "PASS", ["skipped: pretest part, no assignment"]))

    # tracked_vs_practice: no practice prompt reuses a tracked prompt, in either direction.
    offences = []
    for _, _, t in tracked:
        for p in practice:
            score = max(containment(t.prompt, p.prompt, lang), containment(p.prompt, t.prompt, lang))
            if score >= OVERLAP_THRESHOLD:
                offences.append(f"{t.id} and {p.id}: tracked and practice prompts overlap at {score:.2f}")
    results.append(_result("tracked_vs_practice", "FAIL", offences))

    # pretest_complete: the pretest prints every pre variant verbatim.
    if assignment is None:
        results.append(CheckResult("pretest_complete", "PASS", ["skipped: no assignment"]))
    else:
        offences = []
        printed = _collapse(pretest_text)
        for cid in sorted(assignment["concepts"]):
            it = items["tracked"].get(cid, {}).get(assignment["concepts"][cid]["pre"])
            if it is not None and _collapse(it.prompt) not in printed:
                offences.append(f"{it.id}: pre variant of {cid} is not printed in the pretest")
        results.append(_result("pretest_complete", "WARN", offences))
    return results


# ---------------------------------------------------------------- variants and phases


def assign_variants(items: dict, seed: str) -> dict:
    """Randomly map variants A/B/C of each tracked concept to pre/post/d7, reproducibly from ``seed``."""
    rng = random.Random(seed)
    concepts = {}
    for cid in sorted(items["tracked"]):
        order = ["A", "B", "C"]
        rng.shuffle(order)
        pre, post, d7 = order
        concepts[cid] = {"pre": pre, "post": post, "d7": d7}
    return {"seed": seed, "concepts": concepts}


def next_items(items: dict, assignment, phase: str) -> list[Item]:
    """The items to ask in ``phase``: the assigned variant (pre, post, d7) or D (d1) / E (d21)."""
    if phase in OPTIONAL_PHASES:
        letter = OPTIONAL_PHASES[phase]
        return [items["tracked"][cid][letter] for cid in sorted(items["tracked"]) if letter in items["tracked"][cid]]
    if phase not in ASSIGNED_PHASES:
        raise ValueError(f"unknown phase: {phase!r}")
    _check_assignment(assignment, (phase,))
    out = []
    for cid in sorted(assignment["concepts"]):
        letter = assignment["concepts"][cid][phase]
        if cid not in items["tracked"]:
            raise ValueError(f"items.json: assignment.json names concept {cid}, which has no tracked variants")
        if letter not in items["tracked"][cid]:
            raise ValueError(f"items.json: concept {cid} has no variant {letter!r} for phase {phase}")
        out.append(items["tracked"][cid][letter])
    return out


# ---------------------------------------------------------------- one function per subcommand


def _read_assignment(path: Path):
    return read_json(path, "assignment.json")


def validate_unit(unit: Path) -> list[CheckResult]:
    """``items validate``: check the unit's item bank against its plan and note (if written yet)."""
    paths = UnitPaths(unit)
    plan = load_plan(paths.plan)
    items = load_items(paths.items)
    md = read_text(paths.explanation, "explanation.md") if paths.explanation.exists() else None
    assignment = _read_assignment(paths.assignment) if paths.assignment.exists() else None
    return validate_items(items, plan, md, plan.note_language, assignment)


def assign_unit(unit: Path, force: bool = False) -> dict:
    """``items assign``: reuse assignment.json, or (when absent or ``force``) write a new one."""
    paths = UnitPaths(unit)
    if paths.assignment.exists() and not force:
        existing = _read_assignment(paths.assignment)
        _check_assignment(existing, ASSIGNED_PHASES)
        return existing
    plan = load_plan(paths.plan)
    obj = assign_variants(load_items(paths.items), f"{plan.course}|{plan.unit}")
    paths.assignment.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return obj


def next_for_unit(unit: Path, phase: str) -> dict:
    """``items next``: the phase's items, and (d1, d21) the tracked concepts lacking that variant."""
    paths = UnitPaths(unit)
    if phase in OPTIONAL_PHASES:
        items = load_items(paths.items)
        letter = OPTIONAL_PHASES[phase]
        chosen = next_items(items, None, phase)
        missing = sorted(cid for cid, variants in items["tracked"].items() if letter not in variants)
    elif phase in ASSIGNED_PHASES:
        if not paths.assignment.exists():
            raise FileNotFoundError(
                f"{paths.assignment} not found: run `tutor-any-lecture items assign --unit DIR` first"
            )
        chosen = next_items(load_items(paths.items), _read_assignment(paths.assignment), phase)
        missing = []
    else:
        raise ValueError(f"unknown phase: {phase!r}")
    return {"phase": phase, "items": [dataclasses.asdict(i) for i in chosen], "missing": missing}


def get_from_unit(unit: Path, item_id: str) -> Item:
    """``items get``: one item of the unit's bank by id (KeyError when unknown)."""
    return find_item(load_items(UnitPaths(unit).items), item_id)
