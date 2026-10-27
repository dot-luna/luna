#!/usr/bin/python3
"""Register Luna's desktop launcher after setup links the source applications."""

import os
from pathlib import Path
import stat
import sys
import tempfile


REPO = Path(__file__).resolve().parents[2]


def exec_argument(value):
    # Desktop Exec arguments have two escaping layers: command quoting first,
    # then key-file escapes. Percent signs must survive field-code expansion.
    quoted = "".join("\\" + character if character in '\\"`$' else
                     "%%" if character == "%" else character for character in str(value))
    escaped = quoted.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return '"' + escaped + '"'


def install_settings():
    command = REPO / "bin/luna"
    if not command.is_file() or not os.access(command, os.X_OK):
        raise ValueError(f"Luna command is missing or not executable: {command}")
    if not (REPO / "src/luna-settings/shell.qml").is_file():
        raise ValueError("Luna Settings source is missing; restore src/luna-settings/shell.qml")

    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    if not data_home.is_absolute():
        raise ValueError("XDG_DATA_HOME must be an absolute path")

    # Follow parent aliases for checkout protection, but replace an existing
    # launcher symlink itself so its target is never overwritten.
    destination = (data_home / "applications").resolve() / "luna-settings.desktop"
    if destination.is_relative_to(REPO):
        raise ValueError(f"Desktop launcher would modify the Luna checkout: {destination}")
    if destination.exists() and not destination.is_symlink() and not destination.is_file():
        raise ValueError(f"Desktop launcher must be a file: {destination}")

    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Luna Settings\n"
        "GenericName=Settings\n"
        "Comment=Open Luna Settings\n"
        f"Exec=/usr/bin/env -u LUNA_INSTALL_DIR {exec_argument(command)} settings\n"
        "Icon=preferences-system\n"
        "Terminal=false\n"
        "Categories=Settings;DesktopSettings;\n"
        "Keywords=Luna;Settings;Preferences;Appearance;\n"
        "StartupNotify=false\n"
    ).encode("utf-8")
    if (not destination.is_symlink() and destination.is_file()
            and destination.read_bytes() == content
            and stat.S_IMODE(destination.stat().st_mode) == 0o644):
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".luna-desktop-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        install_settings()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Cannot install Luna Settings launcher: {error}", file=sys.stderr)
        sys.exit(1)
    print("[OK] Luna Settings is available in the app launcher.")
