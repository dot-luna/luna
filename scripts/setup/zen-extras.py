#!/usr/bin/python3
"""Install the optional Better Find Bar Mod after app configurations are connected."""

import importlib.util
import os
from pathlib import Path
import sys

# Loading helpers must not leave cache files in the checkout.
sys.dont_write_bytecode = True

import zen_mods


spec = importlib.util.spec_from_file_location("zen_profile", Path(__file__).with_name("zen-profile.py"))
profile_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile_config)


def install(destination, available):
    if not available and not os.environ.get("ZEN_PROFILE_DIR"):
        return
    profile = profile_config.choose_profile()
    if profile is None:
        return

    repo = Path(__file__).resolve().parents[2]
    output = profile_config.absolute_path(destination, "Zen configuration destination").resolve()
    profile = profile.resolve()
    if profile_config.overlaps(profile, repo) or profile_config.overlaps(profile, output):
        raise ValueError("The Zen profile must be separate from Luna's source and generated configs")

    # Mod paths may be symlinks, but must never alias Luna's personal CSS/user.js
    # connections or browser locks. Check every write before publishing any.
    protected = {
        (profile / relative).resolve() for relative in
        ("chrome/userChrome.css", "chrome/userContent.css", "user.js", ".parentlock", "lock")
    }
    try:
        writes = zen_mods.prepare_mod(
            profile, lambda path: profile_config.read_personal(path, repo, output)
        )
        if any(path in protected for path, _, _ in writes):
            raise ValueError("Zen mod files, profile styles, user.js and locks must be separate files")
        for path, content, mode in writes:
            profile_config.write_file(path, content, mode)
    finally:
        zen_mods.release_lock()


if __name__ == "__main__":
    try:
        install(sys.argv[1], sys.argv[2] == "1")
    except (OSError, ValueError, RuntimeError, KeyError, IndexError) as error:
        print(f"Zen: Better Find Bar skipped: {error}", file=sys.stderr)
        sys.exit(1)
