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
        parser:command("awake", "Temporarily pause automatic screensaver and locking.")
            :argument("awake_action"):args("?"):default("status")
            :choices({ "status", "toggle", "on", "off" })
    end

    local function awake(action)
        local method = action == "status" and "awakeStatus" or "setAwake"
        local arguments = { "qs", "ipc", "-p", renderer, "call", "screensaver", method }
        if action ~= "status" then
            -- The idle shell owns the session state and applies toggles atomically.
            local _, running = shell.ipc("ping")
            if not running then
                -- Quickshell prints startup logs to stdout; keep this command's JSON clean.
                local startup, started = common.capture({ root .. "/bin/luna", "screensaver", "start" })
                startup = startup:match("^%s*(.-)%s*$")
                assert(started, "Could not start the idle monitor for Stay awake"
                    .. (startup ~= "" and ":\n" .. startup or ""))
            end
            table.insert(arguments, action)
        end

        local output, ok = common.capture(arguments, true)
        if not ok and action == "status" then
            local _, running = shell.ipc("ping")
            if not running then
                return { enabled = false }
            end
        end
        assert(ok, "Could not " .. (action == "status" and "read" or "update")
            .. " Stay awake; run luna screensaver reload to refresh the idle monitor")
        local valid, state = pcall(json.decode, output)
        assert(valid and type(state) == "table" and type(state.enabled) == "boolean",
            "Invalid Stay awake response from the idle monitor")
        return state
    end

    function M.run(options)
        if options.awake then
            common.info(json.encode(awake(options.awake_action or "status")))
        elseif options.idle then
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
