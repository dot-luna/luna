-- Command-line adapter for the shared screensaver API. Parsing and output belong
-- here; idle timers, session state, config persistence, and rendering do not.
return function(common, directory)
    local root = directory .. "/../../.."
    local screensaver = dofile(root .. "/lib/luna.lua")(root, common).screensaver
    local json = dofile(root .. "/lib/json.lua")
    local M = {}

    function M.register(parser)
        local command = parser:command("screensaver", "Manage the screensaver shell and idle controller.")
        command:require_command(false)
        local install = command:command("install", "Copy a local QML shell or package into the library.")
            :target("screensaver_install")
        install:argument("screensaver_source", "QML file or directory containing shell.qml")
        install:option("--name", "Installed name (defaults to the source name)"):target("screensaver_name")
        install:flag("--force", "Replace an inactive installed shell"):target("screensaver_force")
        command:command("list", "List installed and bundled shells; mark the current selection.")
            :target("screensaver_list")
        command:command("set", "Select a shell by name or QML path and apply it.")
            :target("screensaver_set"):argument("screensaver_target")
        local remove = command:command("remove", "Preview and remove installed shells.")
            :target("screensaver_remove")
        remove:argument("screensaver_names", "Installed shell names"):args("+")
        remove:flag("-y --yes", "Remove without asking for confirmation"):target("screensaver_yes")
        command:command("dir", "Print the screensaver library directory."):target("screensaver_dir")
        local get = command:command("get-config getConfig", "Print resolved config or one dotted key."):target("get_config")
        get:argument("config_key", "Optional dotted key, such as idle.lock_seconds"):args("?")
        local update = command:command("update-config updateConfig", "Deep-merge a JSON object into the config."):target("update_config")
        update:argument("config_changes", "Partial config as a JSON object")
        command:command("get-config-file getConfigFile", "Print the absolute config file path."):target("get_config_file")
        command:command("status", "Print the screensaver controller state.")
        command:command("state", "Print screensaver and Stay awake state as JSON.")
        command:command("start", "Start idle monitoring without showing the screensaver.")
        command:command("stop", "Stop idle monitoring and close the screensaver.")
        command:command("restart", "Restart idle monitoring and reset session Stay awake state.")
        command:command("reload", "Apply saved config and theme while preserving Stay awake.")
        command:command("show", "Show the screensaver, starting idle monitoring if needed.")
        command:command("hide", "Dismiss the screensaver without stopping idle monitoring.")

        local idle = parser:command("idle", "Configure automatic screensaver, locking, and display power.")
        idle:argument("idle_action"):args("?"):default("status"):choices({ "status", "set" })
        idle:argument("idle_setting"):args("?"):choices({ "screensaver", "lock", "display" })
        idle:argument("seconds"):args("?")
        parser:command("awake", "Temporarily pause automatic idle actions.")
            :argument("awake_action"):args("?"):default("status")
            :choices({ "status", "toggle", "on", "off" })
        return command
    end

    function M.run(options)
        if options.awake then
            local action = options.awake_action or "status"
            local state
            if action == "status" then
                state = screensaver.getState()
            elseif action == "toggle" then
                state = screensaver.toggleStayAwake()
            else
                state = screensaver.setStayAwake(action == "on")
            end
            common.info(json.encode({ enabled = state.stayAwake }))
        elseif options.idle then
            if options.idle_action == "set" then
                local key = ({ screensaver = "screensaver_seconds", lock = "lock_seconds",
                    display = "display_off_seconds" })[options.idle_setting]
                assert(key, "Choose an idle setting: screensaver, lock, or display")
                local seconds = tonumber(options.seconds)
                assert(seconds and seconds % 1 == 0 and seconds >= 0 and seconds <= 86400,
                    "Idle timeouts must be whole seconds from 0 to 86400")
                screensaver.updateConfig({ idle = { [key] = seconds } })
                local ok, message = pcall(screensaver.reload)
                assert(ok, "Idle settings saved, but could not apply them: " .. tostring(message))
            end
            common.info(screensaver.getConfig("idle", "json"))
        elseif options.screensaver_install then
            local entry = screensaver.install(options.screensaver_source, {
                name = options.screensaver_name,
                force = options.screensaver_force == true,
            })
            common.info("Screensaver installed: " .. entry.name)
        elseif options.screensaver_list then
            for _, entry in ipairs(screensaver.list()) do
                common.info((entry.current and "* " or "  ") .. entry.name
                    .. (entry.bundled and " (bundled)" or ""))
            end
        elseif options.screensaver_set then
            local entry = screensaver.set(options.screensaver_target)
            common.info("Screensaver set: " .. entry.name)
        elseif options.screensaver_remove then
            local entries = screensaver.removalPlan(options.screensaver_names)
            if not options.screensaver_yes then
                common.info("Remove these installed screensavers?")
                for _, entry in ipairs(entries) do
                    common.info("  " .. entry.name)
                end
                io.stdout:write("Continue? [y/N] ")
                io.stdout:flush()
                local answer = io.read("*l")
                if not answer or (answer:lower() ~= "y" and answer:lower() ~= "yes") then
                    common.info("Removal cancelled.")
                    return
                end
            end
            for _, name in ipairs(screensaver.remove(options.screensaver_names)) do
                common.info("Screensaver removed: " .. name)
            end
        elseif options.screensaver_dir then
            common.info(screensaver.getDirectory())
        elseif options.get_config then
            local value = screensaver.getConfig(options.config_key, "text")
            if value ~= "" then
                io.stdout:write(value, "\n")
            end
        elseif options.update_config then
            common.info(screensaver.updateConfig(json.decode(options.config_changes), "json"))
        elseif options.get_config_file then
            common.info(screensaver.getConfigFile())
        elseif options.status then
            common.info(screensaver.status())
        elseif options.state then
            common.info(json.encode(screensaver.getState()))
        else
            for _, action in ipairs({ "start", "stop", "restart", "reload", "hide", "show" }) do
                if options[action] then
                    screensaver[action]()
                    return
                end
            end
            screensaver.show()
        end
    end

    return M
end
