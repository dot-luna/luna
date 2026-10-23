-- User development tools installed after the core packages provide mise.
-- Version requests become global defaults; projects can override them locally.
return {
    {
        name = "node",
        source = "mise",
        version = "lts",
        purpose = "Node.js runtime using the current long-term support release",
    },
    {
        name = "bun",
        source = "mise",
        version = "latest",
        purpose = "Bun JavaScript runtime and tooling",
    },
    {
        name = "pnpm",
        source = "mise",
        version = "latest",
        purpose = "pnpm JavaScript package manager",
    },
    {
        name = "python",
        source = "mise",
        version = "latest",
        purpose = "Python runtime for development",
    },
    {
        name = "uv",
        source = "mise",
        version = "latest",
        purpose = "uv Python package and project manager",
    },
}
