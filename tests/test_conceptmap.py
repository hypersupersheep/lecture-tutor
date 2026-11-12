import json

import pytest

from conftest import status_of
from tutor_any_lecture.cli import main
from tutor_any_lecture.conceptmap import to_mermaid, validate_map


def map_with_view(nodes):
    ids = [f"n{i}" for i in range(1, nodes + 1)]
    return {
        "nodes": [{"id": i, "label": i.upper(), "type": "definition"} for i in ids],
        "edges": [],
        "views": [{"id": "v1", "nodes": ids}],
    }


def map_with_edge(verb):
    return {
        "nodes": [
            {"id": "a", "label": "A", "type": "definition"},
            {"id": "b", "label": "B", "type": "method"},
        ],
        "edges": [{"from": "a", "to": "b", "verb": verb}],
    }


def write_map(unit, m):
    unit.mkdir(parents=True, exist_ok=True)
    text = json.dumps(m, ensure_ascii=False, indent=2) + "\n"
    (unit / "map.json").write_text(text, encoding="utf-8", newline="\n")


AB_MERMAID = 'flowchart TD\n    a["A"]\n    b("B")\n    a -- "uses" --> b\n'


def test_view_cap():
    assert status_of(validate_map(map_with_view(nodes=13)), "view_size") == "FAIL"


def test_unlabelled_edge():
    assert status_of(validate_map(map_with_edge(verb="")), "edges") == "FAIL"


def test_mermaid_shapes():
    s = to_mermaid({"nodes": [{"id": "t", "label": "Itô", "type": "theorem", "order": 1}], "edges": []})
    assert 't[["(1) Itô"]]' in s


def test_unknown_node_type():
    m = map_with_edge(verb="uses")
    m["nodes"][0]["type"] = "lemma"
    assert status_of(validate_map(m), "node_types") == "FAIL"


def test_unknown_edge_endpoint():
    m = map_with_edge(verb="uses")
    m["edges"][0]["to"] = "missing"
    assert status_of(validate_map(m), "edges") == "FAIL"


def test_valid_map_passes():
    results = validate_map(map_with_view(nodes=12))
    assert [r.name for r in results] == ["schema", "node_types", "edges", "view_size", "orphans"]
    assert {r.status for r in results} == {"PASS"}


def test_orphan_and_total_cap():
    m = map_with_view(nodes=3)
    m["nodes"].append({"id": "x", "label": "X", "type": "example"})
    assert status_of(validate_map(m), "orphans") == "FAIL"
    m = map_with_view(nodes=13)
    del m["views"]
    results = validate_map(m)
    assert status_of(results, "view_size") == "FAIL"
    assert status_of(results, "orphans") == "PASS"


def test_schema_failure_returns_only_schema():
    m = map_with_edge(verb="uses")
    m["nodes"].append({"id": "a", "label": "Again", "type": "example"})
    assert [(r.name, r.status) for r in validate_map(m)] == [("schema", "FAIL")]
    assert [(r.name, r.status) for r in validate_map({"nodes": "x"})] == [("schema", "FAIL")]
    assert [(r.name, r.status) for r in validate_map([])] == [("schema", "FAIL")]


def test_validate_never_raises():
    m = {
        "nodes": [{"id": "a", "label": "A", "type": ["x"]}],
        "edges": [{"from": ["a"], "to": {"k": 1}, "verb": 3}],
    }
    results = validate_map(m)
    assert status_of(results, "schema") == "PASS"
    assert status_of(results, "node_types") == "FAIL"
    assert status_of(results, "edges") == "FAIL"


def test_mermaid_layout_and_escaping():
    assert to_mermaid(map_with_edge(verb="uses")) == AB_MERMAID
    m = {
        "nodes": [
            {"id": "e", "label": 'A "fair" bet', "type": "example"},
            {"id": "p", "label": "Mixing rates", "type": "pitfall", "order": 2},
        ],
        "edges": [{"from": "e", "to": "p", "verb": 'can "hide"'}],
    }
    s = to_mermaid(m)
    assert 'e>"A #quot;fair#quot; bet"]' in s
    assert 'p{{"(2) Mixing rates"}}' in s
    assert 'e -- "can #quot;hide#quot;" --> p' in s


def test_mermaid_view():
    m = map_with_edge(verb="uses")
    m["nodes"].append({"id": "c", "label": "C", "type": "example"})
    m["edges"].append({"from": "b", "to": "c", "verb": "shows"})
    m["views"] = [{"id": "v1", "nodes": ["a", "b"]}, {"id": "v2", "nodes": ["c"]}]
    assert to_mermaid(m, "v1") == AB_MERMAID
    assert 'b -- "shows" --> c' in to_mermaid(m)
    with pytest.raises(ValueError):
        to_mermaid(m, "nope")


def test_cli_map_validate_and_mermaid(tmp_path):
    unit = tmp_path / "课程 资料" / "第1周"
    write_map(unit, map_with_edge(verb="uses"))
    assert main(["map", "validate", "--unit", str(unit)]) == 0
    assert main(["map", "mermaid", "--unit", str(unit)]) == 0
    assert (unit / "overview.mmd").read_bytes() == AB_MERMAID.encode("utf-8")


def test_cli_map_failures(tmp_path):
    bad = tmp_path / "bad"
    write_map(bad, map_with_edge(verb=""))
    assert main(["map", "validate", "--unit", str(bad)]) == 1
    assert main(["map", "mermaid", "--unit", str(bad)]) == 1
    assert not (bad / "overview.mmd").exists()
    ok = tmp_path / "ok"
    write_map(ok, map_with_edge(verb="uses"))
    assert main(["map", "mermaid", "--unit", str(ok), "--view", "nope"]) == 2
    assert not (ok / "overview.mmd").exists()
    assert main(["map", "validate", "--unit", str(tmp_path / "missing")]) == 1


def test_cli_map_invalid_json(tmp_path, capsys):
    unit = tmp_path / "broken"
    unit.mkdir()
    (unit / "map.json").write_text("{", encoding="utf-8", newline="\n")
    assert main(["map", "validate", "--unit", str(unit)]) == 1
    assert main(["map", "mermaid", "--unit", str(unit)]) == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert not (unit / "overview.mmd").exists()
