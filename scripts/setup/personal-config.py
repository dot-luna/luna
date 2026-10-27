#!/usr/bin/python3
"""Seed personal Luna TOML files without replacing existing user settings."""

import os
from pathlib import Path


def plan(staging, destination, app):
    """Return a missing-file seed; existing personal contents are never parsed."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path(os.environ["HOME"]) / ".config")
    override = "LUNA_" + app.upper() + "_CONFIG"
    filename = app + ".toml"
    active = Path(os.environ.get(override) or config_home / "luna" / filename)
    if not active.is_absolute():
        raise ValueError(f"{override} must be an absolute path")
    repo = Path(__file__).resolve().parents[2]
    installed = destination.resolve()

    # Follow personal links without replacing them. Check every hop because an
    # installed-file link may be replaced when the staged defaults are published.
    target = active.parent.resolve() / active.name
    seen = set()
    while True:
        if target.is_relative_to(repo) or target.is_relative_to(installed) or installed.is_relative_to(target):
            raise ValueError(f"Personal {app} config points into Luna's source or installed configs")
        if target in seen:
            raise ValueError(f"Personal {app} config contains a symlink loop")
        seen.add(target)
        if not target.is_symlink():
            break
        link = target.readlink()
        target = link if link.is_absolute() else target.parent / link
        target = target.parent.resolve() / target.name

    if target.exists():
        if not target.is_file():
            raise ValueError(f"Expected a personal {app} config file: {active}")
        return []

    content = (staging / filename).read_bytes()

    return [(target, content, 0o600)]
