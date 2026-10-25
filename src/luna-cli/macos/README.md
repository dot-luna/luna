# macOS VM

Luna uses [Dockur macOS](https://github.com/dockur/macos) with Docker Compose
and a foreground TigerVNC console. This follows the Windows command's resource
prompts, persistent storage, launcher, and session lifecycle.

```sh
luna macos install                     # interactively choose RAM, cores, disk, and version
luna mac install --yes                 # 4G RAM, 2 CPUs, 64G disk, macOS 15
luna mac install --ram 8G --cpus 4 --disk 128G --version 15
luna mac start --keep-alive             # finish installation without stopping when the viewer closes
luna mac start                          # normal session; stop VM when the viewer closes
luna mac stop
luna mac status
luna mac logs                           # follow; Ctrl+C ends only log viewing
luna mac logs --no-follow --tail 200
luna mac delete                         # confirm permanent deletion; retain shared files
```

`macos` and `mac` are interchangeable. Bare `luna mac` displays help.
Back up any files you want to keep before installation or VM changes; Luna does
not create automatic backups.

## Interactive resources

New installations prompt in this order: RAM, CPU cores, disk capacity, and macOS
version. Enter accepts the displayed default. Invalid answers are requested
again; RAM/disk answers accept `8`, `8G`, or `8g` as GiB. Explicit flags skip only
their corresponding prompts. `--yes` and non-interactive invocations use defaults
for missing values. Retrying installation preserves the existing configuration
and disk without asking resource questions again.

RAM must be at least 4G and disk capacity at least 64G. CPU choices are
1, 2, 4, 6, 8, 10, 12, 14, 16, 24, 32, or 64, matching Dockur topologies without
silently reducing the requested count. macOS versions 11–15 and 26 are selectable;
15 (Sequoia) is the default. Upstream currently describes 26 as experimental and
slow. On AMD, keep RAM at 8G or less during the initial installation.

## Prerequisites and installation

Use an x86-64 Linux host with AVX2, KVM, `/dev/net/tun`, and enough free memory and
disk space for the chosen resources and recovery download. Docker and Compose
must already be available to the invoking user (`docker info`). TigerVNC's
`vncviewer` and an X11/XWayland display are needed for `start`; Luna's package
manifest includes TigerVNC. This command does not install packages, enable Docker,
or change groups. See upstream's [requirements and hardware usage notice](https://github.com/dockur/macos#requirements-%EF%B8%8F).

`install` creates the private Compose configuration, pulls `dockurr/macos:latest`,
and starts the container. An installation lock prevents deletion during image
pulling, container startup, and final setup writes. It waits for a real VNC protocol
greeting before recording `prepared` and creating the **macOS** launcher entry.
This means the console is usable; it does **not** mean macOS has finished installing.
`install --timeout SECONDS` changes the default two-hour console wait (1–86400).
If the wait fails or is interrupted, the VM stays running and a retry preserves
its disk. No new preparation marker or launcher is created before console readiness.

Complete the [upstream installation steps](https://github.com/dockur/macos#how-do-i-use-it)
in the browser at `http://127.0.0.1:8007`, or run `luna mac start --keep-alive`:

1. Wait for recovery to load and open Disk Utility.
2. Erase the largest virtual **Apple Inc. VirtIO Block Media** disk as APFS.
3. Close Disk Utility, choose Reinstall macOS, and select that virtual disk.
4. Allow installation and reboots to finish, then complete Setup Assistant and
   create your macOS account inside the guest.

Luna does not configure a guest username/password or enable Dockur's experimental
unattended account setup. Credentials are entered inside the macOS console.

## Files and connections

- Config: `$XDG_CONFIG_HOME/luna/macos/compose.yml`, normally
  `~/.config/luna/macos/compose.yml` (directory 0700, file 0600).
- Virtual disk and recovery files: `$XDG_DATA_HOME/luna/macos/storage`, normally
  `~/.local/share/luna/macos/storage`.
- Shared host directory: `~/macOS`, mounted at `/shared`. In the guest, run
  `sudo mount_9p shared` and open **Go → Computer** in Finder.
- Browser console: `127.0.0.1:8007`; native VNC: `127.0.0.1:5900`. Both bind only
  to localhost. Windows keeps its separate project, storage, and ports.

Stop the VM before editing resource values in Compose. The CLI's install flags
apply only to new configurations. Expanding an existing virtual disk also needs
guest partition/container expansion; do not shrink an existing disk. Changing
`VERSION` is not a guest OS upgrade procedure.

## Session and shutdown

`start` uses the existing image without pulling or building, waits for the VNC
console, and opens TigerVNC fullscreen. The terminal remains attached until that
viewer exits. Only one Luna console session owns cleanup at a time. Clipboard
forwarding is requested from the server; guest support determines availability.
Audio, GPU passthrough, and automatic guest display resizing are not configured.

Closing or interrupting the viewer stops the VM unless `--keep-alive` was given.
A startup timeout leaves it running so recovery/downloads can continue.
`start --timeout SECONDS` changes the default 120-second wait (1–3600).
Closing the browser console alone does not stop the VM; use `luna mac stop`.

Both macOS and Windows stop commands disable the container's automatic restart,
request shutdown with a 120-second grace period, and verify it is no longer
running or restarting. After a successful stop, the guest has no running QEMU
process and consumes no guest CPU or allocated VM RAM. Disk images and container
images remain on storage. Other Docker containers and the shared Docker service
are not stopped. `--keep-alive` deliberately keeps the guest's resources allocated.

`delete`/`remove` requires typing `delete`, or explicit `--yes`. It removes the
Compose containers, virtual disk/recovery files, private configuration, and
launcher only after verifying container removal. Shared `~/macOS` files and the
cached Docker image are retained. Active sessions/installations, custom storage
mounts, and symlinked storage are refused to protect unrelated files.
