# Luna roadmap

Just the way I like it.

An ordered plan for improving this personal desktop, borrowing useful behavior
from Omarchy and design ideas from other desktops. Include improvements to
features Luna already has, not just new applications.

This is a roadmap, not a record of completed work or an instruction to install
every optional application. Work through it one stage at a time.

## Principles

- Keep the default installation lean: one preferred application per everyday
  role, with specialist tools available as optional installs.
- Prefer GTK/GNOME applications or Luna's own UI. Avoid adding KDE components.
  Replace the temporary `polkit-kde-agent` when Luna's own agent is ready.
- Make important, frequent actions work entirely from the keyboard. Keep visible
  focus, discoverable shortcuts, and useful feedback.
- Use modern, subtle animations with a natural spring feel where appropriate.
  Motion should be responsive, interruptible, and respect reduced motion.
- Integrate each feature with the relevant shortcut, menu, CLI, defaults, theme,
  and feedback instead of merely installing its package.
- Adapt ideas to Luna's existing choices, including Kitty, Zsh, Zen, and its own
  shell. Check compatibility before copying upstream configuration.
- Keep setup understandable. Optional features may warn and skip on failure;
  required operations must succeed. Do not create automatic setup backups.

## Current foundation

Luna already has a launcher, shortcut guide, clipboard history, emoji/GIF
pickers, screenshots, silent screen recording, notifications, a calendar with
Nepali date support, media controls, hardware-key bindings and OSDs, Wi-Fi and
Bluetooth controls, power controls, lock/idle handling, Hyprland workflows,
themes/fonts/wallpapers, and Windows/macOS VM commands.

Existing app setup covers Kitty, mpv, Starship, Zsh, Zen, and Hyprland. Other
app directories may only be placeholders. In particular, a `tmux` directory
does not mean tmux is installed or configured, and packaging T3 Code or Zed does
not mean their Luna configuration is finished.

The twelve Settings pages and many launcher installation/removal actions are
still placeholders. Theme generation exists, but coordinated live updates across
all consumers and wallpaper application still need work.

## Build order

Labels describe the starting point: **Improve** means a feature already exists,
**Finish** means scaffolding exists, and **Add** means new work. Unchecked items
represent proposed work, including improvements to existing features.

### 1. Everyday applications and defaults — Add

- [ ] Choose default image, PDF, archive, text, and calculator applications.
- [ ] Add their packages and file associations, keeping Kitty, Zen, Nautilus,
  Zed, and mpv for their existing roles.
- [ ] Make default selection consistent across file opening, launchers, and
  shortcuts.
- [ ] Cover the intended image and document MIME types. The current defaults
  installer only expands audio/video wildcards; image associations need explicit
  types or deliberate support in the installer.

### 2. File management — Improve

- [ ] Improve Nautilus and Yazi keyboard navigation, hidden-file handling,
  thumbnails, and previews.
- [ ] Add Space-to-preview through Sushi and useful thumbnail support.
- [ ] Open the file manager or terminal in the relevant current directory.
- [ ] Support removable drives, phones, and network shares through appropriate
  GVFS and mounting helpers.
- [ ] Add convenient sharing and disk-usage inspection.

### 3. Hyprland workflow — Improve

- [ ] Revisit focus, move, resize, groups, scratchpads, dropdown terminals, pinning,
  fullscreen, monitor movement, and workspace movement.
- [ ] Improve useful window sizing behavior, including reusable window widths.
- [ ] Keep shortcuts documented and discoverable in the shortcut guide.
- [ ] Check that frequent flows work predictably across tiling and floating
  windows, multiple monitors, and keyboard-only use.

### 4. Kitty, Zsh, and Starship — Improve

- [ ] Refine coordinated themes, fonts, tabs, splits, and opening a terminal in
  the active terminal's directory.
- [ ] Improve history, completion, previews, and SSH ergonomics where useful.
- [ ] Keep the prompt readable and responsive without unnecessary decoration.

### 5. Tmux and development workspaces — Add / Finish

- [ ] Install and configure tmux with persistent sessions, pane/session navigation,
  copy mode, and discoverable help.
- [ ] Add reusable editor, terminal, and agent layouts where they save effort.
- [ ] Finish useful Zed, Git, GitHub CLI, and T3 Code configuration.
- [ ] Treat placeholder app folders as unfinished until their actual setup exists.

### 6. Luna visual language — Improve

- [ ] Establish shared spacing, typography, icon sizes, focus and selection
  states, menus, and dialogs.
- [ ] Make loading, empty, success, and error states useful and consistent.
- [ ] Refine restrained spring motion, interruption behavior, and reduced motion.

### 7. Themes, fonts, and wallpapers — Improve

