#!/usr/bin/python3
"""Plan and prepend Luna's shell source line without changing personal settings."""

import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile


def literal_source_word(value):
    # Recognize literal paths without evaluating shell expansions or user code.
    # Stop at unquoted whitespace so a trailing comment does not affect matching.
    quote = None
    escaped = False
    for character in value:
        if escaped:
            escaped = False
        elif character == "\\" and quote != "'":
            escaped = True
        elif quote:
            if character == quote:
                quote = None
            elif quote == '"' and character in "$`":
                return False
        elif character in "'\"":
            quote = character
        elif character.isspace():
            break
        elif character in "$`*?[]~;|&()<>":
            return False
    return quote is None and not escaped


def already_sourced(content, installed):
    for line in os.fsdecode(content).splitlines():
        match = re.fullmatch(r"\s*(?:source|\.)\s+(.+)", line)
        if not match or not literal_source_word(match[1]):
            continue
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            continue
        if len(words) == 2:
            candidate = Path(words[1])
            if candidate.is_absolute() and (candidate == installed or candidate.resolve() == installed):
                return True
    return False


def plan_source(config_path, installed_path, allow_missing=False):
    config = Path(config_path).absolute()
    installed = Path(installed_path).absolute()
    installed_directory = installed.parent.resolve()
    installed_target = installed_directory / installed.name if allow_missing else installed.resolve()
    repo = Path(__file__).resolve().parents[2]

    # Preserve dotfile symlinks while keeping source and generated files separate.
    # Check each link: publishing can replace a link inside the installed folder.
    target = config.parent.resolve() / config.name
    seen = set()
    while True:
        if target.is_relative_to(repo) or target.is_relative_to(installed_directory):
            raise ValueError("The active .zshrc points into Luna's source or generated configs")
        if target in seen:
            raise ValueError("The active .zshrc contains a symlink loop")
        seen.add(target)
        if not target.is_symlink():
            break
        link = target.readlink()
        target = link if link.is_absolute() else target.parent / link
        target = target.parent.resolve() / target.name
    if not allow_missing and not installed.is_file():
        raise ValueError("Install Luna's Zsh config before adding its source line")
    if any(character in str(installed) for character in "\r\n"):
        raise ValueError("Zsh source paths cannot contain line breaks")

    try:
        content = target.read_bytes()
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        content = b""
        mode = 0o600
    if already_sourced(content, installed_target):
        return

    prefix = os.fsencode("source " + shlex.quote(str(installed)) + "\n")
    return target, prefix + content, mode


def prepend_source(config_path, installed_path):
    update = plan_source(config_path, installed_path)
    if update is None:
        return
    target, content, mode = update
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".zshrc.luna-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "include":
            prepend_source(sys.argv[2], sys.argv[3])
        else:
            raise ValueError("Expected include")
    except (OSError, ValueError, IndexError) as error:
        print(f"Cannot configure Zsh: {error}", file=sys.stderr)
        sys.exit(1)
