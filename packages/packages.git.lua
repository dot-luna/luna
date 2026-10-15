-- Git applications delegate dependency installation and native builds to their
-- own installer. Luna supplies a user prefix and requests non-interactive setup.
-- Each checkout under ~/.local/src/<name> is replaced on every setup run.
return {
    {
        name = "whatly",
        source = "git",
        url = "https://github.com/dot-luna/whatly.git",
        ref = "main",
        script = "scripts/install.sh",
        executable = "whatly",
    },
}
