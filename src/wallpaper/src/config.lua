-- Wallpaper defaults and schema; every operation reads the user file.
-- Shared config resolution and TOML persistence live in lib/.
return function(common, root)
    local M = {}
    local json = dofile(root .. "/lib/json.lua")
    local config = dofile(root .. "/lib/config.lua")(json)
    local toml = dofile(root .. "/lib/toml.lua")(common, json)
    local validation = dofile(root .. "/lib/validation.lua")(root)
    local types = validation.types

    -- Load the app's shared defaults lazily; importing the API reads no config files.
    local defaults
    local schema = validation.object({
        wallpaper = validation.object({
            source = (types.literal("") + types.pattern("^/[^%z\1-\31]*$"))
                :describe("an absolute path without control characters, or an empty string"),
            fit = types.one_of({ "fill", "fit", "stretch", "center", "tile" }),
            background_color = types.pattern("^#%x%x%x%x%x%x$"):describe("a #RRGGBB color"),
        }),
        playback = validation.object({
            pause_when_output_inactive = types.boolean,
        }),
        transition = validation.object({
            type = types.one_of({ "none", "fade" }),
            duration_ms = types.integer * types.range(0, 2147483647),
        }),
    })

    function M.file()
        return config.path("luna/wallpaper.toml", "LUNA_WALLPAPER_CONFIG")
    end

    -- Shared by reads and TOMLKit's prewrite validator; the input is never modified.
    function M.resolve(document)
        defaults = defaults or toml.read(root .. "/apps/luna-wallpaper/config/wallpaper.toml")
        local resolved = config.merge(defaults, document)
        local ok, message = schema:check_value(resolved)
        assert(ok, "Invalid wallpaper config: " .. (message or ""))
        return resolved
    end

    function M.get(key, format)
        local document = M.resolve(toml.read(M.file()))
        return config.format(config.get(document, key), format)
    end

    -- Edit the user file whether the renderer is running or stopped. Save only
    -- supplied edits, never defaults; applying changes requires an explicit reload.
    function M.update(changes, format)
        assert(config.isObject(changes), "Config updates must be an object")

        -- Reject invalid supplied values, then validate TOMLKit's actual merged
        -- result before saving. Empty/null patches follow the editor's semantics.
        M.resolve(changes)
        local document = toml.update(M.file(), changes, {
            protectedRoot = root,
            validate = { "/usr/bin/lua", "-E", root .. "/src/wallpaper/src/read.lua", "--validate" },
        })
        return config.format(M.resolve(document), format)
    end

    return M
end
