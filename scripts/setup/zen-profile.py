#!/usr/bin/python3
"""Plan stylesheet imports and font defaults in an existing Zen profile."""

import configparser
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


BOM = b"\xef\xbb\xbf"
CSS_START = b"/* >>> Luna theme >>> */"
CSS_END = b"/* <<< Luna theme <<< */"
JS_START = b"// >>> Luna stylesheets >>>"
JS_END = b"// <<< Luna stylesheets <<<"
FONT_START = b"// >>> Luna fonts >>>"
FONT_END = b"// <<< Luna fonts <<<"

# Gecko's language groups from modules/libpref/init/all.js. Keep its dedicated
# math fonts and fallback lists: UI fonts may not contain every script's glyphs.
FONT_GROUPS = (
    "ar", "el", "he", "ja", "ko", "th", "x-armn", "x-beng", "x-cans",
    "x-cyrillic", "x-devanagari", "x-ethi", "x-geor", "x-gujr", "x-guru",
    "x-khmr", "x-knda", "x-mlym", "x-orya", "x-sinh", "x-tamil", "x-telu",
    "x-tibt", "x-unicode", "x-western", "zh-CN", "zh-HK", "zh-TW",
)


def warn(message):
    print(f"Zen: {message}", file=sys.stderr)


def overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path


def choose_profile():
    override = os.environ.get("ZEN_PROFILE_DIR")
    if override:
        return absolute_path(override, "ZEN_PROFILE_DIR")

    # Native Zen retains an existing legacy root, even without profiles.ini.
    # Mozilla's app-data/legacy environment overrides take precedence over XDG.
    home = absolute_path(os.environ["HOME"], "HOME")
    legacy = home / ".zen"
    if os.environ.get("MOZ_APP_DATA"):
        root = absolute_path(os.environ["MOZ_APP_DATA"], "MOZ_APP_DATA")
    elif os.environ.get("MOZ_LEGACY_HOME", "").startswith("1") or legacy.exists():
        root = legacy
    else:
        config = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
        root = absolute_path(config, "XDG_CONFIG_HOME") / "zen"

    registry = root / "profiles.ini"
    try:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(registry.read_text(encoding="utf-8-sig"))
        profiles = []
        defaults = []
        installs = []
        for section in parser.sections():
            if section.startswith("Install") and parser.has_option(section, "Default"):
                if not parser[section]["Default"]:
                    raise ValueError("An install default profile path is empty")
                path = Path(parser[section]["Default"])
                installs.append(path if path.is_absolute() else root / path)
            elif re.fullmatch(r"Profile\d+", section):
                if not parser[section]["Path"]:
                    raise ValueError("A profile path is empty")
                path = Path(parser[section]["Path"])
                relative = parser.get(section, "IsRelative", fallback="1")
                if relative not in ("0", "1") or (relative == "1" and path.is_absolute()):
                    raise ValueError("Invalid IsRelative or relative profile path")
                if relative == "1":
                    path = root / path
                elif not path.is_absolute():
                    raise ValueError("A nonrelative profile path must be absolute")
                profiles.append(path)
                if parser.get(section, "Default", fallback="0") == "1":
                    defaults.append(path)
        choices = {path.resolve() for path in (installs or defaults or profiles)}
        if len(choices) == 1:
            return choices.pop()
        if choices:
            warn("Multiple profiles are available; set ZEN_PROFILE_DIR to the intended profile and rerun setup.")
            return None
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError, configparser.Error, KeyError, ValueError) as error:
        warn(f"Cannot read profiles.ini: {error}. Set ZEN_PROFILE_DIR and rerun setup.")
        return None

    warn("No existing profile found. Open Zen once, then rerun setup.")
    return None


def remove_managed(content, start, end):
    # Only Luna's reserved full-line markers are managed; all other bytes stay.
    output = []
    inside = False
    for line in content.splitlines(keepends=True):
        marker = line.rstrip(b"\r\n")
        if marker == start:
            if inside:
                raise ValueError("Nested Luna markers; repair the managed block before rerunning setup")
            inside = True
        elif marker == end:
            if not inside:
                raise ValueError("Unmatched Luna marker; repair the managed block before rerunning setup")
            inside = False
        elif not inside:
            output.append(line)
    if inside:
        raise ValueError("Unclosed Luna marker; repair the managed block before rerunning setup")
    return b"".join(output)


def managed_content(content, installed=None):
    if content.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
        raise ValueError("Convert UTF-16/UTF-32 profile styles or user.js to UTF-8 before rerunning setup")
    bom = BOM if content.startswith(BOM) else b""
    body = content[len(bom):]
    newline = b"\r\n" if b"\r\n" in body else b"\n"
    start, end = (CSS_START, CSS_END) if installed else (JS_START, JS_END)
    body = remove_managed(body, start, end)
    if installed:
        # CSS imports must precede namespaces/rules, but follow an encoding
        # declaration. URI escaping keeps arbitrary filesystem names literal.
        rule = ('@import url("' + installed.as_uri() + '");').encode("ascii")
        charset = re.match(br'\A@charset "[^"\r\n]+";(?:(?:\r\n|\n))?', body)
        offset = charset.end() if charset else 0
        prefix, suffix = body[:offset], body[offset:]
        if prefix and not prefix.endswith(b"\n"):
            prefix += newline
        return bom + prefix + newline.join((start, rule, end, b"")) + suffix

    # user.js is read in order; the managed preference must remain last even
    # when personal preferences were appended after a previous setup run.
    if body and not body.endswith(b"\n"):
        body += newline
    preference = b'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
    return bom + body + newline.join((start, preference, end, b""))


