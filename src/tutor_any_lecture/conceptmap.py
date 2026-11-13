"""The concept map: the map.json schema, its checks and the Mermaid export.

map.json is ``{"nodes": [{"id", "label", "type", "order"?, "citation"?}],
"edges": [{"from", "to", "verb"}], "views": [{"id", "nodes": [ids]}]?}``. The agent
writes it; ``validate_map`` checks it and ``to_mermaid`` turns it into a flowchart.
``citation`` is a plain string such as "slide 3" and is not used here.
"""

from __future__ import annotations

import re
from pathlib import Path

from .checks import CheckResult
from .plan import PlanError, read_json, safe_name
from .unit import UnitPaths

NODE_TYPES = ("definition", "theorem", "method", "example", "pitfall")
MAX_VIEW_NODES = 12
# A node id is written bare into the Mermaid source; "end" (any case) closes a subgraph there.
NODE_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")  # applied with fullmatch

# Mermaid node shapes by type: (opening, closing) around the quoted label.
_SHAPES = {
    "definition": ("[", "]"),
    "theorem": ("[[", "]]"),
    "method": ("(", ")"),
    "example": (">", "]"),
    "pitfall": ("{{", "}}"),
}


class UnknownView(ValueError):
    """Raised by ``to_mermaid`` when ``view_id`` names no view of the map."""


class MapInvalid(Exception):
    """Raised by ``export_mermaid`` when the map fails a check; ``results`` holds them all."""

    def __init__(self, results: list[CheckResult]) -> None:
        super().__init__("map.json failed validation")
        self.results = results


def load_map(path):
    """Parse map.json and return it unchanged. Raises FileNotFoundError, or ValueError
    ("map.json: ...") for bytes that are not UTF-8 or invalid JSON."""
    return read_json(path, "map.json")


def _result(name: str, offences: list[str]) -> CheckResult:
    return CheckResult(name, "FAIL" if offences else "PASS", offences)


def _is_text(value) -> bool:
    """A non-empty string. Checked before any value is used as an id, so nothing unhashable is hashed."""
    return isinstance(value, str) and value != ""


def _show(value) -> str:
    return value if isinstance(value, str) else repr(value)


def _edge_name(edge: dict) -> str:
    return f"{_show(edge.get('from'))} -> {_show(edge.get('to'))}"


def _check_schema(m) -> list[str]:
    """One detail per offending node, edge or view, or one for a broken top level."""
    if not isinstance(m, dict):
        return ["map is not an object"]
    offences = []
    nodes, edges, views = m.get("nodes"), m.get("edges"), m.get("views")
    if not isinstance(nodes, list):
        offences.append("nodes is missing or not a list")
    if not isinstance(edges, list):
        offences.append("edges is missing or not a list")
    if "views" in m and not isinstance(views, list):
        offences.append("views is not a list")
    if offences:
        return offences

    ids: set[str] = set()
    for n, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            offences.append(f"node #{n}: not an object")
            continue
        node_id = node.get("id")
        name = node_id if _is_text(node_id) else f"node #{n}"
        reasons = []
        if not _is_text(node_id):
            reasons.append("id is not a non-empty string")
        elif node_id in ids:
            reasons.append("duplicate id")
        if not _is_text(node.get("label")):
            reasons.append("label is not a non-empty string")
        # bool is a subclass of int, so true/false must be excluded explicitly.
        if "order" in node and (not isinstance(node["order"], int) or isinstance(node["order"], bool)):
            reasons.append("order is not an integer")
        if reasons:
            offences.append(f"{name}: {', '.join(reasons)}")
        if _is_text(node_id) and (not NODE_ID_RE.fullmatch(node_id) or node_id.lower() == "end"):
            offences.append(
                f'node id {node_id!r}: use letters, digits and underscores, starting with a letter; "end" is reserved'
            )
        if _is_text(node_id):
            ids.add(node_id)

    for n, edge in enumerate(edges, 1):
        if not isinstance(edge, dict):
            offences.append(f"edge #{n}: not an object")

    for n, view in enumerate(views or [], 1):
        if not isinstance(view, dict):
            offences.append(f"view #{n}: not an object")
            continue
        view_id = view.get("id")
        name = view_id if _is_text(view_id) else f"view #{n}"
        reasons = []
        if not _is_text(view_id):
            reasons.append("id is not a non-empty string")
        members = view.get("nodes")
        if not isinstance(members, list):
            reasons.append("nodes is not a list")
        else:
            unknown = [_show(x) for x in members if not (isinstance(x, str) and x in ids)]
            if unknown:
                reasons.append(f"unknown nodes {', '.join(unknown)}")
        if reasons:
            offences.append(f"{name}: {', '.join(reasons)}")
    return offences


