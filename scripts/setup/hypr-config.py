#!/usr/bin/python3
"""Publish staged Hyprland modules and preserve personal Lua entry points."""

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[2]
MODULES = ("hyprland", "animations", "bindings", "monitors", "theme", "workspaces")
LEGACY_PATH = Path("config/hypr/.config/hypr/hyprland.lua")
START = b"-- >>> Luna Hyprland >>>"
END = b"-- <<< Luna Hyprland <<<"
LEGACY_ROOT = b"-- Keep the checkout root available to migrated personal settings."
BOM = b"\xef\xbb\xbf"

# Recognize the old shipped loader exactly, allowing CRLF line endings. Anything
# between its first comment and bootstrap call may contain personal Lua otherwise.
LEGACY_PREFIX = rb"""-- Luna's Hyprland entry point; load shared defaults before personal overrides.
local root = os.getenv("LUNA_PATH")

-- Follow config symlinks back to the checkout without depending on the current cwd.
-- A copied entry point instead needs LUNA_PATH set to the Luna checkout directory.
if not root or root == "" then
    local source = debug.getinfo(1, "S").source:sub(2)
    local quoted = "'" .. source:gsub("'", "'\\''") .. "'"
    local pipe = assert(io.popen("readlink -f -- " .. quoted, "r"))
    local path = pipe:read("*l")
    -- Hyprland may reap subprocesses before pclose; use the resolved output instead.
    pipe:close()
    root = path and path:match("^(.*)/config/hypr/%.config/hypr/[^/]+$")
end
assert(root, "Set LUNA_PATH to the Luna checkout directory")

-- dofile runs again on each config load, so saved theme changes are not cached.
dofile(root .. "/default/hypr/bootstrap.lua")(root)
"""


def warn(message):
    print(f"Hyprland: {message}", file=sys.stderr)


def overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path


