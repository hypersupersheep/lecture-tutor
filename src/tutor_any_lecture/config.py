"""Where the user's configuration and workspace live."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .profile import Profile

APP_NAME = "tutor-any-lecture"


def config_dir() -> Path:
    """The per-user config folder. Computed on every call; never created here."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def workspace(profile: Profile | None = None) -> Path:
    """The profile's workspace folder with ``~`` expanded."""
    if profile is None:
        # Imported here: profile.py imports config_dir from this module.
        from .profile import load_profile

        profile = load_profile()
    return Path(profile.workspace).expanduser()
