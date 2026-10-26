#!/usr/bin/python3
"""Stage app trees, run Lua builders, then publish and connect personal configs."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


sys.dont_write_bytecode = True
SETUP = Path(__file__).resolve().parent
REPO = SETUP.parents[1]


def helper(name):
    spec = importlib.util.spec_from_file_location(name, SETUP / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def relative(value):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError("Expected a nonempty relative app path")
    path = Path(value)
    if path.is_absolute() or any(part in (".", "..", "") for part in value.split("/")):
        raise ValueError(f"App paths must stay inside their directory: {value}")
    return path


def absolute(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path


def overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def directory(path):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(f"Expected a configuration directory, not a file or symlink: {path}")


def target_path(connection):
    if connection.get("file_env") and os.environ.get(connection["file_env"]):
        return absolute(os.environ[connection["file_env"]], connection["file_env"])
    base = os.environ["HOME"] if connection.get("base") == "home" else os.environ["XDG_CONFIG_HOME"]
    target = relative(connection["target"])
    override = connection.get("directory_env")
    if override and os.environ.get(override):
        return absolute(os.environ[override], override) / target.name
    return Path(base) / target


def preflight_file(destination, name):
    path = destination / name
    for parent in path.parents:
        if parent == destination.parent:
            break
        directory(parent)
    if path.is_dir() and not path.is_symlink():
        raise ValueError(f"Expected a configuration file, found a directory: {path}")


def tree_files(source):
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"App config trees must contain ordinary files and directories: {path}")
        if path.is_file():
            files.append(path.relative_to(source))
    if not files:
        raise ValueError(f"App configuration is empty: {source}")
    return files


def validate(app, config):
    source = absolute(app["source"], "App source")
    if source.is_symlink() or source.resolve() != REPO / "apps" / app["name"]:
        raise ValueError("App descriptors must remain inside this checkout")
    app["source"] = source
    app["config"] = relative(app["config"])
    config_source = source / app["config"]
    if not config_source.resolve().is_relative_to(source) or not config_source.is_dir():
        raise ValueError(f"App config directory is missing or outside the app: {config_source}")
    if app["builder"]:
        builder = source / relative(app["builder"])
        if not builder.is_file() or not builder.resolve().is_relative_to(source):
            raise ValueError(f"App builder is missing or outside the app: {builder}")
    app["retired"] = [relative(name) for name in app["retired"]]
    destination = config / app["name"]
    directory(destination)
    if overlaps(destination.resolve(), REPO):
        raise ValueError("App source and installed configuration must be separate paths")
    for name in [*tree_files(config_source), *app["retired"]]:
        preflight_file(destination, name)
    for connection in app["connections"]:
        kind = connection.get("type")
        if kind not in ("kitty", "lua", "shell", "mpv", "zen"):
            raise ValueError(f"Unknown app connection type: {kind}")
        if kind in ("kitty", "lua", "shell"):
            relative(connection["source"])
            active = target_path(connection)
            if kind == "kitty" and overlaps(destination.resolve(), active.parent.resolve()):
                raise ValueError("Kitty configuration destination overlaps the active config")
            if kind == "shell":
                helper("zsh-config").plan_source(active, destination / connection["source"], allow_missing=True)
    return destination


def connections(app, staging, destination):
    writes = []
    for connection in app["connections"]:
        kind = connection["type"]
        if kind in ("kitty", "lua", "shell"):
            source = relative(connection["source"])
            if not (staging / source).is_file():
                raise ValueError(f"App connection source is missing: {source}")
            active = target_path(connection)
            if kind == "kitty":
                planned = helper("kitty-include").plan_include(active, destination / source, allow_missing=True)
            elif kind == "shell":
                planned = helper("zsh-config").plan_source(active, destination / source, allow_missing=True)
            else:
                # Hyprland's adapter also understands the old checkout entry point.
                # Other Lua apps only need a literal dofile at the top of their file.
                if app["name"] == "hypr":
                    writes.extend(helper("hypr-config").plan(staging, destination, active))
                    continue
                planned = lua_include(active, destination / source, destination)
            if planned:
                writes.append(planned)
        elif kind == "mpv":
            writes.extend(helper("mpv-config").plan(staging, destination))
        elif kind == "zen":
            styles = {
                "chrome": (staging / "generated/userChrome.css").read_text(),
                "content": (staging / "generated/userContent.css").read_text(),
                "fonts": json.loads((staging / "generated/fonts.json").read_text()),
            }
            available = bool(shutil.which("zen-browser") or shutil.which("zen"))
            writes.extend(helper("zen-profile").plan(str(destination), available, styles))
    # Adapters may include their legacy owned-file plans. The staged tree is the
    # single source for installed files; retain only their personal-file updates.
    return [write for write in writes if not write[0].is_relative_to(destination)
            and not write[0].is_relative_to(destination.resolve())]


def lua_include(active, installed, destination):
    target = active.parent.resolve() / active.name
    seen = set()
    while True:
        if target.is_relative_to(REPO) or target.is_relative_to(destination.resolve()):
            raise ValueError("Personal Lua configuration points into Luna's source or installed configs")
        if target in seen:
            raise ValueError("Personal Lua configuration contains a symlink loop")
        seen.add(target)
        if not target.is_symlink():
            break
        link = target.readlink()
        target = link if link.is_absolute() else target.parent / link
        target = target.parent.resolve() / target.name
    try:
        content, mode = target.read_bytes(), stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        content, mode = b"", 0o600
    # JSON's ordinary UTF-8 quoting is also a Lua string literal for these paths.
    if any(ord(c) < 32 for c in str(installed)):
        raise ValueError("Lua include paths cannot contain control characters")
    line = ("dofile(" + json.dumps(str(installed), ensure_ascii=False) + ")\n").encode()
    if content.startswith(line):
        return None
    return target, line + content, mode


def write_file(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".luna-app-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install(app, destination, config):
    with tempfile.TemporaryDirectory(prefix=".luna-app-") as temporary:
        staging = Path(temporary) / "config"
        shutil.copytree(app["source"] / app["config"], staging)
        if app["builder"]:
            subprocess.run(["/usr/bin/lua", "-E", str(SETUP / "build-app.lua"), str(app["source"]),
                            str(staging), str(destination), str(config)], check=True)
        files = tree_files(staging)
        for name in files:
            preflight_file(destination, name)
        personal = connections(app, staging, destination)

        # Publish only after generation and personal-file validation succeed.
        # Generated helpers precede entry points; unrelated installed files stay.
        files.sort(key=lambda name: (name.parts[0] != "generated", str(name)))
        for name in files:
            source = staging / name
            write_file(destination / name, source.read_bytes(), stat.S_IMODE(source.stat().st_mode))
        for path, content, mode in personal:
            write_file(path, content, mode)
        for name in app["retired"]:
            (destination / name).unlink(missing_ok=True)
        for parent in {name.parent for name in app["retired"] if name.parent != Path(".")}:
            path = destination / parent
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    print(f"Installed {app['name']} configuration.", flush=True)


def main():
    home = absolute(os.environ["HOME"], "HOME")
    xdg = absolute(os.environ.get("XDG_CONFIG_HOME") or str(home / ".config"), "XDG_CONFIG_HOME")
    config = absolute(os.environ.get("LUNA_CONFIG_DIR") or str(xdg / "luna"), "LUNA_CONFIG_DIR")
    os.environ.update(XDG_CONFIG_HOME=str(xdg), LUNA_CONFIG_DIR=str(config))
    apps = json.load(sys.stdin)["apps"]
    destinations = [validate(app, config) for app in apps]
    for app, destination in zip(apps, destinations):
        install(app, destination, config)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Cannot install app configurations: {error}", file=sys.stderr)
        sys.exit(1)
