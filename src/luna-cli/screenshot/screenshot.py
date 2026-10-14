"""Capture through grim, retaining the saved image if clipboard ownership fails."""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


MODES = ("region", "screen", "window", "all")
LAUNCHER = Path(__file__).resolve().parents[2] / "launcher"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def command(*args, timeout=10):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError(detail or f"{args[0]} exited with status {result.returncode}")
    return result.stdout


def hyprland(subject):
    return json.loads(command("hyprctl", "-j", subject, timeout=2))


def launcher_visible(value):
    if isinstance(value, dict):
        if value.get("namespace") in ("luna-launcher", "luna-menu-dismiss"):
            return True
        return any(launcher_visible(item) for item in value.values())
    if isinstance(value, list):
        return any(launcher_visible(item) for item in value)
    return False


def hide_launcher():
    # IPC only closes an existing instance; taking a screenshot must never launch the menu.
    try:
        subprocess.run(["qs", "ipc", "-p", str(LAUNCHER), "call", "launcher", "close"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    except (OSError, subprocess.SubprocessError):
        pass

    # Allow the close request to reach the compositor before reading layers or pixels.
    time.sleep(0.2)
    deadline = time.monotonic() + 1.5
    while True:
        try:
            visible = launcher_visible(hyprland("layers"))
        except (ValueError, OSError, subprocess.SubprocessError):
            # Other Wayland compositors can still use region/all after the settling delay.
            return
        if not visible:
            return
        if time.monotonic() >= deadline:
            raise ValueError("Luna's menu did not close; screenshot was not taken")
        time.sleep(0.05)


@contextmanager
def capture_lock():
    directory = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/luna-{os.getuid()}")) / "luna-screenshot"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Keep the inode between calls so another process cannot lock a replacement file.
    descriptor = os.open(directory / "capture.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("A screenshot is already in progress") from error
        yield


def geometry(position, size):
    if not isinstance(position, list) or not isinstance(size, list) or len(position) != 2 or len(size) != 2:
        raise ValueError("The active window has no usable geometry")
    if not all(type(value) is int for value in position + size) or any(value <= 0 for value in size):
        raise ValueError("The active window has no usable geometry")
    return f"{position[0]},{position[1]} {size[0]}x{size[1]}"


def capture_arguments(mode):
    if mode == "region":
        result = subprocess.run(["slurp", "-f", "%x,%y %wx%h"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False)
        detail = result.stderr.decode("utf-8", "replace").strip()
        if result.returncode == 1 and detail.lower() in ("", "selection cancelled", "selection canceled"):
            return None
        if result.returncode:
            raise ValueError(detail or f"slurp exited with status {result.returncode}")
        selected = result.stdout.decode("utf-8", "replace").strip()
        if not re.fullmatch(r"-?\d+,-?\d+ [1-9]\d*x[1-9]\d*", selected):
            raise ValueError("No usable screenshot region was selected")
        # Hyprland can keep the selection layer visible during its closing animation.
        time.sleep(0.2)
        return ["-g", selected]
    if mode == "screen":
        monitors = hyprland("monitors")
        if not isinstance(monitors, list):
            raise ValueError("Could not read the focused monitor")
        focused = next((monitor for monitor in monitors if isinstance(monitor, dict) and monitor.get("focused")), None)
        if not focused or not isinstance(focused.get("name"), str) or not focused["name"]:
            raise ValueError("No focused monitor is available")
        return ["-o", focused["name"]]
    if mode == "window":
        window = hyprland("activewindow")
        if not isinstance(window, dict) or window.get("mapped") is False:
            raise ValueError("No active window is available")
        return ["-g", geometry(window.get("at"), window.get("size"))]
    return []


def copy_image(path):
    # wl-copy forks a clipboard owner: avoid pipes it could keep open indefinitely.
    with path.open("rb") as image, tempfile.TemporaryFile() as errors:
        result = subprocess.run(["wl-copy", "--type", "image/png"], stdin=image,
                                stdout=subprocess.DEVNULL, stderr=errors, timeout=10, check=False)
        if result.returncode:
            errors.seek(0)
            detail = errors.read().decode("utf-8", "replace").strip()
            raise ValueError(detail or f"wl-copy exited with status {result.returncode}")


def capture(mode="region"):
    if mode not in MODES:
        raise ValueError("Choose region, screen, window, or all")
    required = ["grim", "slurp"] if mode == "region" else ["grim"]
    if mode in ("screen", "window"):
        required.append("hyprctl")
    for executable in required:
        if not shutil.which(executable):
            raise ValueError(f"Install {executable} before taking a screenshot")

    with capture_lock():
        hide_launcher()
        arguments = capture_arguments(mode)
        if arguments is None:
            return None

        directory = Path(os.environ.get("LUNA_SCREENSHOT_DIR", str(Path.home() / "Pictures" / "Screenshots"))).expanduser().resolve()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Atomic reservation avoids overwriting even if two captures share a timestamp.
        prefix = "Screenshot_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f") + "_"
        descriptor, filename = tempfile.mkstemp(prefix=prefix, suffix=".png", dir=directory)
        os.close(descriptor)
        path = Path(filename)
        try:
            command("grim", "-t", "png", *arguments, str(path), timeout=30)
            with path.open("rb") as image:
                if image.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                    raise ValueError("grim did not produce a PNG screenshot")
        except BaseException:
            path.unlink(missing_ok=True)
            raise

        try:
            copy_image(path)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            raise ValueError(f"Screenshot saved to {path}, but copying to the clipboard failed: {error}") from error
        return path


def main():
    path = capture(sys.argv[1] if len(sys.argv) > 1 else "region")
    if path is not None:
        print(path)
        notify("Screenshot saved", "Copied to the clipboard.", image=path)


def notify(summary, body, image=None):
    # Feedback must not turn a successful capture into a failure when the server is unavailable.
    arguments = ["notify-send", "--app-name=Luna Screenshot", "--icon=video-display",
                 "--urgency=normal"]
    if image is not None:
        arguments.append(f"--hint=string:image-path:{image}")
    # AppImage launchers can inject older libraries that do not match system notify-send.
    environment = dict(os.environ)
    environment.pop("LD_LIBRARY_PATH", None)
    environment.pop("LD_PRELOAD", None)
    try:
        subprocess.run([*arguments, "--", summary, body], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=3, check=False, env=environment)
    except (OSError, subprocess.SubprocessError):
        pass


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        notify("Screenshot failed", str(error))
        sys.exit(1)
