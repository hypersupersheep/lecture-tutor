"""The user profile: load, save and change it, with the public_video_audio consent gate."""

from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import config_dir
from .plan import DEFAULT_QUOTE_DENSITY, QUOTE_DENSITIES

PUBLIC_VIDEO_AUDIO_NOTICE = "Turning this on lets tutor-any-lecture download the audio track of a video (YouTube, Bilibili and other sites yt-dlp supports) when no usable captions exist, transcribe it locally, then delete it. The choice and the responsibility are yours for every address you give, a school's or a meeting platform's recordings included: check that you are allowed to download it, and follow its site's terms and copyright; use it for personal study only. The tool uses no cookies and no login, so a recording behind a sign-in is out of reach, and DRM is never circumvented."

PROFILE_FILE_NAME = "profile.yaml"

# Fields whose value must come from a fixed set. Every other string field is free text.
ALLOWED_VALUES: dict[str, tuple[str, ...]] = {
    "goal": ("deep", "exam", "quick"),
    "terms": ("bilingual", "note", "original"),
    "level": ("auto", "beginner", "intermediate", "advanced"),
    "output_target": ("markdown", "obsidian", "notion"),
    "downloads": ("ask", "allow"),
    "public_video_audio": ("on", "off"),
    "naming": ("default",),
    "quote_density": QUOTE_DENSITIES,
}
# The members outputs may list, and the keys platforms may hold (each value a base URL).
OUTPUT_MEMBERS = ("explanation", "pretest", "quiz", "cards", "map")
PLATFORM_KEYS = ("moodle", "panopto")


class ProfileError(Exception):
    """A profile file or a requested change is invalid. The message names the key."""


class ConsentRequired(Exception):
    """Turning public_video_audio on needs explicit consent. ``str(e)`` is the notice."""

    def __init__(self, notice: str) -> None:
        super().__init__(notice)
        self.notice = notice


@dataclass
class Profile:
    note_language: str = "auto"
    lecture_language: str = "auto"
    terms: str = "bilingual"
    level: str = "auto"
    goal: str = "deep"
    # How densely a note in another language than the lecture quotes it; written into plan.json.
    quote_density: str = DEFAULT_QUOTE_DENSITY
    outputs: list[str] = field(default_factory=lambda: ["explanation", "pretest", "quiz", "cards", "map"])
    output_target: str = "markdown"
    workspace: str = "~/TutorAnyLecture"
    obsidian_vault: str = ""
    naming: str = "default"
    downloads: str = "ask"
    public_video_audio: str = "off"
    # The day the notice was accepted (YYYY-MM-DD); written by "profile set public_video_audio
    # on --i-understand", removed by "off". Audio is downloaded only while it holds a date.
    public_video_audio_consent: str | None = None
    platforms: dict[str, str] = field(default_factory=dict)


FIELD_NAMES = tuple(f.name for f in dataclasses.fields(Profile))
CONSENT_KEY = "public_video_audio_consent"
# outputs and platforms are structured, the consent key is an optional date; the other
# twelve fields hold strings.
STRING_FIELDS = tuple(name for name in FIELD_NAMES if name not in ("outputs", "platforms", CONSENT_KEY))


def _profile_file() -> Path:
    return config_dir() / PROFILE_FILE_NAME


def _check_key(key: Any) -> None:
    if key not in FIELD_NAMES:
        raise ProfileError(f"unknown profile key {key!r}; known keys: {', '.join(FIELD_NAMES)}")


def _check_allowed(key: str, value: Any) -> None:
    allowed = ALLOWED_VALUES.get(key)
    if allowed is not None and value not in allowed:
        raise ProfileError(f"{key}: {value!r} is not allowed; allowed values: {', '.join(allowed)}")


