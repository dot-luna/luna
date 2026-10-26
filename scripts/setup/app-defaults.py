#!/usr/bin/python3
"""Apply validated application defaults while preserving personal preference files."""

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


def warn(message):
    print(f"[WARN] {message}", file=sys.stderr)


def update_group(content, group, mime_type, transform, create=False):
    """Change one MIME key, retaining unrelated lines and their original bytes."""
    lines = content.splitlines(keepends=True)
    header = None
    current = None
    found = False
    for index, line in enumerate(lines):
        section = re.fullmatch(rb"\s*\[([^\]\r\n]+)\]\s*", line)
        if section:
            current = section[1]
            if current == group and header is None:
                header = index
            continue
        match = re.match(rb"([ \t]*" + re.escape(mime_type) + rb"[ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?$", line)
        if current != group or not match:
            continue
        found = True
        entries = [entry.strip() for entry in match[2].split(b";") if entry.strip()]
        updated = transform(entries)
        if updated != entries:
            # Drop an emptied removal entry, leaving its section and comments intact.
            if updated:
                lines[index] = match[1] + b";".join(updated) + b";" + (match[3] or b"")
            else:
                lines[index] = b""

    if create and not found:
        entry = mime_type + b"=" + b";".join(transform([])) + b";\n"
        if header is None:
            content = b"".join(lines)
            if content and not content.endswith(b"\n"):
                content += b"\n"
            return content + (b"\n" if content else b"") + b"[" + group + b"]\n" + entry
        if not lines[header].endswith(b"\n"):
            lines[header] += b"\n"
        lines.insert(header + 1, entry)
    return b"".join(lines)


def preference_files(config_home, filename, kind):
    """Read generic and applicable desktop files before writing any of them."""
    repo = Path(__file__).resolve().parents[2]
    names = [filename, f"hyprland-{filename}"]
    for desktop in os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":"):
        if re.fullmatch(r"[a-z0-9_-]+", desktop):
            name = f"{desktop}-{filename}"
            if (config_home / name).exists() or (config_home / name).is_symlink():
                names.append(name)

    # Resolve every destination before writing, preserving personal dotfile symlinks.
    targets = {}
    for name in dict.fromkeys(names):
        target = (config_home / name).resolve()
        if target.is_relative_to(repo):
            raise ValueError(f"{kind} preferences must not point into the Luna checkout")
        if target.exists():
            if not target.is_file():
                raise ValueError(f"Expected a {kind.lower()} preference file: {target}")
            content = target.read_bytes()
            mode = stat.S_IMODE(target.stat().st_mode)
        else:
            content, mode = b"", 0o600
        generic = name == filename or targets.get(target, (None, None, False))[2]
        targets[target] = (content, mode, generic)
    return targets


def write_preference(target, original, content, mode):
    if content == original:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".app-defaults.luna-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def set_terminal(config_home, desktop_id):
    preferred = desktop_id.encode()
    for target, (content, mode, _) in preference_files(config_home, "xdg-terminals.list", "Terminal").items():
        first = next((line.strip() for line in content.splitlines()
                      if line.strip() and not line.lstrip().startswith(b"#")), b"")
        if first != preferred:
            write_preference(target, content, preferred + b"\n" + content, mode)


def set_mime_defaults(config_home, choices):
    for target, (original, mode, generic) in preference_files(config_home, "mimeapps.list", "MIME").items():
        content = original
        for mime_type, desktop_id in choices.items():
            mime_type, preferred = mime_type.encode(), desktop_id.encode()
            content = update_group(content, b"Default Applications", mime_type, lambda entries: [preferred], create=True)
            if generic:
                # Defaults must remain associated with their types. Desktop-specific
                # files may only declare defaults, so associations stay in the generic file.
                content = update_group(content, b"Added Associations", mime_type,
                                       lambda entries: [preferred] + [entry for entry in entries if entry != preferred],
                                       create=True)
                content = update_group(content, b"Removed Associations", mime_type,
                                       lambda entries: [entry for entry in entries if entry != preferred])
        write_preference(target, original, content, mode)