- [ ] Coordinate live updates across Luna, terminal/editor palettes, GTK, and
  wallpaper consumers.
- [ ] Add useful previews, personal overrides, and per-monitor wallpaper choices.
- [ ] Consider optional wallpaper-derived colors after the basic theme pipeline
  is reliable.

### 8. Real Settings — Finish

- [ ] Replace the twelve placeholder pages with working controls.
- [ ] Add searchable settings, persistence, and consistent behavior between the
  CLI and UI.
- [ ] Explain or hide unsupported hardware controls appropriately.
- [ ] Revert display changes automatically unless the user confirms they work.

### 9. Launcher and command menu — Improve

- [ ] Search apps, settings, actions, files, and shortcuts with useful synonyms.
- [ ] Add favorites, recent items, and launch-or-focus behavior where appropriate.
- [ ] Make keyboard selection and navigation consistent.
- [ ] Replace placeholder menu actions as their underlying features become ready.

### 10. Bar and panels — Improve

- [ ] Support useful widget ordering and visibility, tray management, and panel
  shortcuts.
- [ ] Show active modes clearly, such as recording, muted input, or stay-awake.
- [ ] Consider optional panel positions, weather, and a dock later.

### 11. Sound and media — Improve

- [ ] Add a per-application mixer and convenient output/input switching.
- [ ] Refine microphone control, fine volume increments, media-source selection,
  and OSD feedback.
- [ ] Handle Bluetooth audio device loss and reconnection predictably.

### 12. Displays and hardware keys — Improve

- [ ] Add external-monitor brightness through DDC where supported and keyboard
  backlight control where available.
- [ ] Support fine brightness increments, mirror/extend actions, laptop-display
  and lid behavior, scaling, and zoom.
- [ ] Improve relevant touchpad and touchscreen controls.
- [ ] Retain and verify the existing volume, brightness, and media-key bindings
  across supported hardware.

### 13. Power and idle — Improve

- [ ] Support separate AC and battery preferences, low-battery behavior, and
  useful idle timing controls.
- [ ] Improve presentation/stay-awake controls and add night light.
- [ ] Verify suspend/resume behavior; offer hibernation setup only where supported.

### 14. Networking and sharing — Improve / Add

- [ ] Polish Wi-Fi and Bluetooth connection flows and device feedback.
- [ ] Add Wi-Fi QR sharing, captive-portal handling, and useful connection details.
- [ ] Add LocalSend and a convenient file-manager sharing action.
- [ ] Offer Tailscale and Taildrop as optional integrations.

### 15. Authentication and locking — Improve / Add

- [ ] Build Luna's own polkit UI and replace the temporary KDE agent once the
  replacement works reliably.
- [ ] Refine the lock screen's appearance, feedback, and keyboard interaction.
- [ ] Keep GNOME Keyring integration and consider optional fingerprint/security-key
  support with clear limits for each authentication flow.

### 16. Screenshots and screen tools — Improve / Add

- [ ] Add annotation, cropping, arrows, labels, and redaction.
- [ ] Consider scrolling capture, keyboard-driven capture, and reuse of the last
  capture region.
- [ ] Add OCR, QR reading, and a color picker.

### 17. Recording and media processing — Improve / Add

- [ ] Extend recording beyond silent video with system audio and microphone
  capture, plus optional webcam capture.
- [ ] Use hardware encoding where supported and expose useful quality choices.
- [ ] Add trimming, conversion, compression, and GIF creation where useful.
- [ ] Preserve reliable stop/save behavior and clear recording feedback.

### 18. Clipboard, snippets, and dictation — Improve / Add

- [ ] Refine text/image history, previews, paste-back, and plain-text paste.
- [ ] Add reusable snippets and consider universal clipboard integration.
- [ ] Handle sensitive clipboard content deliberately.
- [ ] Offer speech-to-text as an optional feature, with a clear choice of local
  or remote processing.

### 19. Notifications, calendar, and reminders — Improve / Add

- [ ] Improve keyboard notification actions, per-app preferences, and history.
- [ ] Add timers and reminders and refine world clocks.
- [ ] Preserve Luna's Nepali calendar support.

### 20. Browser and web apps — Improve / Add

- [ ] Refine Zen styling, defaults, profiles, and useful extensions.
- [ ] Add website launchers with icons, sensible focus behavior, and optional work
  profiles.
- [ ] Adapt Chromium-specific upstream features for Zen where possible; do not
  assume their extensions or browser integration work unchanged.

### 21. Application catalog — Add

- [ ] Provide optional installs with clear progress, actionable errors, presets,
  and launchers for terminal applications.
- [ ] Expose appropriate default-app selection.
- [ ] Limit removal to the selected managed application; do not remove unrelated
  software installed outside Luna.

