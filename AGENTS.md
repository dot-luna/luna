# Luna

Look in `.agents/skills/` for project skills and apply those relevant to the task.

Luna is in active development. Do not add backward-compatibility functions,
legacy aliases, fallback code for old APIs or formats, or migration layers unless
explicitly requested. Update affected callers to the current API and remove obsolete
code when changing it.

Prefer GTK/GNOME applications or Luna's own UI. Avoid KDE applications and desktop
components wherever possible; do not introduce new KDE apps. Replace existing KDE
components when a working alternative is available. Luna's own polkit agent lives
in `src/luna-polkit/` and is managed with `luna auth`.

TODO: Review how Luna should handle `~/.config/hypr/hyprqt6engine.conf`.
This Qt theme config remains from the old setup; check whether it is still used
before deciding whether to manage it through Luna or remove it.

Build a modern, responsive UI with subtle, polished animations and useful
interactive feedback. Keep it lightweight; avoid visual clutter and excessive
motion. Use Luna's shared theme for colors, fonts, borders, and rounding.

Keep UI text minimal and focused on the user's task. Omit technical identifiers,
internal names, debug/status metadata, repeated branding, and explanatory filler.
Show only context needed to make a decision, required inputs, actions, and useful
feedback. Put implementation details in documentation or diagnostic logs.

Make interactive UI fully usable with both keyboard and mouse. Provide visible
focus, logical Tab/Shift+Tab navigation, Enter/Space activation, Escape dismissal,
and arrow-key selection where appropriate. Verify these interactions, including
menus, disabled controls, and error/retry states.

Put all tests in `__tests__/`, mirroring the tested source file's
directory. For example, `install.sh` uses `__tests__/test_install.py`, while a
file in `scripts/` uses `__tests__/scripts/`.

Keep user-facing logs concise: useful progress, actionable errors, and next steps.
Omit routine implementation metadata and long explanatory paragraphs.

Internal setup scripts ignore extra arguments and continue past noncritical
failures. Optional steps should warn and skip; essential dependencies and required
file operations must succeed.

Setup does not create automatic backups. Tell users to back up files they want
to keep before installation.
