# Luna

A Hyprland desktop setup for Arch Linux.

## Install

Back up files you want to keep before installing. Setup replaces conflicting source/command paths and updates shell startup files without automatic backups.

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

The URL selects the installer script; `--ref` selects the branch or tag to install. Existing Luna checkouts are updated in place: branches fast-forward to the latest remote commit, and tags are fetched and checked out detached. Local edits and commits are preserved; conflicting edits or diverged branches stop the update so you can resolve them before retrying. An existing non-Git path at the install location is still replaced without a backup.

The installer uses `LUNA_INSTALL_DIR` for the checkout, defaulting to `~/.local/src/luna` when unset or empty. Set it to an absolute path to use a coding checkout, for example `LUNA_INSTALL_DIR="$HOME/coding/luna" bash install.sh --ref dev`. It installs dependencies and fonts, then links source directories and `~/.local/bin/luna`. Source links live in `~/.local/src/`. Include Luna's configuration files from the checkout in your own Hyprland configuration. Setup adds the command directory to your shell's PATH; open a new terminal afterward and run `luna --version`.

The `luna` command also respects `LUNA_INSTALL_DIR`, so `LUNA_INSTALL_DIR="$HOME/coding/luna" luna --version` uses your coding checkout. When unset or empty, it uses the checkout containing the launcher, following symlinks. Export the variable in your shell to use that checkout for subsequent commands.

Development tools are listed in `packages/packages.mise.lua`: Node.js LTS, plus the latest Bun, pnpm, Python, and uv. After installing core packages, setup uses [mise](https://mise.jdx.dev/) to install them as global defaults, preserving unrelated mise settings and tools. Edit the manifest to change version requests; project mise configurations can override the defaults. Setup adds mise activation to your Bash or Zsh startup file while preserving existing contents. Open a new terminal afterward. Luna's Bluetooth helper uses the system Python so its Arch dependencies remain available.

Git apps are listed in `packages/packages.git.lua` and installed after fonts. Setup clones each repository into `~/.local/src/<name>` and runs its declared install script with `--prefix "$HOME/.local" --non-interactive`. The app manages its own dependencies and native build. Reinstalling replaces that app's source checkout without a backup. Whatly is included from [our personal fork](https://github.com/dot-luna/whatly), with a **WhatsApp** desktop launcher.

Package installation may upgrade the system and runs without package-manager confirmations; `sudo` may still ask for your password. Setup does not enable Docker or run NVIDIA driver installation.

After the installation steps, setup replaces the installed Tokyo Night theme with the bundled copy and selects it, including on reruns. Theme setup failures warn and continue. Setup then reloads the configuration in an active Hyprland session.

Luna's terminal messages use colors and separated steps; external tool output is muted gray. Set `NO_COLOR=1` to disable colors. Plain-text logs are saved in `~/.local/state/luna/`, or `$XDG_STATE_HOME/luna/` when set.

## Run setup again

```sh
bash ~/.local/src/luna/scripts/setup.sh
```

Setup ignores extra arguments. It installs missing packages, upgrades installed packages, and skips reinstalling current versions. Optional steps warn and continue on failure; core dependencies and required source/command links must succeed.

To install only the development tools once core packages are available:

```sh
/usr/bin/lua -E ~/.local/src/luna/scripts/setup/mise.lua
```