def font_preferences(fonts):
    if not isinstance(fonts, dict) or any(
        not isinstance(fonts.get(role), str) or not fonts[role].strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in fonts[role])
        for role in ("ui", "mono")
    ):
        raise ValueError("The Zen builder must provide valid UI and monospace fonts")

    # Match the Fonts settings dialog: these are defaults for generic families,
    # while the site's own font declarations and downloadable fonts still win.
    preferences = {"browser.display.use_document_fonts": 1}
    for group in FONT_GROUPS:
        preferences[f"font.default.{group}"] = "sans-serif"
        for family, role in (("serif", "ui"), ("sans-serif", "ui"), ("monospace", "mono")):
            preferences[f"font.name.{family}.{group}"] = fonts[role]
    return preferences


def managed_preferences(content, preferences, start, end):
    bom = BOM if content.startswith(BOM) else b""
    content = content[len(bom):]
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    body = remove_managed(content, start, end)
    if body and not body.endswith(b"\n"):
        body += newline
    lines = [start]
    for name, value in preferences.items():
        lines.append(f"user_pref({json.dumps(name)}, {json.dumps(value)});".encode("ascii"))
    return bom + body + newline.join((*lines, end, b""))


def read_personal(path, repo, output, forbidden=()):
    # Check every symlink hop, including parent directories: publication replaces
    # owned links, so their current external targets are not safe personal paths.
    pending = list(path.parts)
    target = Path(pending.pop(0))
    links = 0
    while pending:
        part = pending.pop(0)
        target = target.parent if part == ".." else target / part
        if target.is_relative_to(repo) or target.is_relative_to(output):
            raise ValueError(f"Profile file points into Luna's source or generated configs: {path}")
        if target in forbidden:
            raise ValueError("Zen profile styles and user.js must not point to browser lock files")
        if target.is_symlink():
            links += 1
            if links > 40:
                raise ValueError(f"Profile file contains a symlink loop or too many links: {path}")
            link = target.readlink()
            pending = list(link.parts) + pending
            target = Path(pending.pop(0)) if link.is_absolute() else target.parent

    try:
        content = target.read_bytes()
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        content, mode = b"", 0o600
    return target, content, mode


def write_file(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".luna-zen-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def plan(destination, available, styles):
    """Validate every personal file before the shared installer publishes anything."""
    if not isinstance(styles, dict) or any(
        not isinstance(styles.get(key), str) or not styles[key] for key in ("chrome", "content")
    ):
        raise ValueError("The Zen builder must provide nonempty chrome and content styles")
    preferences = font_preferences(styles.get("fonts"))
    output = absolute_path(destination, "Zen configuration destination")
    generated = output / "generated"
    repo = Path(__file__).resolve().parents[2]
    for directory in (output, generated):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(f"Zen configuration destination must be a directory, not a symlink: {directory}")
    output = output.resolve()
    if overlaps(output, repo):
        raise ValueError("Zen source and installed configuration must be separate paths")

    writes = []

    # An explicit profile also supports alternate installs, including Flatpak,
    # whose executable may not be on PATH. No browser command is ever launched.
    explicit = bool(os.environ.get("ZEN_PROFILE_DIR"))
    profile = choose_profile() if available or explicit else None
    if not available and not explicit:
        warn("Zen command is unavailable; skipping automatic profile integration.")
    elif profile is not None:
        profile = profile.resolve()
        if overlaps(profile, repo) or overlaps(profile, output):
            raise ValueError("The Zen profile must be separate from Luna's source and generated configs")
        if not profile.is_dir():
            warn("Selected Zen profile does not exist. Open Zen once or set ZEN_PROFILE_DIR, then rerun setup.")
            profile = None

    if profile is not None:
        targets = set()
        for relative, installed in (
            ("chrome/userChrome.css", output / "userChrome.css"),
            ("chrome/userContent.css", output / "userContent.css"),
            ("user.js", None),
        ):
            target, content, mode = read_personal(
                profile / relative, repo, output, (profile / ".parentlock", profile / "lock")
            )
            if target in targets:
                raise ValueError("Zen profile styles and user.js must be separate files")
            targets.add(target)
            updated = managed_content(content, installed)
            if installed is None:
                updated = managed_preferences(updated, preferences, FONT_START, FONT_END)
            if updated != content:
                writes.append((target, updated, mode))

    return writes


def configure(destination, available, styles):
    for path, content, mode in plan(destination, available, styles):
        write_file(path, content, mode)


if __name__ == "__main__":
    try:
        configure(sys.argv[1], sys.argv[2] == "1", json.load(sys.stdin))
    except (OSError, ValueError, RuntimeError, KeyError, IndexError) as error:
        print(f"Cannot configure Zen: {error}", file=sys.stderr)
        sys.exit(1)
