# Zen setup

Run `bash /path/to/luna/scripts/setup/zen.sh`, or use Luna's normal `apps`
setup step. Back up personal files you want to keep first; setup creates no
automatic backups. Close Zen before setup so Better Find Bar can be installed.
Setup does not launch or restart the browser.

## Theme and fonts

`scripts/generate-theme.lua` resolves Luna's current theme and personal font
choices. Setup writes styles under `$LUNA_CONFIG_DIR/zen/generated` and imports
them from the selected profile's `userChrome.css` and `userContent.css`.
Personal CSS, symlinks, and file permissions are preserved.

The browser UI uses Luna's UI font. A managed block in `user.js` also sets
proportional, serif, and sans-serif defaults to that font, and monospace defaults
to Luna's monospace font. Website font choices remain enabled. These are browser
font preferences, with no font override in website CSS. Gecko's language fallback
lists and special math fonts are kept. Rerun setup to refresh theme/font choices.

Luna's existing square-corner behavior remains conditional: theme rounding `0`
adds `border-radius: 0` to the browser and HTTP(S) page elements; positive rounding
leaves native corner styles alone.

## Extensions

`extensions.json` selects uBlock Origin, Dark Reader, and Bitwarden. Setup merges
their Mozilla Add-ons download URLs into `Extensions.Install` in
`/etc/zen/policies/policies.json`. Zen installs them when it next starts with
network access. No account, Bitwarden sign-in, or extension settings are seeded.

The native policy affects all profiles/users of that Zen installation. Existing
effective policies are preserved; when the system file does not exist, setup
starts from the native installation's distribution policy. Privilege or policy
errors warn and skip extension setup. This policy setup targets native Linux Zen,
not a Flatpak installation selected only through `ZEN_PROFILE_DIR`.
The packaged installation defaults to `/opt/zen-browser-bin`; set
`ZEN_INSTALL_DIR=/absolute/native/installation` for another native installation.
Setup verifies that directory identifies Zen before updating its policy.

Extensions remain removable and can be disabled. Firefox tracks changes to the
installation list, so a removed extension is not forcibly restored on every
launch. Removing a URL from the manifest does not uninstall an existing extension.
See Mozilla's [Extensions policy](https://firefox-admin-docs.mozilla.org/reference/policies/extensions/).

## Better Find Bar

Better Find Bar is the only Mod that Luna adds. Setup downloads its assets from
the official Zen Mod store, merges its entry into `zen-themes.json`, and rebuilds
Zen's Mod stylesheet cache while preserving other enabled Mods. Missing Mod
preference defaults are seeded once in `prefs.js`; existing preferences win and
can still be changed in Zen's Mod settings.

If Better Find Bar is already registered, setup leaves its version, enabled state,
and settings alone. Zen manages subsequent updates. A busy profile, unavailable
download, or invalid existing Mod configuration skips this optional installation
with a warning. Close Zen and rerun setup to retry.

## Profile selection

Setup uses the existing default profile from Zen's registry, preferring an
existing `~/.zen` root over `$XDG_CONFIG_HOME/zen`. It does not create a new profile.
Use `ZEN_PROFILE_DIR=/absolute/profile/path` to select an existing profile when
discovery is ambiguous. Without a profile, generated theme files and native
extension policies can still be installed; open Zen once, close it, and rerun
setup to connect the profile styles, fonts, and Mod.
