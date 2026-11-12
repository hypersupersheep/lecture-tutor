# tests/test_manifest.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_and_marketplace_use_new_name():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "tutor-any-lecture"
    assert market["name"] == "tutor-any-lecture"
    assert market["plugins"][0]["name"] == "tutor-any-lecture"
    assert plugin["version"] == "2.0.0-dev"
    assert market["plugins"][0]["version"] == plugin["version"]
    assert market["plugins"][0]["description"] == plugin["description"]


def test_skill_folder_renamed():
    assert (ROOT / "skills" / "tutor-any-lecture" / "SKILL.md").exists()
    assert not (ROOT / "skills" / "lecture-tutor").exists()


def test_readme_h1():
    for name in ("README.md", "README.zh-CN.md"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        assert "# Tutor Any Lecture" in lines
