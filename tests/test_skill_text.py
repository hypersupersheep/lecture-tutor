# tests/test_skill_text.py
import argparse
import re
from pathlib import Path

import pytest
import yaml

from tutor_any_lecture.cli import build_parser
from tutor_any_lecture.config import config_dir

SKILL = Path("skills/tutor-any-lecture/SKILL.md")
TEACHING = SKILL.parent / "references" / "teaching.md"
GUARDRAILS = [
    "Never type, store or ask for passwords.",
    "Never read browser cookies.",
    "Download media only when the profile allows it.",
    "Never capture streams of recordings whose downloads are disabled, and never circumvent DRM.",
    "Every claim you attribute to the lecturer carries a (slide N) or (mm:ss) citation.",
]
CARD_NOTICE = (
    "Card-writing rules adapted from anki-card-forge (https://github.com/FrostySL/anki-card-forge), "
    "MIT License, Copyright (c) 2026 Lukas Sinning."
)
# U+3000-30FF, U+3400-9FFF, U+AC00-D7AF, U+FF00-FFEF
CJK = re.compile("[　-ヿ㐀-鿿가-힯＀-￯]")
AGENT_SPECIFIC = ["javascript_tool", "Claude in Chrome", "mcp__"]


# ---- local helpers ----

def read(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter YAML, body); the body is everything after the closing --- line."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1:])


def frontmatter(path: Path) -> dict:
    return yaml.safe_load(split_frontmatter(read(path))[0]) or {}


def body(path: Path) -> str:
    return split_frontmatter(read(path))[1]


LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\s]+)\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def relative_links(path: Path) -> list[str]:
    """Targets of Markdown links [text](target) that are not URLs, anchors or absolute paths; #fragments dropped."""
    out = []
    for target in LINK.findall(read(path)):
        target = target.split("#", 1)[0]
        if not target or SCHEME.match(target) or target.startswith(("/", "\\", "~")):
            continue
        out.append(target)
    return out


CODE_SPAN = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"^\s*(`{3}|~{3})")  # a line opening or closing a fenced block
CMD = re.compile(r"(?:^|[\s(])tutor-any-lecture((?:[ \t]+[a-z][a-z-]*(?=\s|$)){1,2})")


def code_texts(text: str) -> list[str]:
    """Inline code spans outside fences, plus every line inside fenced blocks."""
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line)
        else:
            out.extend(CODE_SPAN.findall(line))
    return out


def subcommands_mentioned(path: Path) -> list[str]:
    """Space-joined subcommand paths ("doctor", "acquire route") from `tutor-any-lecture ...` in code."""
    paths = []
    for chunk in code_texts(read(path)):
        for m in CMD.finditer(chunk):
            paths.append(" ".join(m.group(1).split()))
    return paths


def cli_subcommands() -> list[str]:
    """Every subcommand path of build_parser(), at every depth ("acquire", "acquire route")."""
    paths = []

    def walk(parser: argparse.ArgumentParser, prefix: str) -> None:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    path = f"{prefix} {name}".strip()
                    paths.append(path)
                    walk(sub, path)

    walk(build_parser(), "")
    return paths


# ---- tests ----

def test_length():
    assert len(read(SKILL).splitlines()) <= 150


def test_description_triggers():
    desc = frontmatter(SKILL)["description"][:180].lower()
    assert all(w in desc for w in ["lecture", "notes", "quiz"])


def test_guardrails_present():
    t = read(SKILL)
    for s in GUARDRAILS:
        assert s in t


def test_referenced_files_exist():
    assert not [p for p in relative_links(SKILL) if not (SKILL.parent / p).exists()]


def test_subcommands_exist():
    assert set(subcommands_mentioned(SKILL)) <= set(cli_subcommands())


def test_no_private_terms():
    denylist = config_dir() / "denylist.txt"
    if not denylist.exists():
        pytest.skip(f"no denylist at {denylist}")
    terms = [s.strip() for s in read(denylist).splitlines()]
    terms = [t for t in terms if t and not t.startswith("#")]
    text = "\n".join(read(p) for p in sorted(SKILL.parent.rglob("*.md"))).lower()
    assert not [t for t in terms if t.lower() in text]


def test_body_agent_neutral():
    b = body(SKILL)
    assert not CJK.search(b)
    assert not [s for s in AGENT_SPECIFIC if s in b]


def test_helpers_not_vacuous():
    assert len(relative_links(SKILL)) >= 5 and len(set(subcommands_mentioned(SKILL))) >= 6


def test_step0_names_installers():
    t = read(SKILL)
    for name in ("scripts/install.sh", "scripts/install.ps1"):
        assert f"`{name}`" in t
        assert (SKILL.parent / name).exists()


def test_card_rules_notice():
    assert CARD_NOTICE in read(TEACHING)
