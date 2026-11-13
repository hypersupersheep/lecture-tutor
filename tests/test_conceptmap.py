import json

import pytest

from conftest import status_of
from tutor_any_lecture.checks import CheckResult
from tutor_any_lecture.cli import main
from tutor_any_lecture.conceptmap import format_results, to_mermaid, validate_map


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


# ---- unreadable files and exit codes (Task 21) ------------------------------


def test_cli_map_not_utf8_is_one_line(tmp_path, capsys):
    unit = tmp_path / "课程 资料" / "第1周"
    unit.mkdir(parents=True)
    (unit / "map.json").write_bytes(b"\xff\xfe")
    for command in ("validate", "mermaid"):
        assert main(["map", command, "--unit", str(unit)]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.endswith("\n") and captured.err.count("\n") == 1
        assert captured.err.startswith("map.json")
    assert not (unit / "overview.mmd").exists()


def test_cli_map_mermaid_exit_codes(tmp_path):
    broken = tmp_path / "broken"
    write_map(broken, {"nodes": [{"id": "a", "label": "A", "type": "definition"}]})
    (broken / "map.json").write_text('{"nodes": [', encoding="utf-8", newline="\n")
    assert main(["map", "mermaid", "--unit", str(broken)]) == 1
    ok = tmp_path / "ok"
    write_map(ok, map_with_edge(verb="uses"))
    assert main(["map", "mermaid", "--unit", str(ok), "--view", "nope"]) == 2
    assert not (broken / "overview.mmd").exists() and not (ok / "overview.mmd").exists()


@pytest.mark.parametrize(
    "node_id, status",
    [("ito lemma", "FAIL"), ("a-b", "FAIL"), ("1x", "FAIL"), ("End", "FAIL"), ("ito_lemma", "PASS")],
)
def test_node_id_rule(node_id, status):
    m = {"nodes": [{"id": node_id, "label": "Itô's lemma", "type": "theorem"}], "edges": []}
    results = validate_map(m)
    assert status_of(results, "schema") == status
    if status == "FAIL":
        assert results[0].details == [
            f'node id {node_id!r}: use letters, digits and underscores, starting with a letter; "end" is reserved'
        ]



# ---- rules that had no test (Task 21) ---------------------------------------


@pytest.mark.parametrize("order, status", [(True, "FAIL"), (False, "FAIL"), (2, "PASS")])
def test_order_must_be_an_integer(order, status):
    m = map_with_edge(verb="uses")
    m["nodes"][0]["order"] = order
    assert status_of(validate_map(m), "schema") == status


def test_view_with_unknown_id_fails_schema():
    m = map_with_view(nodes=2)
    m["views"][0]["nodes"].append("zz")
    results = validate_map(m)
    assert [(r.name, r.status, r.details) for r in results] == [("schema", "FAIL", ["v1: unknown nodes zz"])]


def test_format_results_layout():
    results = [CheckResult("schema", "PASS", []), CheckResult("edges", "FAIL", ["a -> b: no verb", "c -> d: no verb"])]
    assert format_results(results) == "PASS schema\nFAIL edges\n  a -> b: no verb\n  c -> d: no verb"


def test_cli_map_mermaid_view(tmp_path):
    unit = tmp_path / "课程 资料" / "第1周"
    m = map_with_edge(verb="uses")
    m["nodes"].append({"id": "c", "label": "C", "type": "example"})
    m["views"] = [{"id": "v1", "nodes": ["a", "b"]}, {"id": "v2", "nodes": ["c"]}]
    write_map(unit, m)
    assert main(["map", "mermaid", "--unit", str(unit), "--view", "v1"]) == 0
    assert (unit / "overview.mmd").read_bytes() == AB_MERMAID.encode("utf-8")


def test_cli_unknown_view_is_one_line(tmp_path, capsys):
    ok = tmp_path / "ok"
    write_map(ok, map_with_edge(verb="uses"))
    assert main(["map", "mermaid", "--unit", str(ok), "--view", "two\nlines"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "unknown view: two lines\n"


# ---- a map with views is exported by view (Task 29, L11) ----------------------


def test_mermaid_writes_one_file_per_view(tmp_path, capsys):
    unit = tmp_path / "课程 资料" / "第1周"
    m = map_with_edge(verb="uses")
    m["nodes"].append({"id": "c", "label": "C", "type": "example"})
    m["edges"].append({"from": "b", "to": "c", "verb": "shows"})
    m["views"] = [{"id": "v1", "nodes": ["a", "b"]}, {"id": "later part", "nodes": ["b", "c"]}]
    write_map(unit, m)
    assert main(["map", "mermaid", "--unit", str(unit)]) == 0
    out = json.loads(capsys.readouterr().out)
    expected = [unit / "overview-v1.mmd", unit / "overview-later part.mmd"]
    assert out == {"paths": [str(p) for p in expected]}
    assert expected[0].read_bytes() == AB_MERMAID.encode("utf-8")
    assert expected[1].read_text(encoding="utf-8") == to_mermaid(m, "later part")
    assert not (unit / "overview.mmd").exists()
    # one view on request still writes overview.mmd; a map without views is one file
    assert main(["map", "mermaid", "--unit", str(unit), "--view", "v1"]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(unit / "overview.mmd")}
    plain = tmp_path / "plain"
    write_map(plain, map_with_edge(verb="uses"))
    assert main(["map", "mermaid", "--unit", str(plain)]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(plain / "overview.mmd")}
    assert sorted(p.name for p in plain.glob("*.mmd")) == ["overview.mmd"]


def test_mermaid_view_id_must_be_a_file_name(tmp_path, capsys):
    unit = tmp_path / "unit"
    m = map_with_edge(verb="uses")
    m["views"] = [{"id": "a/b", "nodes": ["a", "b"]}]
    write_map(unit, m)
    assert main(["map", "mermaid", "--unit", str(unit)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "a/b" in captured.err and captured.err.count("\n") == 1
    assert list(unit.glob("*.mmd")) == []
