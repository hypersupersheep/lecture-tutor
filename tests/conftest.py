from pathlib import Path

import pytest


def fx(*parts) -> Path:
    return Path(__file__).parent / "fixtures" / Path(*parts)


@pytest.fixture
def tmp_cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


def status_of(results, name) -> str:
    for r in results:
        if r.name == name:
            return r.status
    raise KeyError(name)


def names_by_status(results) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in results:
        out.setdefault(r.status, set()).add(r.name)
    return out
