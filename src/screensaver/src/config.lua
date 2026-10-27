-- Screensaver defaults and schema. TOMLKit owns comment-preserving persistence;
-- reads always resolve the current file, independent of controller state.
return function(common, root)
    local json = dofile(root .. "/lib/json.lua")
    local config = dofile(root .. "/lib/config.lua")(json)
    local toml = dofile(root .. "/lib/toml.lua")(common, json)
    local validation = dofile(root .. "/lib/validation.lua")(root)
    local types = validation.types
    local M = {}
    local defaults
    local seconds = types.integer * types.range(0, 86400)
    local schema = validation.object({
        idle = validation.object({
            screensaver_seconds = seconds,
            lock_seconds = seconds,
            display_off_seconds = seconds,
        }),
        renderer = validation.object({
            shell = (types.literal("") + types.pattern("^/[^%z\1-\31]*%.qml$")
                + types.pattern("^~/[^%z\1-\31]*%.qml$"))
                :describe("an absolute or ~/ QML file path, or an empty string for the bundled shell"),
        }),
        settings = validation.object({}),
    })

    function M.file()
        return config.path("luna/screensaver.toml", "LUNA_SCREENSAVER_CONFIG")
    end

    function M.resolve(document)
        defaults = defaults or toml.read(root .. "/apps/luna-screensaver/config/screensaver.toml")
        local resolved = config.merge(defaults, document)
        local ok, message = schema:check_value(resolved)
        assert(ok, "Invalid screensaver config: " .. (message or ""))
        return resolved
    end

    function M.get(key, format)
        return config.format(config.get(M.resolve(toml.read(M.file())), key), format)
    end

    -- Validate both supplied values and TOMLKit's merged document before saving.
    -- Save only edits; callers explicitly reload when they want to apply them.
    function M.update(changes, format)
        assert(config.isObject(changes), "Config updates must be an object")
        M.resolve(changes)
        local document = toml.update(M.file(), changes, {
            protectedRoot = root,
            validate = { "/usr/bin/lua", "-E", root .. "/src/screensaver/src/read.lua", "--validate" },
        })
        return config.format(M.resolve(document), format)
    end

    return M
end
