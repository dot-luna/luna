# Windows VM

Luna uses [Dockur Windows](https://github.com/dockur/windows) with Docker Compose and a foreground FreeRDP session, following [Omarchy's lifecycle](https://github.com/omacom/omarchy/blob/master/bin/omarchy-windows-vm). Docker, Compose, FreeRDP 3, KVM, and `/dev/net/tun` must already be available. This command does not install packages, enable Docker, or change user groups. Docker must be running and accessible to the invoking user (`docker info`); membership in the Docker group grants root-equivalent access.

```sh
luna windows install                         # interactive RAM, CPU, disk, and username setup
luna win install --yes                       # defaults: 4G RAM, 2 CPUs, 64G disk
luna win install --ram 8G --cpus 4 --disk 128G
luna win start                               # attach to Windows; stop VM when RDP closes
luna win start --keep-alive                   # leave VM running after RDP closes
luna win stop                                # graceful stop; keep disk and configuration
luna win status
luna win logs                                # last 100 lines, then follow
luna win logs --no-follow --tail 200
luna win delete                              # confirm permanent VM deletion
```

`windows` and `win` are interchangeable. Bare `luna win` displays help.

On the first install in a terminal, Luna prompts for RAM, CPU cores, disk capacity, and the Windows username. Enter accepts the displayed default; invalid values are requested again. RAM and disk answers accept `8`, `8G`, or `8g` (GiB). Explicit command flags skip their corresponding prompts. `--yes` skips all prompts; non-interactive invocations also use defaults for missing options. Existing VM configurations are preserved without prompting when retrying installation.

## Installation and files

`install` creates `$XDG_CONFIG_HOME/luna/windows/compose.yml` (normally `~/.config/luna/windows/compose.yml`), pulls the container image, starts the VM, and waits for the Windows download and unattended setup to finish. Watch progress at `http://127.0.0.1:8006` or with `luna win logs` in another terminal. Installation waits up to two hours by default; `install --timeout SECONDS` changes that limit (1–86400).

Completion requires Dockur's “Windows started successfully” message from the current container boot and an RDP protocol response, rather than just an open Docker port. Only then does Luna record completion in `~/.config/luna/windows/installed`, create `$XDG_DATA_HOME/applications/luna-windows.desktop`, and report success. The `Windows` launcher uses the bundled Windows logo and opens FreeRDP fullscreen without a terminal. The VM stays running, ready for `start`. If setup times out or you interrupt the wait, it stays running, but Luna does not mark it installed or create a new launcher entry. Run `install` again to finish checking setup; existing configuration and disk are preserved. Windows licensing is separate.

The initial username defaults to `luna` and can be set with `install --username NAME`. A random password is generated and saved inside the private Compose file (directory mode 0700, file mode 0600). It is passed to FreeRDP through a private temporary stdin file, never in process arguments. The local browser console controls the VM without requiring an RDP connection; both console and RDP ports bind only to localhost.

The VM disk lives in `$XDG_DATA_HOME/luna/windows/storage` (normally `~/.local/share/luna/windows/storage`). `~/Windows` is mounted as the guest's shared directory. Disk capacity needs room on that filesystem, plus space for the Windows download. The `stop` command never deletes either directory.

Running `install` again preserves the existing Compose file, credentials, and disk, pulls the image, and starts the existing VM. Installation options apply only when creating the configuration. To adjust resources afterward, stop the VM and edit `RAM_SIZE`/`CPU_CORES`/`DISK_SIZE` in Compose. Expanding an existing virtual disk also requires extending its Windows partition; do not shrink it. Username/password environment settings are initial-install settings, so changing an existing Windows password requires updating both Windows and the Compose credentials used by RDP.

## Foreground session

`start` requires a completed installation. It starts the existing container if needed, without pulling or building images, waits up to 120 seconds for the current boot readiness message and an RDP protocol response, then opens FreeRDP and waits for its window to close. `--timeout SECONDS` changes the startup wait (1–3600). First-time Windows installation should finish before starting a desktop session. If the readiness wait times out or is interrupted, the VM stays running so setup can continue. Once RDP is ready, ending or failing the desktop session stops the VM by default; `--keep-alive` leaves it running. Only one Luna RDP session can own the VM at once.

The desktop opens fullscreen with dynamic resolution, clipboard, audio, and microphone forwarding. Display scaling follows the focused Hyprland monitor where supported by FreeRDP. Keyboard grabbing is disabled so compositor shortcuts remain available. GPU passthrough is not configured. Local RDP certificate verification is disabled, matching Omarchy's launcher.

The terminal remains attached by design. For a background session in Bash or Zsh:

```sh
luna win start > ~/luna-windows.log 2>&1 &
disown
```

Closing Windows or interrupting an attached desktop session stops the VM, unless `--keep-alive` was supplied. `logs` follows Docker output independently; closing the log viewer does not stop the VM. `status` reports container state, which does not by itself mean Windows has finished booting.

## Delete the VM

`luna win delete` (also `luna win remove`) asks you to type `delete` before permanently removing the Compose containers, Windows virtual disk and downloaded setup files, private configuration, and launcher entry. `--yes` skips the confirmation for scripts. Your shared `~/Windows` directory and the cached Docker image are kept.

Close the Windows desktop and finish or cancel any installation wait first. If Docker cannot remove the containers, Luna retains the disk and configuration. Automatic deletion refuses custom storage mounts and storage redirected through symlinks. Nothing is deleted from the shared folder. After deletion, `luna win install` offers the resource prompts again.