### 22. Updates, diagnostics, and recovery — Add

- [ ] Add an update command, migrations, and a useful update indicator.
- [ ] Provide readable diagnostics and targeted component restarts.
- [ ] Design explicit recovery options separately from installation.
- [ ] Keep automatic backups out of setup and tell users to back up files they
  want to preserve before installation.

### 23. Productivity and creative applications — Add

- [ ] Add selected applications from the catalog below as optional choices.
- [ ] Integrate their defaults, themes, and useful keyboard entry points.

### 24. Developer and AI extras — Add

- [ ] Offer optional language/database environments, Git worktree helpers, SSH
  tunnels, and project launchers.
- [ ] Integrate chosen coding agents and optional local models.
- [ ] Consider a usage panel separately, after the underlying integrations work.

### 25. Gaming, remote access, and VMs — Improve / Add

- [ ] Polish the existing Windows/macOS VM flows.
- [ ] Offer optional gaming tools, controller support, and game streaming.
- [ ] Add useful remote-connection profiles and launchers.

### 26. Personal extensions and distribution packaging — Later

- [ ] Consider simple personal actions and widgets before a larger plugin system.
- [ ] Explore an optional overview or dock; verify what is feasible with Hyprland
  before promising another compositor's behavior.
- [ ] Consider first-login polish and a reproducible image/ISO if useful for
  personal reinstalls.

## Application candidates

These are Luna choices to evaluate, not a claim that Omarchy ships every listed
application. Alternative and specialist apps are optional, not a bulk-install
list.

| Role | Preferred direction | Optional additions or upstream ideas |
| --- | --- | --- |
| Images | Loupe | imv for a minimal keyboard-driven viewer |
| PDF reading | Papers | Keep one default reader |
| PDF editing | PDF Arranger | Study Signed for signature/text placement |
| Archives | File Roller | Integrate archive actions with the file manager |
| Files | Keep Nautilus and Yazi | Sushi, GVFS, thumbnails, removable-drive handling |
| Storage | GNOME Disks | Baobab or Disktree for disk usage |
| Calculator and time | GNOME Calculator; keep Luna's calendar | GNOME Clocks; study Omacalc |
| Terminal and shell | Keep Kitty, Zsh, Starship, fzf, zoxide, bat, eza, fd, and ripgrep | tmux, tldr, btop |
| Coding and Git | Keep Zed, Git, GitHub CLI, and T3 Code | Lazygit; optional Neovim or Helix |
| Office | LibreOffice | Install when needed |
| Notes | Optional Obsidian | Keep personal note workflows optional |
| Writing | Apostrophe or Omawrite | Keep Zed for ordinary text and code |
| Presentations | LibreOffice Impress | Study Hype |
| Image editing | Pinta | Keep advanced creative tools optional |
| Screenshots | Keep Luna's capture flow | Evaluate Omasnap, Tesseract, zbar, and hyprpicker |
| Recording | Improve Luna's recorder | Evaluate gpu-screen-recorder, Omacut, and Monologue; OBS for advanced work |
| Media processing | Optional FFmpeg and ImageMagick helpers | libvips, yt-dlp |
| Music | Keep mpv and Luna media controls | Spotify or Cliamp; investigate mpv-mpris |
| Sharing | LocalSend | Nautilus sharing action |
| Synchronization | Optional Syncthing | Dropbox if needed |
| Passwords | Keep GNOME Keyring, Seahorse, and the Bitwarden browser extension | Bitwarden desktop/CLI or Secrets for local KeePass databases |
| Messaging | Keep Whatly/WhatsApp | Signal, Discord, or Slack for services actually used |
| Remote access | Keep existing VM clients | Remmina, Tailscale, Moonlight, Sunshine |
| Printing | CUPS and a suitable printer UI when needed | Avoid adding unused printing services by default |
| Local AI | T3 Code and the chosen coding agent | Ollama or LM Studio |
| Gaming | Optional Steam/Proton | Heroic, Lutris, RetroArch, Minecraft, controllers, streaming |

An optional web-app catalog can include mail, calendar, YouTube, Discord, Google
services, Teams, and Outlook. These are website launchers, not native Linux
releases of those services.

Omarchy's small applications worth studying include Omasnap, Omacalc, Omawrite,
Signed, Hype, Omacut, and Monologue. Qt does not imply KDE: using or learning from
an independent Qt application does not require adopting KDE desktop components.

## Design references