def git(checkout, *arguments):
    executable = shutil.which("git")
    if executable is None:
        raise ValueError("Git is needed to recognize or recover the old Luna entry point")
    result = subprocess.run([executable, "--no-pager", "-C", str(checkout), *arguments],
                            capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError("Cannot read the old Luna checkout's local Git history")
    return result.stdout


def luna_checkout(path):
    """Recognize this checkout or another local Git checkout with Luna's layout."""
    if path.is_relative_to(REPO):
        return REPO
    directory = path if path.is_dir() else path.parent
    while not directory.exists() and directory != directory.parent:
        directory = directory.parent
    try:
        checkout = Path(os.fsdecode(git(directory, "rev-parse", "--show-toplevel")).strip()).resolve()
        git(checkout, "ls-files", "--error-unmatch", "--",
            "bin/luna", "lib/common.sh", "packages/packages.lua")
        return checkout
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def recover_legacy(checkout):
    # The last non-deletion change still contains the deleted entry. Read its
    # blob directly; never alter the checkout, contact remotes, or execute it.
    revision = git(checkout, "log", "-n1", "--format=%H", "--diff-filter=d",
                   "--", str(LEGACY_PATH)).strip()
    if not re.fullmatch(rb"[0-9a-f]{40,64}", revision):
        raise ValueError("Old Luna entry is missing and cannot be recovered; restore your personal config before setup")
    return git(checkout, "show", revision.decode("ascii") + ":" + str(LEGACY_PATH))


def lua_string(value):
    # Decimal byte escapes work in every Lua short string, including paths with
    # quotes, backslashes, newlines, or non-ASCII bytes; no shell evaluation occurs.
    result = bytearray(b'"')
    for byte in os.fsencode(value):
        if byte in (34, 92):
            result.extend(b"\\" + bytes((byte,)))
        elif byte < 32 or byte >= 127:
            result.extend(f"\\{byte:03d}".encode("ascii"))
        else:
            result.append(byte)
    return bytes(result) + b'"'


def active_lua(content):
    """Hide comments/long strings when recognizing simple manual dofile lines."""
    output = bytearray()
    index = 0
    while index < len(content):
        if content[index:index + 1] in (b"'", b'"'):
            quote = content[index:index + 1]
            end = index + 1
            while end < len(content):
                if content[end:end + 1] == b"\\":
                    end += 2
                elif content[end:end + 1] == quote:
                    end += 1
                    break
                else:
                    end += 1
            output.extend(content[index:end])
            index = end
            continue
        comment = content[index:index + 2] == b"--"
        start = index + 2 if comment else index
        long = re.match(rb"\[(=*)\[", content[start:])
        if long:
            closing = b"]" + long[1] + b"]"
            end = content.find(closing, start + long.end())
            end = len(content) if end < 0 else end + len(closing)
            output.extend(b" " if comment else b"__long_string__")
            output.extend(b"\n" * content[index:end].count(b"\n"))
            index = end
        elif comment:
            end = content.find(b"\n", index)
            index = len(content) if end < 0 else end
        else:
            output.append(content[index])
            index += 1
    return bytes(output)


def manual_include(content, installed):
    literal = rb"""(?:"(?:[^"\\\r\n]|\\.)*"|'(?:[^'\\\r\n]|\\.)*')"""
    pattern = rb"\s*dofile\s*(?:\(\s*(" + literal + rb")\s*\)|(" + literal + rb"))\s*;?\s*"
    escapes = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t",
               ord("\\"): b"\\", ord('"'): b'"', ord("'"): b"'"}

    def unescape(match):
        value = match[0][1:]
        if value.isdigit():
            return bytes((int(value),))
        if value.startswith(b"x") and len(value) == 3:
            return bytes((int(value[1:], 16),))
        if len(value) == 1 and value[0] in escapes:
            return escapes[value[0]]
        raise ValueError("Unsupported manual Lua string escape")

    previous = []
    for line in active_lua(content).splitlines():
        match = re.fullmatch(pattern, line)
        if match:
            try:
                quoted = match[1] or match[2]
                value = re.sub(rb"\\(?:[0-9]{1,3}|x[0-9a-fA-F]{2}|.)", unescape, quoted[1:-1])
                path = Path(os.fsdecode(value))
            except (ValueError, OSError):
                previous.append(line)
                continue
            if path.is_absolute():
                resolved = path.resolve()
                if path == installed or resolved == installed:
                    # Later calls could be conditional or inside a function.
                    # Do not guess Lua control flow or silently skip initialization.
                    if b"".join(previous).strip():
                        raise ValueError("Move the manual Luna dofile to the first Lua statement before setup")
                    return True
                checkout = luna_checkout(resolved)
                if checkout is not None and resolved in (
                    checkout / LEGACY_PATH, checkout / "apps/hypr/hyprland.lua"
                ):
                    raise ValueError("Migrate the manual Luna source dofile to the installed config before setup")
        previous.append(line)
    return False


def managed_include(content, installed):
    original = content
    bom = BOM if content.startswith(BOM) else b""
    content = content[len(bom):]
    shebang = b""
    if content.startswith(b"#!"):
        shebang, separator, content = content.partition(b"\n")
        shebang += separator or b"\n"
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    legacy = False
    lines = content.splitlines(keepends=True)
    count = len(LEGACY_PREFIX.splitlines())
    if b"".join(lines[:count]).replace(b"\r\n", b"\n") == LEGACY_PREFIX:
        content = b"".join(lines[count:])
        legacy = True

    # The reserved block is replaced as a unit when the install path changes.
    kept = []
    inside = False
    for line in content.splitlines(keepends=True):
        marker = line.rstrip(b"\r\n")
        if marker == START:
            if inside:
                raise ValueError("Nested Luna Hyprland markers; repair the managed block before setup")
            inside = True
        elif marker == END:
            if not inside:
                raise ValueError("Unmatched Luna Hyprland marker; repair the managed block before setup")
            inside = False
        elif inside:
            if marker == LEGACY_ROOT:
                legacy = True
        else:
            kept.append(line)
    if inside:
        raise ValueError("Unclosed Luna Hyprland block; repair it before setup")
    personal = b"".join(kept)
    if b"/default/hypr/bootstrap.lua" in active_lua(personal) or LEGACY_PREFIX.splitlines()[0] in personal:
        raise ValueError("Unrecognized old Luna loader; migrate its bootstrap call manually before setup")
    if manual_include(personal, installed):
        if legacy or START in content:
            raise ValueError("Remove the extra manual Luna dofile call before updating the managed block")
        return original

    block = [START, b"dofile(" + lua_string(str(installed)) + b")"]
    if legacy:
        block.extend((LEGACY_ROOT, b"local root = " + lua_string(str(REPO))))
    block.extend((END, b""))
    return bom + shebang + newline.join(block) + personal


