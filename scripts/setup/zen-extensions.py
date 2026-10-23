#!/usr/bin/python3
"""Merge removable add-ons into the policy used by all native Zen profiles.

Linux Zen reads /etc/zen/policies/policies.json before its distribution policy,
without merging the two. Profile directories are not policy locations. Installing
the policy requires no profile or browser launch; Zen applies it at startup.
"""

import configparser
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


POLICY_FILE = Path("/etc/zen/policies/policies.json")
REPO = Path(__file__).resolve().parents[2]


def warn(message):
    print(f"[WARN] Zen extensions: {message}", file=sys.stderr)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def read_object(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Expected a regular JSON file: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object,
                       parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def native_install(value):
    install = Path(value)
    if not install.is_absolute():
        raise ValueError("ZEN_INSTALL_DIR must be an absolute native Zen installation path")
    if not install.is_dir():
        raise ValueError("Native Zen is unavailable; install zen-browser-bin or set ZEN_INSTALL_DIR")
    install = install.resolve(strict=True)
    application = configparser.ConfigParser(interpolation=None)
    with (install / "application.ini").open(encoding="utf-8") as source:
        application.read_file(source)
    if application.get("App", "Name", fallback="") != "Zen":
        raise ValueError("ZEN_INSTALL_DIR does not identify a native Zen installation")
    if not any((install / name).is_file() and os.access(install / name, os.X_OK)
               for name in ("zen-bin", "zen")):
        raise ValueError("The native Zen executable is unavailable")
    return install


def extension_manifest(path):
    extensions = read_object(Path(path))
    for extension, url in extensions.items():
        if not extension or any(character.isspace() for character in extension):
            raise ValueError("Extension IDs must be nonempty and contain no whitespace")
        if not isinstance(url, str):
            raise ValueError(f"Expected an HTTPS extension URL for {extension}")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or any(character.isspace() for character in url)):
            raise ValueError(f"Expected an HTTPS extension URL for {extension}")
    return extensions


def string_list(value, label):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return value


def merge_extensions(document, desired):
    policies = document.setdefault("policies", {})
    if not isinstance(policies, dict):
        raise ValueError("policies must be a JSON object")
    extensions = policies.setdefault("Extensions", {})
    settings = policies.get("ExtensionSettings", {})
    if not isinstance(extensions, dict) or not isinstance(settings, dict):
        raise ValueError("Extensions and ExtensionSettings must be JSON objects")
    installed = string_list(extensions.get("Install", []), "Extensions.Install")
    removed = string_list(extensions.get("Uninstall", []), "Extensions.Uninstall")
    locked = string_list(extensions.get("Locked", []), "Extensions.Locked")
    default = settings.get("*", {})
    if not isinstance(default, dict):
        raise ValueError("The default ExtensionSettings entry must be an object")

    # Respect an administrator's removal, blocking, or locking decisions instead
    # of silently weakening them. A per-ID mode overrides the wildcard mode.
    for extension in desired:
        specific = settings.get(extension, {})
        if not isinstance(specific, dict):
            raise ValueError(f"ExtensionSettings for {extension} must be an object")
        mode = specific.get("installation_mode", default.get("installation_mode", "allowed"))
        if extension in removed or "*" in removed or extension in locked or "*" in locked:
            raise ValueError(f"Existing removal or lock policy conflicts with {extension}")
        if mode != "allowed":
            raise ValueError(f"Existing ExtensionSettings mode conflicts with {extension}: {mode}")

    # Install alone allows users to disable/remove an add-on. Zen tracks this
    # list per profile, so reruns do not force an unchanged list to reinstall.
    extensions["Install"] = list(dict.fromkeys([*installed, *desired.values()]))


def prepare(install_value, manifest_path):
    install = native_install(install_value)
    desired = extension_manifest(manifest_path)
    if not desired:
        return None

    destination = POLICY_FILE.parent.resolve() / POLICY_FILE.name
    if destination.is_relative_to(REPO) or destination.is_relative_to(install):
        raise ValueError("The system policy directory must be outside Luna and the native installation")
    exists = destination.exists() or destination.is_symlink()
    metadata = destination.stat() if exists else None
    # An existing system policy is authoritative. Only a new system policy is
    # seeded from the package's distribution defaults (such as update settings).
    source = destination if exists else install / "distribution/policies.json"
    document = read_object(source) if source.exists() or source.is_symlink() else {"policies": {}}
    original = json.dumps(document, sort_keys=True)
    merge_extensions(document, desired)
    if exists and json.dumps(document, sort_keys=True) == original:
        return None
    content = (json.dumps(document, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    return destination, content, metadata


def atomic_write(destination, content, metadata):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".luna-zen-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            if metadata is not None and os.geteuid() == 0:
                os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode) if metadata else 0o644)
        # Detach an existing policy symlink instead of modifying its target,
        # which can be the package-owned distribution file.
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply(install, manifest):
    prepared = prepare(install, manifest)
    if prepared is not None:
        atomic_write(*prepared)


def configure(install, manifest):
    try:
        prepared = prepare(install, manifest)
        if prepared is None:
            return
    except (OSError, ValueError, configparser.Error) as error:
        warn(f"Skipped: {error}.")
        return

    sudo = shutil.which("sudo") if os.geteuid() != 0 else None
    if os.geteuid() != 0 and sudo is None:
        warn("sudo is unavailable; rerun setup with sudo available to install the extension policy.")
        return
    warn("Back up policies you want to keep; setup updates native Zen policies without backups.")
    try:
        if os.geteuid() == 0:
            apply(install, manifest)
        else:
            # Re-read and validate under sudo instead of writing a stale merge.
            result = subprocess.run([sudo, "/usr/bin/python3", str(Path(__file__).resolve()),
                                     "apply", install, manifest], check=False)
            if result.returncode:
                warn("Policy setup failed; rerun setup when administrative access is available.")
                return
    except (OSError, ValueError, configparser.Error) as error:
        warn(f"Policy setup failed: {error}. Rerun setup to retry.")
        return
    print("Zen extension policy configured; restart Zen to install the add-ons.")


if __name__ == "__main__":
    try:
        if sys.argv[1] == "configure":
            configure(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "apply":
            apply(sys.argv[2], sys.argv[3])
        else:
            raise ValueError("Expected configure or apply")
    except (OSError, ValueError, configparser.Error, IndexError) as error:
        warn(str(error))
        sys.exit(1)
