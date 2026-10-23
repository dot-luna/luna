# Luna

A Hyprland desktop setup for Arch Linux.

## Install

Back up files you want to keep before installing. Setup replaces conflicting source/command paths and installed app configs, and updates shell startup files and default application preferences without automatic backups.

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

Skip selected setup steps with one comma-separated option:

```sh
bash install.sh --skip=git-apps,fonts,mise
```

For the downloaded installer, pass the same option after `bash -s --`. It also works with `--ref`. Available step names are `lua`, `core`, `mise`, `aur`, `main`, `fonts`, `git-apps`, `src`, `command`, `postinstall`, `apps`, `keyring`, `defaults`, `session`, and `cleanup`. `main` installs application packages; `apps` installs app configurations; `postinstall` selects the bundled Tokyo Night theme; `keyring` configures desktop secret storage; `defaults` sets default applications; `cleanup` removes replaced applications at the end. Empty or unknown names are rejected before installation starts.

Only the named steps are skipped; the others keep their normal order and behavior. Dependencies needed by remaining steps must already be available when their installation step is skipped. System checks, Git bootstrap, and checkout preparation always run. The `mise` and `command` steps also configure shell startup, even if the final `apps` step is skipped.

The installer uses `LUNA_INSTALL_DIR` for the checkout, defaulting to `~/.local/src/luna` when unset or empty. Set it to an absolute path to use a coding checkout, for example `LUNA_INSTALL_DIR="$HOME/coding/luna" bash install.sh --ref dev`. It installs dependencies and fonts, then links source directories and `~/.local/bin/luna`. Source links live in `~/.local/src/`. App setup installs Luna's Hyprland configuration and includes it from your personal Lua config. Setup adds the command directory to your shell's PATH; open a new terminal afterward and run `luna --version`.

The `luna` command also respects `LUNA_INSTALL_DIR`, so `LUNA_INSTALL_DIR="$HOME/coding/luna" luna --version` uses your coding checkout. When unset or empty, it uses the checkout containing the launcher, following symlinks. Export the variable in your shell to use that checkout for subsequent commands.

