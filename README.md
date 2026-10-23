# Luna

A Hyprland desktop setup for Arch Linux.

## Install

Run from an interactive terminal as your regular user with `sudo` access and `curl` installed:

```sh
curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/install.sh | bash
```

To install a specific version, replace `BRANCH_OR_TAG` with an existing branch or tag:

```sh
curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/install.sh | bash -s -- --ref BRANCH_OR_TAG
```

To test the development installer and install `dev`, use:

```sh
curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/dev/install.sh | bash -s -- --ref dev
```

The URL selects the installer script; `--ref` selects the checkout to install. Each run removes the existing `~/.local/src/luna` directory, including local changes, and clones the requested branch or tag afresh. The old checkout is not backed up.

The installer clones Luna into `~/.local/src/luna`, installs dependencies and fonts, then links the Hyprland configuration, source directories, and `~/.local/bin/luna`. Source links live in `~/.local/src/`. Conflicting paths are backed up beside the originals with `.luna-backup` suffixes, numbered when needed. Setup adds the command directory to your shell's PATH; open a new terminal afterward and run `luna --version`.

Development tools are listed in `packages/packages.mise.lua`: Node.js LTS, plus the latest Bun, pnpm, Python, and uv. After installing core packages, setup uses [mise](https://mise.jdx.dev/) to install them as global defaults, preserving unrelated mise settings and tools. Edit the manifest to change version requests; project mise configurations can override the defaults. Setup adds mise activation to your Bash, Zsh, or fish startup file, backing up existing content. Open a new terminal afterward. Luna's Bluetooth helper uses the system Python so its Arch dependencies remain available.

Git apps are listed in `packages/packages.git.lua` and installed after fonts. Setup clones each repository into `~/.local/src/<name>` and runs its declared install script with `--prefix "$HOME/.local" --non-interactive`. The app manages its own dependencies and native build. Reinstalling replaces that app's source checkout without a backup. Whatly is included from [our personal fork](https://github.com/dot-luna/whatly), with a **WhatsApp** desktop launcher.

Setup automatically enables and starts Docker, logging a warning if it cannot. Package installation may upgrade the system and runs without package-manager confirmations; `sudo` may still ask for your password. The final installation step offers optional NVIDIA setup, with confirmation defaulting to **No**. It supports Turing or newer GPUs using Arch's standard `linux` kernel.

When setup finishes, it automatically reloads the configuration in an active Hyprland session. NVIDIA driver changes still require a reboot.

Luna's terminal messages use colors and separated steps; external tool output is muted gray. Set `NO_COLOR=1` to disable colors. Plain-text logs are saved in `~/.local/state/luna/`, or `$XDG_STATE_HOME/luna/` when set.

## Run setup again

```sh
bash ~/.local/src/luna/scripts/setup.sh
```

To install only the development tools once core packages are available:

```sh
/usr/bin/lua -E ~/.local/src/luna/scripts/setup/mise.lua
```

Pass `--force` to either command to reinstall the requested packages or tools.