def _check_structured(key: str, value: Any) -> None:
    if key == "outputs":
        if not isinstance(value, list):
            raise ProfileError(f"outputs must be a list, for example [explanation, quiz]; got {value!r}")
        bad = [x for x in value if x not in OUTPUT_MEMBERS]
        if bad:
            raise ProfileError(f"outputs: {bad[0]!r} is not allowed; allowed members: {', '.join(OUTPUT_MEMBERS)}")
        if "explanation" not in value:
            raise ProfileError(
                f"outputs must include explanation (the gate always reads explanation.md); got {value!r}"
            )
    if key == "platforms":
        if not isinstance(value, dict):
            raise ProfileError(
                f"platforms must be a mapping, for example {{moodle: https://moodle.example.edu}}; got {value!r}"
            )
        for name, url in value.items():
            if name not in PLATFORM_KEYS:
                raise ProfileError(f"platforms: {name!r} is not allowed; allowed keys: {', '.join(PLATFORM_KEYS)}")
            if not isinstance(url, str):
                raise ProfileError(f"platforms: {name} must be a base URL as text; got {url!r}")


def _is_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def has_audio_consent(profile: Profile) -> bool:
    """The switch is on and the consent key holds a date: audio may be downloaded."""
    return profile.public_video_audio == "on" and _is_date(profile.public_video_audio_consent)


def load_profile(path: Path | None = None) -> Profile:
    """Read the profile file. A missing or empty file gives the defaults. Never writes."""
    path = _profile_file() if path is None else Path(path)
    if not path.exists():
        return Profile()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ProfileError(f"{path}: not valid YAML: {e}") from e
    if data is None:
        return Profile()
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: the top level must be a mapping of key: value lines")

    for key in data:
        _check_key(key)

    # PyYAML (YAML 1.1) reads a bare on/off as a boolean; map it back.
    if isinstance(data.get("public_video_audio"), bool):
        data["public_video_audio"] = "on" if data["public_video_audio"] else "off"
    # An unquoted 2026-11-13 is read as a date; keep it as text.
    consent = data.get(CONSENT_KEY)
    if isinstance(consent, datetime.date) and not isinstance(consent, datetime.datetime):
        data[CONSENT_KEY] = consent = consent.isoformat()
    if consent is not None and not _is_date(consent):
        raise ProfileError(f"{CONSENT_KEY}: expected a date such as 2026-11-13; got {consent!r}")

    for key in STRING_FIELDS:
        if key in data and not isinstance(data[key], str):
            raise ProfileError(_not_a_string(key, data[key]))

    for key, value in data.items():
        _check_structured(key, value)
        _check_allowed(key, value)

    return Profile(**data)


def _not_a_string(key: str, value: Any) -> str:
    if value is None:
        return f'{key}: the value is empty; write a value, quoted if needed (for example {key}: "value"), or delete the line'
    if isinstance(value, bool):
        # YAML 1.1 turns yes/no/on/off/true/false into booleans; which word was written is lost.
        return f"{key}: put the value in quotes; YAML reads yes, no, on, off, true and false as booleans"
    return f'{key}: expected text but got {value!r}; quote the value, for example {key}: "{value}"'


def save_profile(profile: Profile, path: Path | None = None) -> Path:
    """Write all fields as YAML, creating the parent folder when needed."""
    path = _profile_file() if path is None else Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dataclasses.asdict(profile)
    if data[CONSENT_KEY] is None:
        del data[CONSENT_KEY]  # no consent: the key is absent from the file
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def set_value(key: str, value: str, i_understand: bool = False) -> Profile:
    """Change one key in the profile file. Every check runs before anything is written.

    ``public_video_audio on`` (with ``i_understand``) also records today's date under
    ``public_video_audio_consent``; ``off`` removes it.
    """
    _check_key(key)
    if key == CONSENT_KEY:
        raise ProfileError(
            f"{CONSENT_KEY} is recorded when you accept the notice: "
            "tutor-any-lecture profile set public_video_audio on --i-understand"
        )

    parsed: Any = value
    if key in ("outputs", "platforms"):
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError as e:
            raise ProfileError(f"{key}: not valid YAML: {e}") from e
        _check_structured(key, parsed)
    # String fields keep the raw string: through YAML, "on" would become True.

    _check_allowed(key, parsed)

    if key == "public_video_audio" and parsed == "on" and not i_understand:
        raise ConsentRequired(PUBLIC_VIDEO_AUDIO_NOTICE)

    changes: dict[str, Any] = {key: parsed}
    if key == "public_video_audio":
        changes[CONSENT_KEY] = datetime.date.today().isoformat() if parsed == "on" else None
    profile = dataclasses.replace(load_profile(), **changes)
    save_profile(profile)
    return profile
