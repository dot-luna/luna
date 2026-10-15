# Luna

A Hyprland desktop setup for Arch Linux.

## Install

Run from an interactive terminal as your regular user with `sudo` access and `curl` installed:

```sh
curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/scripts/install.sh | bash
```

To install a specific version, replace `BRANCH_OR_TAG` with an existing branch or tag:

```sh
curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/scripts/install.sh | bash -s -- --ref BRANCH_OR_TAG
```

The installer clones Luna into `~/.local/src/luna`, installs dependencies and fonts, then links the Hyprland configuration and source directories. Source links live in `~/.local/src/`. Config and source setup run automatically; conflicting paths are backed up beside the originals with `.luna-backup` suffixes, numbered when needed.

The final step offers optional NVIDIA setup, with confirmation defaulting to **No**. It supports Turing or newer GPUs using Arch's standard `linux` kernel. Package installation may upgrade the system and retains package manager prompts.

Logs are saved in `~/.local/state/luna/`, or `$XDG_STATE_HOME/luna/` when set. An existing checkout must be clean and match the requested branch or tag; the installer reuses it without updating it.

## Run setup again

```sh
bash ~/.local/src/luna/scripts/setup.sh
```
