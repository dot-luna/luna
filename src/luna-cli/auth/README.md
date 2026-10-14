# Authentication prompts

`luna auth start` imports the current Wayland session environment and starts the
packaged KDE PolicyKit agent. Repeated starts keep the same service. `luna auth status`
reports whether it is running.

Hyprland starts it at login. The `polkit-kde-agent` package provides
`plasma-polkit-agent.service`; administrator authentication stays inside its password
dialog. Luna never reads or stores the password.
