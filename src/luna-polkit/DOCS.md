# Luna authentication agent

Luna presents desktop authorization requests through Quickshell's native
`Quickshell.Services.Polkit` module, available in Quickshell 0.3.2. It runs
separately from the bar and launcher so reloading those interfaces does not
interrupt administrator prompts. Polkit decides which identity and authentication
method a protected action requires; Luna does not change polkit policy or the
system's PAM configuration.

## Commands

Run these from your desktop session:

| Command | Behavior |
| --- | --- |
| `luna auth start` | Validate the shell and start its user service; repeated starts preserve a healthy agent. |
| `luna auth status` | Print `running` when the native agent reports registration, `unavailable` while it cannot register, or `stopped`. |
| `luna auth restart` | Validate, then restart the authentication service. |
| `luna auth stop` | Stop the service and any instances of this checkout's authentication shell. |
| `luna auth serve` | Run the themed shell in the foreground; used by the service. |

## How applications use it

Applications do not need a Luna-specific integration. At startup, Luna registers
as the authentication agent for the desktop session. A privileged system service
checks its caller's requested action with polkit; when policy requires
authentication and interaction is allowed, polkit contacts the registered agent
over D-Bus. Luna shows the prompt, and the service performs the action only after
authorization succeeds. The application does not receive the password. See the
[polkit architecture](https://polkit.pages.freedesktop.org/polkit/polkit.8.html)
and [agent registration](https://polkit.pages.freedesktop.org/polkit/polkit-agents.html).

Existing applications using polkit work with Luna automatically once it is
registered. Applications that use another authorization mechanism do not switch
to polkit just because Luna is running.

For a new application, use the relevant system service's API for the operation.
If it needs its own privileged service, that service must check the caller through
polkit and define the supported actions. A small privileged command-line helper
can instead be invoked through `pkexec`; it uses the session's registered agent.
For example, this requests authorization for a command that makes no changes:

```sh
pkexec --disable-internal-agent /usr/bin/true
```

The option disables pkexec's terminal-agent fallback, so a missing desktop agent
is reported instead. Policy or cached authorization can allow the command without
a prompt. See the [pkexec manual](https://polkit.pages.freedesktop.org/polkit/pkexec.1.html).

### Sudo

Ordinary `sudo` uses its own authorization policy and normally asks for the
password in the terminal. It does not use this polkit agent. `sudo -A` uses a
separate askpass helper; Luna's polkit agent does not implement that interface.
See the [sudo manual](https://github.com/sudo-project/sudo/blob/main/docs/sudo.man.in).

## Service and KDE replacement

Hyprland runs `luna auth start` at login. The command writes
`$XDG_CONFIG_HOME/systemd/user/luna-polkit.service` (defaulting to
`~/.config/systemd/user/`) and imports the current desktop session environment,
including `XDG_SESSION_ID` when present. The service restarts after crashes and
stops with the graphical session. Luna manages one active desktop session per user.

Startup first loads the actual shell with agent registration disabled. A missing
polkit module, invalid theme, or broken QML leaves the current agent untouched.
After validation, Luna stops and runtime-masks an installed
`plasma-polkit-agent.service`, then confirms its own polkit registration. If takeover
fails, it attempts to restore the previous unit file and agent state, reporting any
recovery failures. The runtime mask expires on reboot; Luna applies it again at
login. `stop` keeps the mask in place so an explicit stop does not unexpectedly
start a different agent.

`polkit-kde-agent` is no longer a Luna dependency. Updating Luna does not uninstall
an existing package. After verifying Luna authentication, it can be removed with
`sudo pacman -R polkit-kde-agent`. Manually launched agents outside the KDE user
service must be stopped separately if they already own the session registration.

## Dialog and keyboard controls

The dialog reads colors, fonts, borders, and rounding from the shared `Luna.Theme`
snapshot. It opens on the focused monitor and stays there until the request
finishes. It scrolls on short displays and keeps keyboard-focused controls visible.
The prompt shows the requested action, account, response field, and buttons.
Technical action IDs and branding subtitles are omitted.

| Key | Action |
| --- | --- |
| Enter | Submit the current response or activate the focused button. |
| Space | Activate the focused button or open the account selector. |
| Escape | Cancel the request; an open account menu closes first. |
| Tab / Shift+Tab | Move between the account selector, input, and buttons. |
| Arrow keys | Select an account when the selector is focused and the policy permits multiple identities. |
| Enter / Alt+Down on the account selector | Open the account menu; Enter confirms the highlighted account. |

The response field, account menu, and both buttons also support the mouse.
Changing accounts clears the response and returns focus to the input.

The dialog uses the message and permitted accounts supplied by polkit, and the
input prompt supplied by the system authentication conversation. Secret responses
are masked immediately. Multi-step challenges, visible responses, retry messages,
and cancellation use the same conversation.

## Response handling

Responses are submitted directly to the native `AuthFlow` object. Luna never
writes them to files or logs, or passes them through shell commands, command
arguments, environment variables, or CLI IPC.

The input and its undo/redo history are cleared on submission, cancellation,
completion, account changes, replacement requests, and between authentication
steps. This prevents a later visible challenge from restoring a prior password.
Like other graphical password prompts, the typed response exists temporarily in
process memory; clearing the field does not guarantee that all copies in Qt or
JavaScript memory have been overwritten.

## Verify in a desktop session

1. Run `luna auth start`, then `luna auth status`; expect `running`.
2. Run `pkexec /usr/bin/true`. Check the requested action and account, cancel with
   Escape, and confirm the command fails without running the privileged action.
3. Run it again, try an incorrect password, then authenticate correctly. Verify
   the prompt reports the failure, clears the response, and closes on success.
4. Confirm Tab, Shift+Tab, Enter, Escape, and identity selection work; check that
   ordinary password prompts conceal input and a visible PAM challenge stays visible.
5. Run `luna auth start` twice and confirm there is still one authentication shell
   in `qs list -a`; exercise `restart`, `stop`, and `start` as well.

Polkit can cache authorization according to the action's policy. If no prompt
appears, use `pkcheck --revoke-temp` before retrying. Cancellation and denial must
leave the protected operation unauthorized. For registration failures, inspect
`journalctl --user -u luna-polkit.service` and check for another authentication agent.

## Source and checks

- [`src/shell/shell.qml`](src/shell/shell.qml) owns registration, a bounded
  registration deadline, and lifecycle IPC. The IPC interface exposes only
  readiness and shutdown.
- [`src/shell/AuthDialog.qml`](src/shell/AuthDialog.qml) owns the Wayland overlay
  and exclusive keyboard focus.
- [`src/shell/AuthContent.qml`](src/shell/AuthContent.qml) handles account
  selection, input, and authentication feedback.
- [`../luna-cli/auth/`](../luna-cli/auth/) owns startup, shutdown, and user service
  integration.
- [`../../__tests__/src/luna-polkit/src/shell/`](../../__tests__/src/luna-polkit/src/shell/)
  exercises the UI with fake conversations and the native backend against an
  isolated D-Bus authority.
- [`../../__tests__/src/luna-cli/auth/`](../../__tests__/src/luna-cli/auth/)
  covers the lifecycle with mocked system commands.

`LUNA_POLKIT_VALIDATE=1` loads the real shell and dialog without registering an
agent, then exits. Lifecycle startup uses this check before handing over the
session's authentication prompts. It needs a working Wayland display.

Run the targeted checks from the repository root; they do not authenticate against
the host:

```sh
python -m unittest discover -s __tests__/src/luna-cli/auth -v
python -m unittest discover -s __tests__/src/luna-polkit/src/shell -v
```

The backend API is documented by
[Quickshell](https://quickshell.org/docs/v0.3.0/types/Quickshell.Services.Polkit/).
