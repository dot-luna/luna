#!/usr/bin/env bash
# Set default applications after app setup; extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
if [[ "$config_home" != /* ]]; then
    luna_error 'XDG_CONFIG_HOME must be an absolute path.'
    exit 1
fi
export XDG_CONFIG_HOME="$config_home"

# Application packages are optional, including when their setup step is skipped.
for dependency in kitty xdg-terminal-exec; do
    if ! luna_available "$dependency"; then
        luna_warn "Default terminal setup skipped: $dependency is unavailable."
        exit 0
    fi
done

luna_warn 'Back up files you want to keep; default application preferences are updated without backups.'

# Preserve personal lists and their symlinks while giving Kitty first priority.
/usr/bin/python3 - "$config_home" "$script_path" <<'PY'
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

try:
    config_home = Path(sys.argv[1])
    repo = Path(sys.argv[2]).parents[2]
    names = ["xdg-terminals.list", "hyprland-xdg-terminals.list"]

    # Hyprland's list also covers installation from a TTY. Existing lists for
    # the current desktop can outrank it when XDG_CURRENT_DESKTOP has many names.
    for desktop in os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":"):
        if re.fullmatch(r"[a-z0-9_-]+", desktop):
            name = f"{desktop}-xdg-terminals.list"
            if (config_home / name).exists() or (config_home / name).is_symlink():
                names.append(name)

    # Read every destination before writing so invalid paths leave lists intact.
    updates = {}
    for name in dict.fromkeys(names):
        target = (config_home / name).resolve()
        if target.is_relative_to(repo):
            raise ValueError("Terminal preferences must not point into the Luna checkout")
        if target.exists():
            if not target.is_file():
                raise ValueError(f"Expected a terminal preference file: {target}")
            content = target.read_bytes()
            mode = stat.S_IMODE(target.stat().st_mode)
        else:
            content, mode = b"", 0o600
        first = next((line.strip() for line in content.splitlines()
                      if line.strip() and not line.lstrip().startswith(b"#")), b"")
        if first != b"kitty.desktop":
            updates[target] = (b"kitty.desktop\n" + content, mode)

    for target, (content, mode) in updates.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".xdg-terminals.luna-",
                                             delete=False) as output:
                temporary = Path(output.name)
                output.write(content)
                os.fchmod(output.fileno(), mode)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
except (OSError, ValueError, RuntimeError) as error:
    print(f"Cannot set the default terminal: {error}", file=sys.stderr)
    sys.exit(1)
PY

# Inspect the choice without opening a terminal or using a stale cached selection.
if selected=$(XTE_CACHE_ENABLED=0 xdg-terminal-exec --print-id) && [[ "$selected" == kitty.desktop ]]; then
    luna_success 'Default terminal set to Kitty.'
else
    luna_warn 'Kitty preference saved, but selection could not be verified. Check xdg-terminal-exec --print-id.'
fi