def active_entry(active, output):
    parent = active.parent.resolve()
    if luna_checkout(parent) is not None:
        raise ValueError("The active Hyprland config directory points into a Luna checkout")
    if overlaps(parent, output):
        raise ValueError("Installed Hyprland configuration overlaps the active config directory")
    if active.suffix == ".conf":
        warn("Legacy .conf configuration was kept. Convert it to Lua before connecting Luna's Hyprland config.")
        return None
    if active.suffix != ".lua":
        raise ValueError("HYPRLAND_CONFIG must name a .lua or legacy .conf file")
    if not active.exists() and not active.is_symlink() and (
        active.with_suffix(".conf").exists() or active.with_suffix(".conf").is_symlink()
    ):
        warn("Existing hyprland.conf was kept; convert it to Lua before connecting Luna's Hyprland config.")
        return None

    target = active.resolve()
    checkout = luna_checkout(target)
    old_link = active.is_symlink() and checkout is not None and target == checkout / LEGACY_PATH
    if checkout is not None and not old_link:
        raise ValueError("The active Hyprland file points into Luna's source; only the old entry symlink can be migrated")
    if target.is_relative_to(output):
        raise ValueError("The active Hyprland file points into Luna's installed configuration")
    try:
        content = target.read_bytes()
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        if old_link:
            content = recover_legacy(checkout)
            mode = 0o600
        elif active.is_symlink():
            raise ValueError("The active Hyprland symlink is broken; restore its target before setup")
        else:
            content, mode = b"", 0o600
    if old_link:
        normalized = content.removeprefix(BOM).replace(b"\r\n", b"\n")
        if not normalized.startswith(LEGACY_PREFIX):
            raise ValueError("Old Luna entry has an unrecognized loader; migrate it manually before setup")
    updated = managed_include(content, output / "hyprland.lua")
    # Detach only recognized old entry symlinks. Ordinary dotfile links keep their
    # target and permissions; neither current nor previous checkouts are edited.
    if old_link or updated != content:
        return (active if old_link else target, updated, mode)
    return None


def write_file(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".luna-hypr-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure(staging_path, output_path, active_path):
    staging = Path(staging_path)
    output = absolute_path(output_path, "Hyprland configuration destination")
    active = absolute_path(active_path, "HYPRLAND_CONFIG")
    for directory in (output, output / "generated"):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(f"Hyprland configuration destination must be a directory, not a symlink: {directory}")
    output = output.resolve()
    if overlaps(output, REPO) or luna_checkout(output) is not None:
        raise ValueError("Hyprland source and installed configuration must be separate paths")

    writes = []
    for relative, source in (
        *((name + ".lua", name + ".lua") for name in MODULES),
        ("generated/paths.lua", "paths.lua"),
    ):
        path = output / relative
        if path.is_dir() and not path.is_symlink():
            raise ValueError(f"Expected a Hyprland configuration file, found a directory: {path}")
        content = (staging / source).read_bytes()
        if not content:
            raise ValueError(f"Staged Hyprland configuration is empty: {source}")
        writes.append((path, content, 0o600))
    entry = active_entry(active, output)
    if entry is not None:
        writes.append(entry)

    # All generation, migration and path checks finish before replacing files.
    for path, content, mode in writes:
        write_file(path, content, mode)


if __name__ == "__main__":
    try:
        configure(sys.argv[1], sys.argv[2], sys.argv[3])
    except (OSError, ValueError, RuntimeError, IndexError, subprocess.TimeoutExpired) as error:
        print(f"Cannot configure Hyprland: {error}", file=sys.stderr)
        sys.exit(1)
