"""Prepare Better Find Bar's native Zen files without changing other installed Mods."""

import ast
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.request


MOD_ID = "a6335949-4465-4b71-926c-4a52d34bc9c0"
MANIFEST_URL = f"https://zen-browser.github.io/theme-store/themes/{MOD_ID}/theme.json"
ASSET_ROOT = f"https://raw.githubusercontent.com/zen-browser/theme-store/main/themes/{MOD_ID}/"
MAX_DOWNLOAD = 1024 * 1024
_locks = {}

# Tokenize preference files without evaluating JavaScript. Strings stay whole,
# so commented-out calls and examples inside preference values cannot match.
JS_TOKEN = re.compile(
    r'''(?P<comment>//[^\r\n]*|/\*.*?\*/)|(?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
    r'''|(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<other>\S)''', re.DOTALL,
)


def warn(message):
    print(f"Zen: Better Find Bar skipped: {message}", file=sys.stderr)


def release_lock():
    """Release profile locks after the caller has published all planned writes."""
    for descriptor in _locks.values():
        os.close(descriptor)
    _locks.clear()


def lock_profile(profile, read_personal):
    # Firefox uses a whole-file POSIX fcntl lock, not flock. Keep its inode in
    # place and retain the descriptor through publication to prevent startup races.
    # https://github.com/mozilla-firefox/firefox/blob/main/toolkit/profile/nsProfileLock.cpp
    if profile in _locks:
        return
    lock_path = profile / ".parentlock"
    target, _, _ = read_personal(lock_path)
    if target != lock_path or lock_path.is_symlink():
        raise ValueError("profile lock must be a regular file; close Zen and repair its lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("profile lock is not a regular file")
        try:
            fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EACCES):
                raise ValueError("close Zen and rerun setup") from None
            raise

        # A '+' lock is obsolete once the fcntl lock is ours. Older/remote locks
        # cannot be safely diagnosed here; preserve them and skip this step.
        legacy = profile / "lock"
        if legacy.is_symlink():
            if not re.fullmatch(r"[^:]+:\+\d+", os.readlink(legacy)):
                raise ValueError("profile has a legacy lock; close Zen and rerun setup")
        elif legacy.exists():
            raise ValueError("profile has an unrecognized lock; close Zen and rerun setup")
    except Exception:
        os.close(descriptor)
        raise
    _locks[profile] = descriptor


def download(url):
    allowed = {MANIFEST_URL, *(ASSET_ROOT + name for name in ("chrome.css", "preferences.json", "readme.md"))}
    if url not in allowed:
        raise ValueError("the Mod metadata contains an unexpected download URL")
    with urllib.request.urlopen(url, timeout=10) as response:
        if response.geturl() not in allowed:
            raise ValueError("the Mod download redirected outside the official store")
        content = response.read(MAX_DOWNLOAD + 1)
    if not content or len(content) > MAX_DOWNLOAD:
        raise ValueError("the Mod download is empty or exceeds 1 MiB")
    content.decode("utf-8")
    return content


def read_json(content):
    def unique_pairs(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate JSON fields in Mod data")
            result[name] = value
        return result
    def reject_constant(value):
        raise ValueError(f"invalid JSON number: {value}")
    return json.loads(content.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def preference_names(content):
    tokens = [match for match in JS_TOKEN.finditer(content.decode("utf-8-sig"))
              if match.lastgroup != "comment"]
    names = set()
    for index, token in enumerate(tokens[:-3]):
        if token.lastgroup != "word" or token[0] not in ("user_pref", "pref", "sticky_pref"):
            continue
        opening, name, comma = tokens[index + 1:index + 4]
        if opening[0] == "(" and name.lastgroup == "string" and comma[0] == ",":
            names.add(ast.literal_eval(name[0]))
    return names


def preference_defaults(preferences):
    if not isinstance(preferences, list):
        raise ValueError("the Mod preferences must be a JSON list")
    defaults = {}
    for preference in preferences:
        if not isinstance(preference, dict):
            raise ValueError("invalid Mod preference")
        name = preference.get("property")
        kind = preference.get("type")
        if not isinstance(name, str) or not re.fullmatch(
            r"(?:theme\.better_find_bar\.|theme-better_find_bar-)[A-Za-z0-9_.-]+", name
        ) or name in defaults:
            raise ValueError("invalid or duplicate Better Find Bar preference name")
        if kind not in ("checkbox", "dropdown", "string"):
            raise ValueError("unsupported Mod preference type")
        if "linux" in preference.get("disabledOn", []) or "defaultValue" not in preference:
            continue
        value = preference["defaultValue"]
        if kind == "checkbox" and not isinstance(value, bool):
            raise ValueError("invalid checkbox default in Mod preferences")
        if kind != "checkbox" and not isinstance(value, (str, int, float)):
            raise ValueError("invalid string default in Mod preferences")
        defaults[name] = value if kind == "checkbox" else str(value)
    return defaults


def prepare_mod(profile, read_personal):
    """Return atomic-write inputs; the caller must call release_lock() in finally.

    Only a first installation is seeded. Zen subsequently owns this Mod's
    updates, enabled state, preference choices, and generated stylesheet.
    """
    profile = Path(profile).resolve()
    try:
        if not profile.is_dir():
            raise ValueError("the selected profile does not exist")
        lock_profile(profile, read_personal)
        return _prepare_mod(profile, read_personal)
    except (OSError, ValueError, TypeError, SyntaxError, RuntimeError) as error:
        warn(str(error))
        release_lock()
        return []


def _prepare_mod(profile, read_personal):
    targets = {}

    def read(relative):
        path = profile / relative
        target, content, mode = read_personal(path)
        if target == profile / ".parentlock" or target in targets.values():
            raise ValueError("Mod files and preference files must be separate paths")
        targets[relative] = target
        return target, content, mode

    registry_path, registry_content, registry_mode = read("zen-themes.json")
    registry = read_json(registry_content) if registry_path.exists() else {}
    if not isinstance(registry, dict):
        raise ValueError("zen-themes.json must contain a JSON object")
    if MOD_ID in registry:
        # Existing installations, including disabled Mods, belong to the user.
        if not isinstance(registry[MOD_ID], dict) or registry[MOD_ID].get("id") != MOD_ID:
            raise ValueError("the existing Better Find Bar registry entry is invalid")
        return []

    mod_dir = profile / "chrome/zen-themes" / MOD_ID
    asset_names = ("chrome.css", "readme.md", "preferences.json")
    if mod_dir.is_symlink() or (mod_dir.exists() and not mod_dir.is_dir()):
        raise ValueError("the unregistered Better Find Bar path is not a regular directory")
    if mod_dir.exists() and any(
        path.name not in asset_names or path.is_symlink() or not path.is_file()
        for path in mod_dir.iterdir()
    ):
        raise ValueError("an unregistered Better Find Bar folder contains personal files; restore its registry entry first")
    cache_path, _, cache_mode = read("chrome/zen-themes.css")
    prefs_path, prefs_content, prefs_mode = read("prefs.js")
    _, user_content, _ = read("user.js")
    existing_preferences = preference_names(prefs_content) | preference_names(user_content)

    # Resolve all other enabled styles before downloading or publishing anything.
    # Do not silently omit an existing Mod when its files or registry are broken.
    styles = []
    for mod_id, mod in registry.items():
        if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", mod_id) or not isinstance(mod, dict):
            raise ValueError("invalid existing Mod registry entry")
        if mod.get("id") != mod_id or not isinstance(mod.get("enabled", True), bool):
            raise ValueError("invalid existing Mod identity or enabled state")
        if not mod.get("enabled", True):
            continue
        _, content, _ = read(f"chrome/zen-themes/{mod_id}/chrome.css")
        if not content:
            raise ValueError(f"an enabled Mod is missing its stylesheet: {mod_id}")
        content.decode("utf-8")
        styles.append((mod_id, content))

    manifest = read_json(download(MANIFEST_URL))
    if not isinstance(manifest, dict) or manifest.get("id") != MOD_ID or manifest.get("name") != "Better Find Bar":
        raise ValueError("unexpected Better Find Bar metadata")
    for field, filename in (("style", "chrome.css"), ("readme", "readme.md"), ("preferences", "preferences.json")):
        if manifest.get(field) != ASSET_ROOT + filename:
            raise ValueError("unexpected Better Find Bar asset URL")
    if not isinstance(manifest.get("version"), str) or not manifest["version"]:
        raise ValueError("Better Find Bar metadata has no version")

    assets = {name: download(ASSET_ROOT + name) for name in asset_names}
    if "findbar" not in assets["chrome.css"].decode("utf-8") or assets["chrome.css"].lstrip().startswith(b"<"):
        raise ValueError("the downloaded stylesheet is not Better Find Bar CSS")
    defaults = preference_defaults(read_json(assets["preferences.json"]))
    defaults = {name: value for name, value in defaults.items() if name not in existing_preferences}

    writes = []
    for name, content in assets.items():
        target, existing, mode = read(f"chrome/zen-themes/{MOD_ID}/{name}")
        # A previous publication can fail between atomic file replacements.
        # Retry only matching official assets; never replace an unregistered edit.
        if target.exists() and existing != content:
            raise ValueError("an unregistered Better Find Bar asset was edited; restore its registry entry first")
        writes.append((target, content, mode))
    registry[MOD_ID] = dict(manifest, enabled=True)
    styles.append((MOD_ID, assets["chrome.css"]))
    cache = b"/* Zen Mods - Generated by Luna setup; managed by Zen after installation. */\n"
    for mod_id, content in styles:
        cache += f"\n/* Mod: {mod_id} */\n".encode("ascii") + content + b"\n"
    writes.append((cache_path, cache, cache_mode))

    if defaults:
        newline = b"\r\n" if b"\r\n" in prefs_content else b"\n"
        if prefs_content and not prefs_content.endswith(b"\n"):
            prefs_content += newline
        # Seed missing values once in prefs.js, not user.js: Zen's Mod settings
        # must remain editable on subsequent browser launches.
        prefs_content += b"// Initial Better Find Bar defaults from Luna setup." + newline
        for name, value in defaults.items():
            prefs_content += f"user_pref({json.dumps(name)}, {json.dumps(value)});".encode("ascii") + newline
        writes.append((prefs_path, prefs_content, prefs_mode))

    # Registration is the final commit: a successful retry must not skip missing
    # assets or defaults after an earlier required file write failed.
    writes.append((registry_path, (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), registry_mode))
    return writes