| Reference | Ideas to adapt |
| --- | --- |
| [Omarchy](https://omarchy.org/manual/) | Integration across shortcuts, menus, CLI actions, defaults, themes, and feedback |
| [GNOME keyboard guidance](https://developer.gnome.org/hig/guidelines/keyboard.html) | Consistent keyboard conventions, visible focus, and usable dialogs |
| [GNOME search guidance](https://developer.gnome.org/hig/patterns/nav/search.html) | Immediate, tolerant search with understandable results |
| [libadwaita spring animation](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.SpringAnimation.html) | Natural motion and respect for reduced motion |
| [elementary configuration guidance](https://docs.elementary.io/hig/design-philosophy/accessible-configuration) | Contextual controls, restraint, and approachable settings |
| [COSMIC](https://system76.com/cosmic) | Configurable panels, themes, and workspace workflows |
| [niri overview](https://niri-wm.github.io/niri/Overview.html) | Spatial workspace navigation and overview ideas, subject to Hyprland feasibility |
| [Noctalia control center](https://docs.noctalia.dev/noctalia/control-center/) | Cohesive panel layout and concise system controls |

Use these as references for Luna's own design. Current Noctalia and its older
Quickshell version have different implementations; check the version before
borrowing implementation details.

## Omarchy source references

The research used the current [Omarchy repository](https://github.com/omacom/omarchy)
and [manual](https://omarchy.org/manual/). The links below use its `quattro` branch;
recheck relevant upstream behavior when implementing a stage.

- [Keyboard shortcuts](https://github.com/omacom/omarchy/blob/quattro/manual/07-hotkeys.md),
  [top bar](https://github.com/omacom/omarchy/blob/quattro/manual/05-the-top-bar.md),
  [themes](https://github.com/omacom/omarchy/blob/quattro/manual/06-themes.md).
- [Terminal](https://github.com/omacom/omarchy/blob/quattro/manual/15-terminal.md),
  [shell tools](https://github.com/omacom/omarchy/blob/quattro/manual/19-shell-tools.md),
  [shell functions](https://github.com/omacom/omarchy/blob/quattro/manual/20-shell-functions.md),
  [TUIs](https://github.com/omacom/omarchy/blob/quattro/manual/21-tuis.md).
- [GUI applications](https://github.com/omacom/omarchy/blob/quattro/manual/22-guis.md),
  [browsers](https://github.com/omacom/omarchy/blob/quattro/manual/23-browsers.md),
  [commercial apps and services](https://github.com/omacom/omarchy/blob/quattro/manual/24-commercial-apps-services.md),
  [web apps](https://github.com/omacom/omarchy/blob/quattro/manual/25-web-apps.md),
  [PDF editing](https://github.com/omacom/omarchy/blob/quattro/manual/27-filling-out-pdfs.md).
- [Clipboard](https://github.com/omacom/omarchy/blob/quattro/manual/08-unified-clipboard-history.md),
  [reminders](https://github.com/omacom/omarchy/blob/quattro/manual/09-reminders.md),
  [OCR and dictation](https://github.com/omacom/omarchy/blob/quattro/manual/11-text-extraction-dictation.md),
  [screenshots and recording](https://github.com/omacom/omarchy/blob/quattro/manual/12-screenshots-recording.md).
- [Idle and screensaver toggles](https://github.com/omacom/omarchy/blob/quattro/manual/13-toggles-idle-screensaver.md),
  [monitors](https://github.com/omacom/omarchy/blob/quattro/manual/33-monitors.md),
  [networking](https://github.com/omacom/omarchy/blob/quattro/manual/35-networking.md),
  [sleep](https://github.com/omacom/omarchy/blob/quattro/manual/36-system-sleep.md),
  [hardware authentication](https://github.com/omacom/omarchy/blob/quattro/manual/37-hardware-authentication.md).
- [Development tools](https://github.com/omacom/omarchy/blob/quattro/manual/18-development-tools.md),
  [AI](https://github.com/omacom/omarchy/blob/quattro/manual/17-ai.md),
  [gaming](https://github.com/omacom/omarchy/blob/quattro/manual/26-gaming.md),
  [shell plugins](https://github.com/omacom/omarchy/blob/quattro/manual/32-shell-plugins.md).
- [Updates](https://github.com/omacom/omarchy/blob/quattro/manual/30-updates.md),
  [common tweaks](https://github.com/omacom/omarchy/blob/quattro/manual/42-common-tweaks.md),
  [troubleshooting](https://github.com/omacom/omarchy/blob/quattro/manual/45-troubleshooting.md),
  [snapshots](https://github.com/omacom/omarchy/blob/quattro/manual/47-system-snapshots.md).
- [Base package list](https://github.com/omacom/omarchy/blob/quattro/install/omarchy-base.packages).

## Starting point

Start with **stage 1: everyday applications and defaults**, followed by
**stage 2: file management**. Keep the remaining stages available for selection
and adjust their order when a concrete dependency or personal priority warrants it.
