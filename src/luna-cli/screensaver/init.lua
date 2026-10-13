-- Own a lightweight screensaver shell which also monitors compositor idle notifications.
return function(common, directory)
    local root = directory .. "/../../.."
    local renderer = directory .. "/../../screensaver"
    local json = dofile(root .. "/lib/theme/json.lua")
    local config = dofile(directory .. "/config.lua")(common, root)
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, renderer, "screensaver", "Luna Screensaver")
    local M = {}

    function M.register(parser)
        parser:command("screensaver", "Show or manage the Luna screensaver and idle monitor.")
            :argument("screensaver_action"):args("?"):default("open")
            :choices({ "open", "hide", "start", "stop", "reload" })
        local idle = parser:command("idle", "Configure automatic screensaver and locking.")
        idle:argument("idle_action"):args("?"):default("status"):choices({ "status", "set" })
        idle:argument("idle_setting"):args("?"):choices({ "screensaver", "lock" })
        idle:argument("seconds"):args("?")
    end

    function M.run(options)
        if options.idle then
            local values
            if options.idle_action == "set" then
                values = config.set(options.idle_setting, tonumber(options.seconds))
                shell.run("start", { LUNA_IDLE_CONFIG = json.encode(values) })
                local _, ok = common.capture({ "qs", "ipc", "-p", renderer, "call", "screensaver",
                    "configure", json.encode(values) }, true)
                assert(ok, "Idle settings saved, but the screensaver could not update")
            else
                values = config.read()
            end
            common.info(json.encode(values))
        elseif options.screensaver_action == "hide" then
            shell.ipc("hide")
        else
            shell.run(options.screensaver_action or "open", { LUNA_IDLE_CONFIG = json.encode(config.read()) })
        end
    end

    return M
end