Development tools are listed in `packages/packages.mise.lua`: Node.js LTS, plus the latest Bun, pnpm, Python, and uv. After installing core packages, setup uses [mise](https://mise.jdx.dev/) to install them as global defaults, preserving unrelated mise settings and tools. Edit the manifest to change version requests; project mise configurations can override the defaults. Setup adds mise activation to your Bash or Zsh startup file while preserving existing contents. Open a new terminal afterward. Luna's Bluetooth helper uses the system Python so its Arch dependencies remain available.

Git apps are listed in `packages/packages.git.lua` and installed after fonts. Setup clones each repository into `~/.local/src/<name>` and runs its declared install script with `--prefix "$HOME/.local" --non-interactive`. The app manages its own dependencies and native build. Reinstalling replaces that app's source checkout without a backup. Whatly is included from [our personal fork](https://github.com/dot-luna/whatly), with a **WhatsApp** desktop launcher.

Package installation may upgrade the system and runs without package-manager confirmations; `sudo` may still ask for your password. Setup does not enable Docker or run NVIDIA driver installation.

Core packages include Nautilus for graphical file browsing and Yazi for terminal file browsing. The final `cleanup` step removes Dolphin only when Nautilus is installed. It limits dependency cleanup to Dolphin's removal candidates, protects Luna's declared packages and other explicitly installed packages, and lets pacman enforce remaining dependency requirements. If safe dependency cleanup is unavailable, it removes only Dolphin. Independently, when GNOME Keyring is installed, cleanup removes installed `kwallet`, `kwallet-pam`, and `kwalletmanager` packages unless they are declared in Luna's manifest or remaining dependencies prevent removal. This wallet pass does not remove dependencies or personal wallets. Cleanup keeps personal configuration files, the KDE authentication agent, shared Qt libraries needed by other apps, and the GTK portal that provides Open/Save dialogs. Missing tools or package-operation failures warn and continue. Use `--skip=cleanup` to keep the replaced packages.

After the installation steps, setup replaces the installed Tokyo Night theme with the bundled copy and selects it, including on reruns. Theme setup failures warn and continue. It then installs app configurations, configures the keyring, sets default applications, reloads the configuration in an active Hyprland session, and runs cleanup last.

Core setup installs `gnome-keyring` and `libsecret`; main setup adds Seahorse (Passwords and Keys) for managing saved secrets. The `keyring` step selects GNOME Keyring through a user D-Bus service entry under `$XDG_DATA_HOME/dbus-1/services` (normally `~/.local/share/dbus-1/services`) and enables its user socket. Luna initializes its secrets and certificate components when Hyprland starts, publishing the display environment so graphical unlock prompts can open. Setup does not restart an existing secret-storage provider; log out and back in after installation.

For SDDM, setup preserves existing PAM configuration and adds missing optional GNOME Keyring login hooks using `sudo` when needed. A normal password login creates or unlocks the password-protected login keyring through [GNOME Keyring's PAM integration](https://wiki.gnome.org/Projects/GnomeKeyring/Pam). Automatic login and fingerprint-only login do not supply the password needed to unlock it; other login managers need their own PAM integration. Setup leaves existing keyrings and passwords intact, does not migrate secrets from KDE Wallet, and does not create passwordless keyrings. Missing SDDM or unavailable privileged updates warn with next steps; required user service-file updates must succeed. Back up files you want to keep before setup; no automatic backups are created.

Run `bash /path/to/luna/scripts/setup/keyring.sh` to configure keyring integration separately. `--skip=keyring` skips this configuration step; `--skip=keyring,cleanup` also keeps KDE Wallet packages. Package installation and Luna's Hyprland startup hook remain separate from those skip choices.

Default app choices live in `default/apps.lua`, using desktop entry IDs as values:

```lua
return {
    terminal = "kitty.desktop",
    ["inode/directory"] = "org.gnome.Nautilus.desktop",
    ["x-scheme-handler/http"] = "zen.desktop",
    ["x-scheme-handler/https"] = "zen.desktop",
    ["text/html"] = "zen.desktop",
    ["application/xhtml+xml"] = "zen.desktop",
}
```

The `terminal` key selects the preferred terminal for [xdg-terminal-exec](https://github.com/Vladimir-csp/xdg-terminal-exec). Other keys are MIME types or URL schemes such as `inode/directory` or `x-scheme-handler/https`. The `defaults` step reads this manifest; edit it to change the choices without editing setup scripts. Unavailable applications warn and skip independently; invalid manifests or required file update failures stop the step.

The terminal preference is written to `$XDG_CONFIG_HOME/xdg-terminals.list` and `hyprland-xdg-terminals.list`, plus any existing user lists for desktops in `XDG_CURRENT_DESKTOP`. The config directory defaults to `~/.config`; it is independent of `LUNA_CONFIG_DIR`. Other list contents, permissions, and symlinks are preserved. Reruns restore the selected terminal's priority without repeatedly adding entries.

MIME preferences are written to `mimeapps.list`, `hyprland-mimeapps.list`, and existing current-desktop lists under `$XDG_CONFIG_HOME`, preserving unrelated associations. The bundled manifest selects Nautilus for folders and Zen for HTTP/HTTPS links and HTML/XHTML files. Check them with `xdg-mime query default inode/directory` and `xdg-mime query default x-scheme-handler/https`.

Use `--skip=defaults` to keep your terminal, browser, and file-manager preferences, or run `bash /path/to/luna/scripts/setup/defaults.sh` to apply them separately. Check the selected terminal with `xdg-terminal-exec --print-id`; launch it with `xdg-terminal-exec`. This preference applies to callers using that mechanism. Luna's existing Kitty-specific launcher dialogs still launch Kitty directly.

`LUNA_CONFIG_DIR` sets the absolute directory for installed app configs. It defaults to `$XDG_CONFIG_HOME/luna`, or `~/.config/luna` when `XDG_CONFIG_HOME` is unset or empty. An unset or empty `LUNA_CONFIG_DIR` uses this default. Setup installs Kitty under `kitty/`, Starship under `starship/`, Zsh under `zsh/`, Zen styles under `zen/`, and Hyprland under `hypr/` inside that directory.

Setup copies `apps/kitty/kitty.conf` to `$LUNA_CONFIG_DIR/kitty/kitty.conf` and generates `theme.conf` beside it from Luna's selected theme and font preferences. Font size and window behavior stay in the static config.

Setup prepends an `include` for the installed Luna config to `$XDG_CONFIG_HOME/kitty/kitty.conf` when it is missing, creating the file if needed. `KITTY_CONFIG_DIRECTORY` can select a different absolute Kitty config directory. Existing contents and symlinks are preserved; a matching include anywhere in the file is left as-is. Personal settings remain below a newly added include, so they can override Luna's defaults. Setup does not reload Kitty.

Hyprland follows the same installed-config pattern: `apps/hypr/` contains the maintained Lua entry point and modules, copied to `$LUNA_CONFIG_DIR/hypr`. Setup generates the checkout location in `hypr/generated/paths.lua` and prepends a managed `dofile` block to `$XDG_CONFIG_HOME/hypr/hyprland.lua`, creating it if absent. Personal settings remain after the include, and existing personal symlinks and file modes are preserved. `HYPRLAND_CONFIG` can select an absolute custom Lua file. The recognized old Luna loader is migrated while keeping its personal settings; old symlinks into the checkout are detached. Deleted old targets are recovered from local Git history when available, otherwise setup reports a migration error instead of discarding settings.

A legacy `.conf`-only configuration is preserved and activation is skipped with a warning until it is converted to Lua. Run `bash /path/to/luna/scripts/setup/hypr.sh` to install just this app config; it does not reload the desktop. The full setup's `session` step attempts a reload afterward. Hyprland continues reading the latest resolved Luna theme on startup or manual reload. See the [Hyprland app guide](apps/hypr/README.md) for configuration and migration details.

Setup copies `apps/starship/starship.toml` to `$LUNA_CONFIG_DIR/starship/starship.toml`. It preserves the original prompt's bracketed modules, two-level directory display, cyan repository root, and 200 ms command timeout. Zsh selects the installed file through `STARSHIP_CONFIG`, preserving a nonempty override. The existing `~/.config/starship.toml` and its symlink are left intact. Refresh only this config with `bash /path/to/luna/scripts/setup/starship.sh`.

Zen setup generates `$LUNA_CONFIG_DIR/zen/generated/userChrome.css` and `userContent.css` from Luna's selected theme. Browser colors and the UI font follow Luna's palette and font preferences. The browser stylesheet targets Zen's tabs, sidebar, toolbar, address bar, and menus; website colors remain their own. This uses local CSS and does not require a Zen Mod or extension.

Square corners are conditional on the resolved theme's `hyprland.decoration.rounding`: exactly `0` adds zero-radius overrides to Zen's browser UI and ordinary CSS elements on HTTP(S) websites. Any positive value emits no corner overrides, leaving Zen and websites' own rounding intact. Rerunning setup after changing this value replaces the generated styles, removing earlier square-corner rules when appropriate. Shapes drawn within images, SVG, canvas, or clipping paths are not controlled by `border-radius`.

Setup adds a managed import to each of the selected profile's `chrome/userChrome.css` and `chrome/userContent.css`, creating these files if needed. It preserves personal CSS, file permissions, and symlinks. It also adds a managed `user.js` preference to enable `toolkit.legacyUserProfileCustomizations.stylesheets`; other preferences remain intact. Back up files you want to keep before setup; no automatic backups are created.

The profile is selected from Zen's existing profile registry. Native Linux installations use `~/.zen` when that directory exists, otherwise `$XDG_CONFIG_HOME/zen`. If there is no profile yet, open Zen once and rerun `bash /path/to/luna/scripts/setup/zen.sh`. Ambiguous profiles are skipped with a warning; use `ZEN_PROFILE_DIR=/absolute/path/to/profile bash /path/to/luna/scripts/setup/zen.sh` to select an existing profile explicitly, including one in a different installation. Setup never launches Zen or creates browser profile registries. Restart Zen to load the updated styles and preference.

For Zsh, setup prepends a source line for `$LUNA_CONFIG_DIR/zsh/zshrc` to `${ZDOTDIR:-$HOME}/.zshrc`, preserving the existing contents, permissions, and symlinks. Repeated setup does not duplicate the source line. There are four maintained files:

- `zshrc`: loads the generated environment and other files, adds `~/.local/bin` and pnpm's installed `bin` to `PATH`, and sets history and Emacs keybindings. `PNPM_HOME` defaults to `$XDG_DATA_HOME/pnpm` (normally `~/.local/share/pnpm`), preserving an existing value. History defaults to `~/.histfile` with 1,000 entries.
- `completion.zsh`: adds packaged completion definitions and initializes Zsh completions once, including when mise is unavailable.
- `tools.zsh`: activates mise, configures zoxide's `cd=z` and `cdi=zi` aliases, adds eza shortcuts, enables fzf with fd/bat/eza integration, and selects and initializes Starship. Existing `FZF_*` settings take precedence, including empty values that disable shortcuts.
- `plugins.zsh`: loads fzf-tab, command suggestions, and syntax highlighting before the first prompt, after personal startup files have finished configuring completion and keybindings.

Setup keeps generated output under `$LUNA_CONFIG_DIR/zsh/generated/`. Other apps can use the same `generated/` convention; directories with that name are ignored by Git throughout the repository.

- `env.zsh`: exports `LUNA_INSTALL_DIR` and `LUNA_CONFIG_DIR`, using the setup checkout and destination as defaults. Nonempty shell overrides take precedence.
- `mise-completion.zsh`: generated by `mise --cd "$HOME" completion zsh`. Missing mise or generation failure warns and preserves an existing completion file.

Rerunning setup migrates saved completions from the previous `autogenerated/` or flat layout into `generated/` if needed and removes retired Luna files. Other files in the installed directory are preserved.

The main package group installs `zsh-autosuggestions`, `zsh-syntax-highlighting`, `zsh-completions`, `fzf`, `zoxide`, `bat`, `eza`, and `fd` from Arch's repositories, plus `fzf-tab` from the AUR. Missing optional tools or plugins are skipped during shell startup. There is no plugin download step when opening a terminal.

Use Right Arrow to accept a history suggestion, Tab for fuzzy completion, `Ctrl-R` to search command history, `Ctrl-T` to insert a file path, and `Alt-C` to select a directory. `ll` lists files with details, `la` includes hidden files, and `lt` shows a tree. `bat FILE` displays highlighted file contents. These integrations apply to interactive Zsh shells; personal settings after Luna's source line can override them.

Mise activation runs from `tools.zsh` when a shell starts, so it uses the current environment. It is not saved as a snapshot of the installer's `PATH`. Personal settings after Luna's source line can override its defaults. Flutter and Dart remain managed by mise. To refresh only Zsh's files, run `bash /path/to/luna/scripts/setup/zsh.sh`; open a new terminal afterward.

The config-directory override controls app output only; Luna's theme selection, resolved `theme.json`, and font preferences remain under `$XDG_CONFIG_HOME/luna`. The Kitty and Zen generators use Luna's defaults when no theme is selected. After changing themes, rounding, or font preferences, refresh app configs with `bash /path/to/luna/scripts/setup/apps.sh`, using the same `LUNA_CONFIG_DIR` override if you set one. This replaces installed app files from the checkout and refreshes their includes; it does not reload Kitty, Zen, or the current shell.

Luna's terminal messages use colors and separated steps; external tool output is muted gray. Set `NO_COLOR=1` to disable colors. Plain-text logs are saved in `~/.local/state/luna/`, or `$XDG_STATE_HOME/luna/` when set.

## Run setup again

```sh
bash ~/.local/src/luna/scripts/setup.sh
```

The setup runner accepts the same skip option when rerunning a local checkout:

```sh
bash ~/.local/src/luna/scripts/setup.sh --skip=git-apps,fonts,mise
```

Unrelated extra arguments are ignored by the setup runner and individual setup scripts. Enabled package steps install missing packages, upgrade installed packages, and skip reinstalling current versions. Optional steps warn and continue on failure; enabled core dependencies, required source/command links, and app configuration installation must succeed.

To apply default applications and clean up replaced packages after installing dependencies:

```sh
bash /path/to/luna/scripts/setup/defaults.sh
bash /path/to/luna/scripts/setup/cleanup.sh
```

To install only the development tools once core packages are available:

```sh
/usr/bin/lua -E ~/.local/src/luna/scripts/setup/mise.lua
```
