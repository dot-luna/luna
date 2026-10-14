-- Start the packaged authentication agent inside the current desktop session.
return function(common, directory)
    local M = {}

    function M.register(parser)
        local command = parser:command("auth", "Manage desktop administrator password prompts.")
        command:argument("auth_action"):args("?"):default("start"):choices({ "start", "status" })
        return command
    end

    function M.run(options)
        local unit = "plasma-polkit-agent.service"
        if options.auth_action == "status" then
            common.info(common.succeeds({ "systemctl", "--user", "is-active", "--quiet", unit }) and "running" or "stopped")
            return
        end
        assert(os.getenv("WAYLAND_DISPLAY"), "Authentication prompts require a Wayland session")
        local environment = { "systemctl", "--user", "import-environment" }
        for _, name in ipairs({ "WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE" }) do
            if os.getenv(name) then
                table.insert(environment, name)
            end
        end
        common.run(environment)
        common.run({ "systemctl", "--user", "start", unit })
    end

    return M
end
