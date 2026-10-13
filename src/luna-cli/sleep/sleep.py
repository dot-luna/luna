"""Check sleep support, lock the Wayland session, then request normal systemd sleep."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def locked():
    result = subprocess.run(["hyprctl", "-j", "locked"], check=True, capture_output=True,
                            text=True, timeout=5)
    return json.loads(result.stdout).get("locked") is True


def sleep_session(action, luna):
    if action not in ("suspend", "hibernate"):
        raise RuntimeError("Unknown sleep action")
    if not os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError("Sleep through Luna requires a Wayland session")
    capability = subprocess.run(
        ["busctl", "--timeout=5", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
         "org.freedesktop.login1.Manager", "CanHibernate" if action == "hibernate" else "CanSuspend"],
        check=True, capture_output=True, text=True, timeout=7)
    if capability.stdout.strip() not in ('s "yes"', 's "challenge"'):
        if action == "hibernate":
            raise RuntimeError("Hibernate is unavailable. Configure disk-backed swap and resume first; zram cannot store a hibernation image.")
        raise RuntimeError("Suspend is unavailable or not permitted by system policy.")

    if not locked():
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "luna"
        cache.mkdir(parents=True, exist_ok=True)
        # The locker must survive this helper and stay active after resume or failure.
        with tempfile.TemporaryFile(dir=cache) as log:
            locker = subprocess.Popen([luna, "lock"], stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 10
            while not locked():
                if locker.poll() is not None:
                    raise RuntimeError("Screen locker exited before locking; sleep cancelled.")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Screen lock was not ready; sleep cancelled.")
                time.sleep(0.1)
    if not locked():
        raise RuntimeError("Session unlocked before sleep; sleep cancelled.")
    subprocess.run(["systemctl", action], check=True)


if __name__ == "__main__":
    try:
        sleep_session(sys.argv[1], sys.argv[2])
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
