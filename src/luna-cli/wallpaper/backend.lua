-- Own only Luna's wallpaper Quickshell instance and persist successful selections.
return function(common, renderer, config)
    local M = {}
    M.current = config.current

    -- Address the wallpaper entry point explicitly so other Quickshell apps stay untouched.
    local function ipc(method, path)
        local arguments = { "qs", "ipc", "-p", renderer, "call", "wallpaper", method }
        if path then
            table.insert(arguments, path)
        end
        return common.capture(arguments, true)
    end

    local function check_session()
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY") and os.getenv("WAYLAND_DISPLAY") ~= "",
            "Wallpaper rendering requires a Wayland session")
    end

    local function launch()
        check_session()
        common.run({ "qs", "-p", renderer, "--daemonize", "--no-duplicate" })
    end

    function M.start()
        check_session()
        config.migrate()
        launch()
    end

    -- The old entry point was moved, so `qs kill -p` cannot resolve its missing file.
    -- Match live instances by their recorded exact path, then stop those IDs only.
    function M.restart()
        check_session()
        config.migrate()
        common.run({ "/usr/bin/python3", "-I", "-c", [=[
import json, pathlib, subprocess, sys, time
current = pathlib.Path(sys.argv[1]).resolve()
paths = {current, current.parent.parent / "shell.qml"}

def wallpaper_instances():
    result = subprocess.run(["qs", "list", "-a", "-j"], capture_output=True, text=True, check=True, timeout=5)
    # Quickshell prints no JSON when there are no live instances.
    return [item for item in json.loads(result.stdout or "[]")
            if pathlib.Path(item["config_path"]).resolve() in paths]

try:
    for item in wallpaper_instances():
        subprocess.run(["qs", "kill", "-i", item["id"]], check=True, timeout=5)
    # Wait for shutdown before --no-duplicate could reuse the retiring instance.
    for attempt in range(30):
        if not wallpaper_instances():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Wallpaper renderer did not stop")
except Exception as error:
    print("Wallpaper restart: " + str(error), file=sys.stderr)
    sys.exit(1)
]=], renderer })
        launch()
    end

    function M.apply(path)
        -- Read before changing the running source, so parse errors cannot lose saved state.
        local previous = config.current() or ""
        launch()

        -- Registration usually completes immediately; allow ten seconds on a cold start.
        local ready = false
        for _ = 1, 100 do
            local _, ok = ipc("set", path)
            if ok then
                ready = true
                break
            end
            common.run({ "sleep", "0.1" })
        end
        assert(ready, "Wallpaper renderer did not become available")

        -- Config parsing, probing, and decoding each have bounded startup deadlines.
        -- Allow sixty seconds overall; save only after the current source is ready.
        for _ = 1, 600 do
            local status, ok = ipc("status")
            if ok and status:match("^%s*ready%s*$") then
                local saved, message = pcall(config.write, path)
                if not saved then
                    ipc("set", previous)
                    error(message, 0)
                end
                common.info("Wallpaper set: " .. path)
                return
            end
            if ok and status:match("^%s*error%s*$") then
                break
            end
            common.run({ "sleep", "0.1" })
        end

        ipc("set", previous)
        error("Quickshell could not load the wallpaper; previous selection preserved")
    end

    return M
end