def verify(arguments, expected, label, quiet=False):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=10,
                                env=dict(os.environ, XTE_CACHE_ENABLED="0"))
        if result.returncode == 0 and result.stdout.strip() == expected:
            if not quiet:
                print(f"[OK] {label} set to {expected}.")
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    if not quiet:
        warn(f"{label} preference saved, but selection could not be verified. Check {' '.join(arguments)}.")
    return False


def verify_mime_defaults(choices, media_defaults):
    """Verify every selection, summarizing broad audio/video choices in one line."""
    remaining = dict(choices)
    for pattern, desktop_id in media_defaults.items():
        mime_types = [mime_type for mime_type, selected in choices.items()
                      if mime_type.startswith(pattern[:-1]) and selected == desktop_id]
        if not mime_types:
            continue
        unverified = []
        for mime_type in mime_types:
            if not verify(["xdg-mime", "query", "default", mime_type], desktop_id, "", quiet=True):
                unverified.append(mime_type)
            remaining.pop(mime_type)
        label = f"Default {pattern.split('/')[0]} player"
        if unverified:
            warn(f"{label} preferences saved, but could not verify {len(unverified)} MIME defaults. "
                 f"Check xdg-mime query default {unverified[0]}.")
        else:
            print(f"[OK] {label} set to {desktop_id}.")
    for mime_type, desktop_id in remaining.items():
        verify(["xdg-mime", "query", "default", mime_type], desktop_id, f"Default {mime_type}")


def apply_defaults(config_home, manifest):
    config_home = Path(config_home)
    if not config_home.is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be an absolute path")

    # GIO implements desktop-ID lookup, XDG precedence, quoting and TryExec rules.
    # python-gobject is part of core setup; no desktop application is launched here.
    import gi
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix

    choices = {}
    media_defaults = {}
    # Expand wildcards first so explicit per-format preferences always win,
    # regardless of the Lua table's iteration order.
    for key in sorted(manifest, key=lambda key: (not key.endswith("/*"), key)):
        desktop_id = manifest[key]
        try:
            application = GioUnix.DesktopAppInfo.new(desktop_id)
        except TypeError:
            # PyGObject represents a missing/invalid desktop constructor as NULL.
            application = None
        executable = application.get_executable() if application else None
        if application is None or application.get_is_hidden() or (executable and not shutil.which(executable)):
            warn(f"Default {key} skipped: {desktop_id} is unavailable.")
            continue
        if key == "terminal":
            if "TerminalEmulator" not in (application.get_categories() or "").split(";"):
                warn(f"Default terminal skipped: {desktop_id} is not a terminal emulator.")
                continue
            if not shutil.which("xdg-terminal-exec"):
                warn("Default terminal skipped: xdg-terminal-exec is unavailable.")
                continue
        if key in ("audio/*", "video/*"):
            supported = sorted({mime_type for mime_type in application.get_supported_types() or []
                                if mime_type.startswith(key[:-1])
                                and re.fullmatch(r"[\w!#$&^_.+\-]+/[\w!#$&^_.+\-]+", mime_type, re.ASCII)})
            if not supported:
                warn(f"Default {key} skipped: {desktop_id} advertises no supported types.")
                continue
            # An unavailable explicit choice must leave that format's existing
            # preference intact, rather than falling back to the wildcard.
            choices.update({mime_type: desktop_id for mime_type in supported if mime_type not in manifest})
            media_defaults[key] = desktop_id
            continue
        choices[key] = desktop_id

    if not choices:
        return
    warn("Back up files you want to keep; default application preferences are updated without backups.")
    terminal = choices.pop("terminal", None)
    if terminal:
        set_terminal(config_home, terminal)
        verify(["xdg-terminal-exec", "--print-id"], terminal, "Default terminal")
    if choices:
        set_mime_defaults(config_home, choices)
        verify_mime_defaults(choices, media_defaults)


if __name__ == "__main__":
    try:
        apply_defaults(sys.argv[1], json.load(sys.stdin))
    except (OSError, ValueError, RuntimeError, IndexError, ImportError) as error:
        print(f"Cannot set default applications: {error}", file=sys.stderr)
        sys.exit(1)
