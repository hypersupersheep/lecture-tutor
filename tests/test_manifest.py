# tests/test_manifest.py
import json
from pathlib import Path


def test_plugin_and_marketplace_use_new_name():
    plugin = json.loads(Path(".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads(Path(".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "tutor-any-lecture"
    assert market["name"] == "tutor-any-lecture"
    assert market["plugins"][0]["name"] == "tutor-any-lecture"
    assert plugin["version"] == "2.0.0-dev"
    assert "panopto" not in plugin["description"].lower().split()[:3]


def test_skill_folder_renamed():
    assert Path("skills/tutor-any-lecture/SKILL.md").exists()
    assert not Path("skills/lecture-tutor").exists()


def test_readme_h1():
    for name in ("README.md", "README.zh-CN.md"):
        lines = Path(name).read_text(encoding="utf-8").splitlines()
        assert "# Tutor Any Lecture" in lines
