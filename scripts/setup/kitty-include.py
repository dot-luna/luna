#!/usr/bin/python3
"""Prepend Luna's include during app setup without rewriting personal Kitty settings."""

import io
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def expand_include(value):
    # Kitty expands ~, $VAR and ${VAR}, with $$ representing a literal dollar.
    # Its built-in OS value takes precedence over environment variables.
    environment = dict(os.environ, KITTY_OS="linux")
    value = os.path.expanduser(value).replace("$$", "\0")
    value = re.sub(r"\$(?:(\w+)|\{([^}]+)\})",
                   lambda match: environment.get(match[1] or match[2], match[0]), value)
    return value.replace("\0", "$")


def config_lines(content):
    # Kitty joins lines beginning with a backslash onto the previous directive.
    # Normalize line endings for matching only; retain the source bytes for writing.
    pending = None
    for physical in io.StringIO(os.fsdecode(content), newline=None):
        line = physical.lstrip().rstrip("\n")
        if pending is not None and line.startswith("\\"):
            pending += line[1:]
        else:
            if pending is not None:
                yield pending
            pending = line
    if pending is not None:
        yield pending


def prepend_include(config_path, installed_path):
    config = Path(config_path).absolute()
    installed = Path(installed_path).absolute()
    target = config.resolve()
    installed_target = installed.resolve()
    repo = Path(__file__).resolve().parents[2]

    # Keep symlinks intact, but never edit a source or generated config through one.
    if target.is_relative_to(repo) or target.is_relative_to(installed_target.parent):
        raise ValueError("The active Kitty config points into Luna's source or generated configs")
    if not installed.is_file():
        raise ValueError("Install Luna's Kitty config before adding its include")
    if any(character in str(installed) for character in "\r\n"):
        raise ValueError("Kitty include paths cannot contain line breaks")

    try:
        content = target.read_bytes()
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        content = b""
        mode = 0o600

    # Match active directives anywhere, including equivalent relative/home paths.
    # Resolve relatives against Kitty's logical config path, even for a symlink.
    for line in config_lines(content):
        match = re.fullmatch(r"\s*include\s+(.+?)\s*", line)
        if match:
            included = Path(expand_include(match[1]))
            if not included.is_absolute():
                included = config.parent / included
            if included.resolve() == installed_target:
                return

    # Includes consume the whole unquoted path, including spaces. Escape dollars
    # for Kitty rather than for a shell, and retain the original bytes verbatim.
    prefix = os.fsencode("include " + str(installed).replace("$", "$$") + "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".kitty.conf.luna-", delete=False) as output:
            temporary = Path(output.name)
            output.write(prefix)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        prepend_include(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, IndexError) as error:
        print(f"Cannot configure Kitty include: {error}", file=sys.stderr)
        sys.exit(1)
