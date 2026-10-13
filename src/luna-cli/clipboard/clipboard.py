"""Cliphist adapter for Luna's menu; clipboard bytes never enter shell arguments."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time


def run(*args, data=None):
    if args[0] == "wl-copy":
        # The clipboard owner forks and keeps its output descriptors open.
        subprocess.run(args, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=15)
        return b""
    return subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True, timeout=15).stdout


def runtime():
    path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/luna-{os.getuid()}")) / "luna-clipboard"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def watch():
    # Hold a session lock rather than matching or killing unrelated clipboard watchers.
    with (runtime() / "watch.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        children = [subprocess.Popen(["wl-paste", "--type", kind, "--watch", "cliphist", "store"])
                    for kind in ("text", "image")]
        def stop(*_):
            for child in children:
                child.terminate()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            while all(child.poll() is None for child in children):
                time.sleep(1)
        finally:
            stop()
            for child in children:
                child.wait()


def listing():
    entries = []
    try:
        output = run("cliphist", "list")
    except subprocess.CalledProcessError as error:
        if b"please store something first" in error.stderr:
            return []
        raise
    for line in output.decode("utf-8", "replace").splitlines():
        key, sep, preview = line.partition("\t")
        if sep and key.isdigit():
            entry = {"id": key, "name": preview, "icon": "clipboard"}
            if preview.startswith("[[ binary data "):
                try:
                    image = image_preview(decode(key))
                    if image:
                        entry.update(name="Image", image=image)
                except (OSError, subprocess.SubprocessError):
                    # A watcher or another client may remove an entry during listing.
                    pass
            entries.append(entry)
    return entries


def decode(key):
    if not key.isdigit():
        raise ValueError("Invalid clipboard entry")
    return run("cliphist", "decode", data=(key + "\t\n").encode())


def image_preview(data):
    mime = run("file", "--brief", "--mime-type", "-", data=data).decode().strip()
    if not mime.startswith("image/"):
        return ""
    # Stable content paths let QML reuse thumbnails without mixing different entries.
    directory = runtime() / "images"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / hashlib.sha256(data).hexdigest()
    if not path.exists():
        path.write_bytes(data)
    return path.as_uri()


def preview(key):
    data = decode(key)
    mime = run("file", "--brief", "--mime-type", "-", data=data).decode().strip()
    if mime.startswith("image/"):
        return {"id": key, "mime": mime, "image": image_preview(data), "text": ""}
    try:
        text = data.decode("utf-8")
        if "\x00" in text:
            raise UnicodeError()
        return {"id": key, "mime": mime, "image": "", "text": text}
    except UnicodeError:
        return {"id": key, "mime": mime, "image": "", "text": f"{mime}\n{len(data):,} bytes"}


def active_window():
    return json.loads(run("hyprctl", "-j", "activewindow"))


def paste(key, address):
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("No application was focused when the menu opened")
    data = decode(key)
    run("wl-copy", data=data)
    # Explicitly promote even entries outside cliphist's default deduplication window.
    run("cliphist", "delete", data=(key + "\t\n").encode())
    run("cliphist", "store", data=data)
    time.sleep(0.18)
    window = active_window()
    if window.get("address") != address:
        raise ValueError("Copied, but focus changed; paste manually in the intended application")
    # Terminals use Ctrl+Shift+V; graphical applications use Ctrl+V for text and images.
    terminal = window.get("class", "").lower() in {
        "kitty", "alacritty", "foot", "footclient", "org.wezfurlong.wezterm",
        "com.mitchellh.ghostty", "org.gnome.terminal", "konsole"}
    keys = ["wtype", "-M", "ctrl"]
    if terminal:
        keys += ["-M", "shift"]
    keys += ["-k", "v"]
    if terminal:
        keys += ["-m", "shift"]
    run(*(keys + ["-m", "ctrl"]))


def main():
    action = sys.argv[1]
    if action == "start":
        for executable in ("cliphist", "wl-paste", "wl-copy", "wtype"):
            if not shutil.which(executable):
                raise ValueError(f"Install {executable} before starting clipboard history")
        log = (runtime() / "watch.log").open("ab")
        subprocess.Popen([sys.executable, __file__, "watch"], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    elif action == "watch":
        watch()
    elif action == "list":
        print(json.dumps(listing()))
    elif action == "preview":
        print(json.dumps(preview(sys.argv[2])))
    elif action == "paste":
        paste(sys.argv[2], sys.argv[3])
    elif action == "target":
        print(json.dumps(active_window().get("address", "")))
    elif action == "delete":
        decode(sys.argv[2])
        run("cliphist", "delete", data=(sys.argv[2] + "\t\n").encode())
    elif action == "clear":
        run("cliphist", "wipe")
        shutil.rmtree(runtime() / "images", ignore_errors=True)
    else:
        raise ValueError("Unknown clipboard action")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