def validate_map(m) -> list[CheckResult]:
    """Check a parsed map. Never raises; returns ``schema`` alone when the structure is wrong."""
    schema = _check_schema(m)
    if schema:
        return [_result("schema", schema)]

    nodes, edges, views = m["nodes"], m["edges"], m.get("views") or []
    ids = {node["id"] for node in nodes}

    bad_types = [
        node["id"] for node in nodes
        if not (isinstance(node.get("type"), str) and node["type"] in NODE_TYPES)
    ]

    bad_edges = []
    for edge in edges:
        reasons = []
        verb = edge.get("verb")
        if not (isinstance(verb, str) and verb.strip()):
            reasons.append("no verb")
        for end in ("from", "to"):
            value = edge.get(end)
            if not (isinstance(value, str) and value in ids):
                reasons.append(f"{end} is not a node id")
        if reasons:
            bad_edges.append(f"{_edge_name(edge)}: {', '.join(reasons)}")

    if views:
        too_big = [
            f"{view['id']}: {len(set(view['nodes']))} nodes"
            for view in views if len(set(view["nodes"])) > MAX_VIEW_NODES
        ]
        in_views = {node_id for view in views for node_id in view["nodes"]}
        orphans = [node["id"] for node in nodes if node["id"] not in in_views]
    else:
        too_big = [f"map: {len(nodes)} nodes and no views"] if len(nodes) > MAX_VIEW_NODES else []
        orphans = []

    return [
        _result("schema", []),
        _result("node_types", bad_types),
        _result("edges", bad_edges),
        _result("view_size", too_big),
        _result("orphans", orphans),
    ]


def _quote(text: str) -> str:
    return '"' + text.replace('"', "#quot;") + '"'


def to_mermaid(m, view_id: str | None = None) -> str:
    """A Mermaid flowchart of the map, or of one view. Expects ``schema``, ``node_types`` and ``edges`` to PASS."""
    nodes, edges = m["nodes"], m["edges"]
    if view_id is not None:
        view = next((v for v in m.get("views") or [] if v["id"] == view_id), None)
        if view is None:
            raise UnknownView(f"unknown view: {view_id}")
        keep = set(view["nodes"])
        nodes = [node for node in nodes if node["id"] in keep]
        edges = [edge for edge in edges if edge["from"] in keep and edge["to"] in keep]

    lines = ["flowchart TD"]
    for node in nodes:
        label = node["label"]
        if "order" in node:
            # "(1) " rather than "1. ": Mermaid 11 reads "1. " as a Markdown list.
            label = f"({node['order']}) {label}"
        opening, closing = _SHAPES[node["type"]]
        lines.append(f"    {node['id']}{opening}{_quote(label)}{closing}")
    for edge in edges:
        lines.append(f"    {edge['from']} -- {_quote(edge['verb'])} --> {edge['to']}")
    return "\n".join(lines) + "\n"


def format_results(results: list[CheckResult]) -> str:
    """``<status> <name>`` per result, each detail on its own line indented by two spaces."""
    lines = []
    for r in results:
        lines.append(f"{r.status} {r.name}")
        lines.extend(f"  {detail}" for detail in r.details)
    return "\n".join(lines)


def validate_unit(unit: Path) -> list[CheckResult]:
    """Validate the unit's map.json. Raises what ``load_map`` raises."""
    return validate_map(load_map(UnitPaths(unit).map))


def view_file(unit: Path, view_id: str) -> Path:
    """``overview-<view id>.mmd`` in the unit; ValueError when the id cannot be part of a file name."""
    try:
        safe_name(view_id, "view")
    except PlanError:
        raise ValueError(
            f"map.json: view {view_id!r} cannot name a file: "
            "avoid / \\ : * ? \" < > | and leading or trailing spaces or dots"
        ) from None
    return UnitPaths(unit).root / f"overview-{view_id}.mmd"


def export_mermaid(unit: Path, view_id: str | None = None) -> Path | list[Path]:
    """Write the map as Mermaid; writes nothing if the map fails.

    With ``view_id``, or for a map without views: overview.mmd (that view, or the whole
    map), and its path is returned. A map with views and no ``view_id``: one file per
    view, ``overview-<view id>.mmd``, in view order, and the list of their paths.
    """
    paths = UnitPaths(unit)
    m = load_map(paths.map)
    results = validate_map(m)
    if any(r.status == "FAIL" for r in results):
        raise MapInvalid(results)
    views = m.get("views") or []
    if view_id is not None or not views:
        text = to_mermaid(m, view_id)
        paths.mermaid.write_text(text, encoding="utf-8", newline="\n")
        return paths.mermaid
    # Every file name is checked before the first file is written.
    targets = [(view["id"], view_file(unit, view["id"])) for view in views]
    for vid, target in targets:
        target.write_text(to_mermaid(m, vid), encoding="utf-8", newline="\n")
    return [target for _, target in targets]
