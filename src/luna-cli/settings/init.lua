-- Launch the standalone settings preview without changing desktop configuration.
return function(common, directory)
    local M = {}

    function M.register(parser)
        return parser:command("settings", "Open the Luna Settings mockup.")
    end

    function M.run()
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY"), "Luna Settings requires a Wayland session")
        common.run({ "qs", "-p", directory .. "/../../settings", "--daemonize", "--no-duplicate" })
    end

    return M
end
