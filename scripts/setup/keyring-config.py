#!/usr/bin/python3
"""Select GNOME's Secret Service and complete existing SDDM login hooks."""

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


PAM_FILE = Path("/etc/pam.d/sddm")
DBUS_SERVICE = Path("/usr/share/dbus-1/services/org.freedesktop.secrets.service")
REPO = Path(__file__).resolve().parents[2]
HOOKS = (
    ("auth", (), b"-auth optional pam_gnome_keyring.so"),
    ("password", ("use_authtok",), b"-password optional pam_gnome_keyring.so use_authtok"),
    ("session", ("auto_start",), b"-session optional pam_gnome_keyring.so auto_start"),
)


def warn(message):
    print(f"Keyring: {message}", file=sys.stderr)


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path


def outside_repository(path):
    if path.is_relative_to(REPO):
        raise ValueError(f"Refusing to overwrite a file in Luna's checkout: {path}")


def atomic_write(path, content, metadata=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".luna-keyring-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            # A privileged PAM update must retain ownership as well as permissions.
            if metadata is not None and os.geteuid() == 0:
                os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode) if metadata else 0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def pam_content(content):
    # Match only active GNOME module calls, including full module paths and
    # bracketed controls. Continuations count as one directive; comments do not.
    found = set()
    pending = ""
    for physical in os.fsdecode(content).splitlines():
        line = (pending + physical.lstrip()).split("#", 1)[0].rstrip()
        if line.endswith("\\"):
            pending = line[:-1] + " "
            continue
        pending = ""
        match = re.match(r"^\s*-?(auth|password|session)\s+(?:\[[^]]+\]|\S+)\s+(\S+)(.*)$", line)
        if not match or Path(match[2]).name != "pam_gnome_keyring.so":
            continue
        arguments = match[3].split()
        if any(argument.startswith("only_if=") and "sddm" not in argument[8:].split(",")
               for argument in arguments):
            continue
        for group, required, _ in HOOKS:
            if match[1] == group and all(argument in arguments for argument in required):
                found.add(group)
    if pending:
        raise ValueError("SDDM PAM ends with an unfinished continuation")

    missing = [line for group, _, line in HOOKS if group not in found]
    if not missing:
        return content
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    prefix = content if not content or content.endswith(b"\n") else content + newline
    # PAM evaluates each group separately, so these hooks follow that group's
    # existing authentication/password/session work without rewriting its rules.
    return prefix + newline.join((b"# Luna: unlock the login keyring with the login password.", *missing, b""))


def read_sddm(path):
    if absolute_path(path, "SDDM PAM path") != PAM_FILE:
        raise ValueError("Only the SDDM PAM file may be configured")
    target = Path(path).resolve(strict=True)
    outside_repository(target)
    metadata = target.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("SDDM PAM must be an existing regular file")
    return target, target.read_bytes(), metadata


def configure_sddm(path):
    target, content, metadata = read_sddm(path)
    updated = pam_content(content)
    if updated != content:
        atomic_write(target, updated, metadata)


def configure(config_home, data_home):
    absolute_path(config_home, "XDG_CONFIG_HOME")
    data = absolute_path(data_home, "XDG_DATA_HOME")
    destination = data / "dbus-1/services/org.freedesktop.secrets.service"
    # Replace an old override symlink itself, never its target (often in /usr).
    destination = destination.parent.resolve() / destination.name
    outside_repository(destination)
    content = DBUS_SERVICE.read_bytes()
    metadata = None
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            if destination.resolve() == DBUS_SERVICE.resolve():
                content = None
        else:
            metadata = destination.stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("The Secret Service override must be a file")
            if destination.read_bytes() == content:
                content = None
    if content is not None:
        atomic_write(destination, content, metadata)

    # PAM integration is optional: other login managers need their own setup.
    # Existing adequate SDDM hooks need no sudo call or privileged write.
    try:
        _, current, _ = read_sddm(PAM_FILE)
        if pam_content(current) == current:
            return
    except FileNotFoundError:
        warn("SDDM PAM is unavailable; configure login-keyring unlock for your login manager manually.")
        return
    except (OSError, ValueError, RuntimeError) as error:
        warn(f"Cannot configure SDDM auto-unlock: {error}. Configure it manually.")
        return

    sudo = shutil.which("sudo")
    if sudo is None:
        warn("sudo is unavailable; configure SDDM login-keyring unlock manually.")
        return
    try:
        result = subprocess.run([sudo, "/usr/bin/python3", str(Path(__file__).resolve()),
                                 "sddm", str(PAM_FILE)], check=False)
    except OSError as error:
        warn(f"Cannot configure SDDM auto-unlock: {error}. Configure it manually.")
        return
    if result.returncode:
        warn("SDDM auto-unlock setup failed; configure login-keyring unlock manually.")


if __name__ == "__main__":
    try:
        if sys.argv[1] == "configure":
            configure(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "sddm":
            configure_sddm(sys.argv[2])
        else:
            raise ValueError("Expected configure or sddm")
    except (OSError, ValueError, RuntimeError, IndexError) as error:
        print(f"Cannot configure GNOME Keyring: {error}", file=sys.stderr)
        sys.exit(1)
