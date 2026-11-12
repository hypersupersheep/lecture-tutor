import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import fx, names_by_status, status_of

from tutor_any_lecture.config import config_dir, workspace
from tutor_any_lecture.profile import ConsentRequired, Profile, ProfileError, load_profile, set_value
from tutor_any_lecture.unit import UnitPaths

CONTRACT = {
    "transcript": "sources/transcript.json",
    "source": "sources/source.json",
    "chapters": "sources/chapters.json",
    "suspects": "sources/suspects.json",
    "pages": "sources/slides/pages.json",
    "plan": "plan.json",
    "explanation": "explanation.md",
    "items": "items.json",
    "assignment": "assignment.json",
    "cards_json": "cards.json",
    "cards_tsv": "cards.tsv",
    "map": "map.json",
    "mermaid": "overview.mmd",
    "verify": "verify.json",
}


def test_defaults_when_missing(tmp_path):
    p = load_profile(tmp_path / "none.yaml")
    assert p.goal == "deep" and p.public_video_audio == "off" and p.lecture_language == "auto" and p.note_language == "auto"


def test_unknown_key_rejected(tmp_path):
    (tmp_path / "p.yaml").write_text("colour: red\n", encoding="utf-8", newline="\n")
    with pytest.raises(ProfileError):
        load_profile(tmp_path / "p.yaml")


def test_public_video_audio_needs_consent(tmp_cfg):
    with pytest.raises(ConsentRequired) as e:
        set_value("public_video_audio", "on")
    assert "personal study only" in e.value.notice


def test_public_video_audio_with_consent(tmp_cfg):
    assert set_value("public_video_audio", "on", i_understand=True).public_video_audio == "on"


def test_config_dir_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\a\AppData\Roaming")
    assert config_dir() == Path(r"C:\Users\a\AppData\Roaming") / "tutor-any-lecture"


def test_config_dir_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    assert config_dir() == tmp_path / "xdg" / "tutor-any-lecture"


def test_config_dir_empty_xdg_is_unset(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    assert config_dir() == Path.home() / ".config" / "tutor-any-lecture"


def test_set_value_saves_to_profile_yaml(tmp_cfg):
    set_value("goal", "exam")
    set_value("public_video_audio", "on", i_understand=True)
    assert (config_dir() / "profile.yaml").exists()
    p = load_profile()
    assert p.goal == "exam" and p.public_video_audio == "on"


def test_set_value_rejects_bad_key_and_value(tmp_cfg):
    with pytest.raises(ProfileError):
        set_value("colour", "red")
    with pytest.raises(ProfileError):
        set_value("goal", "fast")
    with pytest.raises(ProfileError):
        set_value("outputs", "explanation")
    with pytest.raises(ConsentRequired):
        set_value("public_video_audio", "on")
    assert not (config_dir() / "profile.yaml").exists()


def test_set_value_parses_outputs_and_platforms(tmp_cfg):
    assert set_value("outputs", "[explanation, quiz]").outputs == ["explanation", "quiz"]
    assert set_value("platforms", "{video: https://example.org}").platforms == {"video": "https://example.org"}
    assert load_profile().outputs == ["explanation", "quiz"]


def test_load_maps_yaml_bool_to_on_off(tmp_path):
    (tmp_path / "p.yaml").write_text("public_video_audio: on\n", encoding="utf-8", newline="\n")
    assert load_profile(tmp_path / "p.yaml").public_video_audio == "on"


def test_load_rejects_non_string_in_string_field(tmp_path):
    for text, key in [("workspace:\n", "workspace"), ("lecture_language: no\n", "lecture_language")]:
        (tmp_path / "p.yaml").write_text(text, encoding="utf-8", newline="\n")
        with pytest.raises(ProfileError) as e:
            load_profile(tmp_path / "p.yaml")
        assert key in str(e.value)


def test_workspace_resolves_through_profile(tmp_cfg):
    assert workspace(Profile(workspace="~/X")) == Path.home() / "X"
    set_value("workspace", str(tmp_cfg / "ws"))
    assert workspace() == tmp_cfg / "ws"


def test_unit_paths_contract(tmp_path):
    u = UnitPaths(tmp_path)
    for name, rel in CONTRACT.items():
        assert getattr(u, name) == tmp_path / rel
    assert not (tmp_path / "sources").exists()
    u.ensure()
    assert (tmp_path / "sources" / "slides").is_dir()


def test_conftest_helpers():
    results = [
        SimpleNamespace(name="a", status="PASS", details=""),
        SimpleNamespace(name="b", status="FAIL", details="x"),
        SimpleNamespace(name="c", status="PASS", details=""),
    ]
    assert status_of(results, "b") == "FAIL"
    with pytest.raises(KeyError):
        status_of(results, "missing")
    by_status = names_by_status(results)
    assert type(by_status) is dict and by_status == {"PASS": {"a", "c"}, "FAIL": {"b"}}
    assert fx("transcripts", "cues.vtt") == Path(__file__).parent / "fixtures" / "transcripts" / "cues.vtt"
