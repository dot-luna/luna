"""Launch the user's preferred terminal in the focused terminal's local folder."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


PROC = Path("/proc")
SHELLS = Path("/etc/shells")
TERMINALS = {"kitty", "alacritty", "foot", "footclient", "ghostty", "kgx",
             "gnome-terminal-server", "wezterm-gui"}


def query_json(arguments):
    # Desktop state may disappear between a keypress and lookup; never block launch indefinitely.
    try:
        result = subprocess.run(arguments, check=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=1)
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def valid_directory(value):
    # Only existing absolute local paths can be passed to the terminal launcher.
    try:
        return isinstance(value, str) and Path(value).is_absolute() and Path(value).is_dir()
    except (OSError, ValueError):
        return False


def kitty_directory(pid):
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return None
    socket = Path(runtime) / f"luna-kitty-{pid}"
    try:
        available = socket.is_socket()
    except OSError:
        available = False
    if not available:
        return None

    # Query this Kitty process's focused pane, including custom window classes and tabs.
    # Explicitly ignore inherited remote-control passwords so this never opens a prompt.
    windows = query_json(["kitten", "@", "--to", f"unix:{socket}", "--use-password", "never",
                          "ls", "--match", "state:focused"])
    if not isinstance(windows, list):
        return None
    directories = []
    for window in windows:
        if not isinstance(window, dict) or not isinstance(window.get("tabs"), list):
            continue
        for tab in window["tabs"]:
            if not isinstance(tab, dict) or not isinstance(tab.get("windows"), list):
                continue
            for pane in tab["windows"]:
                if isinstance(pane, dict):
                    directories.append(pane.get("cwd"))

    # Use the shell's folder even while a foreground command runs; do not pick another pane.
    if len(directories) == 1 and valid_directory(directories[0]):
        return directories[0]
    return None


def shell_directory(pid):
    # Older Kitty instances and other terminals can expose a single shell through /proc.
    # Multiple shells are ambiguous without terminal IPC, so leave that case to HOME.
    try:
        shells = {str(Path(line.strip()).resolve()) for line in SHELLS.read_text().splitlines()
                  if line.strip().startswith("/")}
        children = set()
        for task in (PROC / str(pid) / "task").glob("*/children"):
            children.update(task.read_text().split())
        directories = []
        for child in children:
            if not child.isdecimal():
                continue
            process = PROC / child
            try:
                executable = str((process / "exe").resolve(strict=True))
            except (OSError, RuntimeError):
                continue
            if executable in shells:
                try:
                    directories.append(str((process / "cwd").resolve(strict=True)))
                except (OSError, RuntimeError):
                    directories.append(None)
        if len(directories) == 1 and valid_directory(directories[0]):
            return directories[0]
    except (OSError, ValueError, RuntimeError):
        pass
    return None


def directory_for(pid=None):
    home = str(Path.home())
    if pid is None:
        focused = query_json(["hyprctl", "-j", "activewindow"])
        pid = focused.get("pid") if isinstance(focused, dict) else None
    if type(pid) is not int or pid <= 0:
        return home

    # Identify the executable, not the window class: browsers must not supply a cwd,
    # while Kitty's custom-class drop-down terminal should behave like any other Kitty.
    try:
        executable = (PROC / str(pid) / "exe").resolve(strict=True).name
    except (OSError, RuntimeError):
        return home
    if executable not in TERMINALS:
        return home
    if executable == "kitty":
        directory = kitty_directory(pid)
        if directory:
            return directory
    return shell_directory(pid) or home


def launch(pid=None):
    directory = directory_for(pid)

    # A project may be removed during lookup. Check again before replacing this helper.
    try:
        os.chdir(directory)
    except OSError:
        directory = str(Path.home())
        os.chdir(directory)

    # Keep spaces and shell metacharacters literal, and honor the current default terminal.
    os.execvp("xdg-terminal-exec", ["xdg-terminal-exec", f"--dir={directory}"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    options = parser.parse_args()
    try:
        launch(options.pid)
    except OSError as error:
        print(f"Could not open the default terminal: {error}", file=sys.stderr)
        sys.exit(1)
