#!/usr/bin/python3
"""Plan the first personal wallpaper TOML during staged app configuration setup."""

import os
from pathlib import Path
import sys


def plan(staging, destination):
    """Return a missing-file seed; existing personal contents are never parsed."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path(os.environ["HOME"]) / ".config")
    active = Path(os.environ.get("LUNA_WALLPAPER_CONFIG") or config_home / "luna/wallpaper.toml")
    if not active.is_absolute():
        raise ValueError("LUNA_WALLPAPER_CONFIG must be an absolute path")
    repo = Path(__file__).resolve().parents[2]
    installed = destination.resolve()

    # Follow personal links without replacing them. Check every hop because an
    # installed-file link may be replaced when the staged defaults are published.
    target = active.parent.resolve() / active.name
    seen = set()
    while True:
        if target.is_relative_to(repo) or target.is_relative_to(installed) or installed.is_relative_to(target):
            raise ValueError("Personal wallpaper config points into Luna's source or installed configs")
        if target in seen:
            raise ValueError("Personal wallpaper config contains a symlink loop")
        seen.add(target)
        if not target.is_symlink():
            break
        link = target.readlink()
        target = link if link.is_absolute() else target.parent / link
        target = target.parent.resolve() / target.name

    if target.exists():
        if not target.is_file():
            raise ValueError(f"Expected a personal wallpaper config file: {active}")
        return []

    content = (staging / "wallpaper.toml").read_bytes()

    # Keep a previous CLI selection when upgrading from the plain path file.
    # This is a one-time seed; leave that legacy file and all existing TOML alone.
    legacy = config_home / "luna/wallpaper"
    if legacy.is_file():
        try:
            source = legacy.read_text(encoding="utf-8").rstrip("\r\n")
        except (OSError, UnicodeError):
            print("Warning: Cannot read the previous wallpaper selection; using theme defaults.", file=sys.stderr)
        else:
            if source.startswith("/") and not any(ord(character) < 32 for character in source):
                import tomlkit

                document = tomlkit.parse(content.decode("utf-8"))
                document["wallpaper"]["source"] = source
                content = tomlkit.dumps(document).encode("utf-8")

    return [(target, content, 0o600)]
