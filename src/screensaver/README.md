# Luna Screensaver

A screensaver controller with a replaceable QML rendering shell. Luna handles idle
timers, Stay awake, input dismissal, display sleep, and the separate lock handoff.
The bundled shell shows a themed clock; custom shells supply their own visuals.

Use `luna screensaver install PATH`, `list`, `set NAME`, and `remove NAME` to manage
shells; run `luna screensaver` to show the selection. See [DOCS.md](DOCS.md) for the
CLI, Lua/QML APIs, and custom shells, or [config.toml](config.toml) for options.
