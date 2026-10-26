#!/usr/bin/python3
"""Install mpv defaults while retaining personal settings and key bindings."""

import os
from pathlib import Path
import re
import stat
import sys
import tempfile


START = b"# >>> Luna mpv >>>"
END = b"# <<< Luna mpv <<<"


def config_paths():
    override = os.environ.get("MPV_HOME")
    if override:
        directory = Path(override)
        if not directory.is_absolute():
            raise ValueError("MPV_HOME must be an absolute path")
        return [directory], directory

    standard = Path(os.environ["XDG_CONFIG_HOME"]) / "mpv"
    legacy = Path(os.environ["HOME"]) / ".mpv"
    preferred = legacy if legacy.is_dir() and not standard.exists() else standard
    return [standard, legacy], preferred


def with_defaults(content, defaults):
    # Only Luna's marked block is refreshed. Personal bytes, including line
    # endings, stay intact and follow the defaults so personal settings win.
    lines = content.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n") == START]
    ends = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n") == END]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            raise ValueError("Repair the incomplete or duplicate Luna mpv configuration block")
        content = b"".join(lines[:starts[0]] + lines[ends[0] + 1:])
    if defaults and not defaults.endswith(b"\n"):
        defaults += b"\n"
    return START + b"\n" + defaults + END + b"\n" + content


def read_personal(path, installed, repo):
    target = path.resolve()
    if target.is_relative_to(repo) or target.is_relative_to(installed.resolve()):
        raise ValueError(f"Personal mpv config points into Luna's source or installed configs: {path}")
    try:
        return target, target.read_bytes(), stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        return target, b"", 0o600


def replace_file(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".mpv.luna-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install(source_path, destination_path):
    source = Path(source_path)
    installed = Path(destination_path)
    repo = Path(__file__).resolve().parents[2]
    directories, preferred = config_paths()
    if installed.is_symlink():
        raise ValueError(f"mpv configuration destination must not be a symlink: {installed}")
    resolved = installed.resolve()
    for protected in [repo, *(directory.resolve() for directory in directories)]:
        if resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
            raise ValueError("mpv configuration destination overlaps the checkout or active config")

    # mpv reads both legacy and XDG settings, from lowest to highest priority,
    # but selects only the highest-priority existing input.conf.
    configs = [directory / "mpv.conf" for directory in directories]
    inputs = [directory / "input.conf" for directory in directories]
    config = next((path for path in reversed(configs) if path.exists() or path.is_symlink()),
                  preferred / "mpv.conf")
    bindings = next((path for path in inputs if path.exists() or path.is_symlink()),
                    preferred / "input.conf")

    # Validate and read every required file before replacing any configuration.
    copies = []
    for name in ("mpv.conf", "input.conf"):
        path = installed / name
        if path.is_dir() and not path.is_symlink():
            raise ValueError(f"Expected a configuration file, found a directory: {path}")
        copies.append((path, (source / name).read_bytes(), 0o644))

    config_target, config_content, config_mode = read_personal(config, installed, repo)
    input_target, input_content, input_mode = read_personal(bindings, installed, repo)
    if config_target == input_target:
        raise ValueError("mpv.conf and input.conf must be separate files")
    # mpv defers included options until after the current profile, which would
    # override personal settings. input.conf has no include directive at all.
    # Refresh both defaults blocks during setup to retain normal last-line wins.
    config_updated = with_defaults(config_content, copies[0][1])
    input_updated = with_defaults(input_content, copies[1][1])

    custom_input = False
    for path in configs:
        if path.is_file() and re.search(rb"(?m)^\s*input-conf\s*=", path.read_bytes()):
            custom_input = True

    for path, content, mode in copies:
        replace_file(path, content, mode)
    for path, previous, updated, mode in (
        (config_target, config_content, config_updated, config_mode),
        (input_target, input_content, input_updated, input_mode),
    ):
        if previous != updated:
            replace_file(path, updated, mode)
    if custom_input:
        print("Warning: Personal mpv input-conf settings override Luna's volume bindings; "
              "add the bindings to your selected input file if needed.", file=sys.stderr)


if __name__ == "__main__":
    try:
        install(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, IndexError) as error:
        print(f"Cannot configure mpv: {error}", file=sys.stderr)
        sys.exit(1)
