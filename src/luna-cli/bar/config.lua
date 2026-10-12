-- Validate user bar preferences before restarting the running shell.
return function(common, root)
    local json = dofile(root .. "/lib/theme/json.lua")
    local directory = (os.getenv("XDG_CONFIG_HOME") or assert(os.getenv("HOME")) .. "/.config") .. "/luna"
    local path = directory .. "/bar.json"
    local M = {}

    local function read(file_path)
        local file = assert(io.open(file_path, "r"))
        local content = assert(file:read("*a"))
        assert(file:close())
        return json.decode(content)
    end

    local function fields(value, allowed, name)
        assert(type(value) == "table", name .. " must be an object")
        for key in pairs(value) do
            assert(allowed[key], "Unknown " .. name .. " field: " .. tostring(key))
        end
    end

    function M.snapshot()
        local file, failure, code = io.open(path, "r")
        if file then
            file:close()
        else
            assert(code == 2, failure)
            common.run({ "mkdir", "-p", "--", directory })
            common.run({ "cp", "-n", "--", root .. "/src/luna-bar/config.json", path })
        end
        local config = read(path)
        local defaults = read(root .. "/src/luna-bar/config.json")
        fields(config, { workspaces = true }, "bar")
        local workspaces = config.workspaces or {}
        fields(workspaces, { active = true, inactive = true, overrides = true }, "workspaces")
        local result = { workspaces = {} }
        local function indicator_config(value, fallback, name)
            fields(value, { type = true, size = true, label = true, path = true, icon = true }, name)
            local kind = value.type or fallback.type
            assert(kind == "number" or kind == "dot" or kind == "label" or kind == "icon",
                "Indicator type must be number, dot, label, or icon")
            local size = value.size or (kind == "dot" and 5 or kind == "icon" and 14 or 12)
            assert(type(size) == "number" and size >= 1 and size <= 24 and size % 1 == 0,
                "Indicator size must be an integer from 1 to 24")
            local indicator = { type = kind, size = size }
            if kind == "label" then
                assert(type(value.label) == "string" and value.label ~= "" and not value.label:find("[%c]"),
                    "Label indicators need a nonempty label")
                indicator.label = value.label
            elseif kind == "icon" then
                assert((value.path ~= nil) ~= (value.icon ~= nil), "Choose either icon or path for an SVG indicator")
                local source
                if value.icon then
                    assert(type(value.icon) == "string" and value.icon:match("^[a-z0-9-]+$"), "Invalid bundled icon name")
                    source = root .. "/src/qml/Luna/icons/" .. value.icon .. ".svg"
                else
                    assert(type(value.path) == "string" and value.path:lower():match("%.svg$") and not value.path:find("[%c]"),
                        "Icon indicators need a local SVG path")
                    source = value.path
                    if source:sub(1, 2) == "~/" then
                        source = assert(os.getenv("HOME")) .. source:sub(2)
                    elseif source:sub(1, 1) ~= "/" then
                        source = directory .. "/" .. source
                    end
                end
                local absolute, exists = common.capture({ "realpath", "-e", "--", source }, true)
                assert(exists, "Cannot find workspace SVG: " .. source)
                source = absolute:gsub("\n$", "")
                local svg = assert(io.open(source, "r"), "Cannot read workspace SVG: " .. source)
                svg:close()
                indicator.source = "file://" .. source:gsub("([^%w/_.~-])", function(character)
                    return string.format("%%%02X", character:byte())
                end)
            end
            assert(value.label == nil or kind == "label", "label is only valid for label indicators")
            assert(value.path == nil or kind == "icon", "path is only valid for icon indicators")
            assert(value.icon == nil or kind == "icon", "icon is only valid for icon indicators")
            return indicator
        end
        for _, state in ipairs({ "active", "inactive" }) do
            result.workspaces[state] = indicator_config(workspaces[state] or {}, defaults.workspaces[state], state)
        end
        local overrides = workspaces.overrides or {}
        assert(type(overrides) == "table", "Workspace overrides must be an object")
        result.workspaces.overrides = {}
        for key, value in pairs(overrides) do
            assert(type(key) == "string" and key:match("^[0-9]$"), "Workspace override keys use 1–9 and 0")
            result.workspaces.overrides[key] = indicator_config(value, defaults.workspaces.active, "workspace " .. key)
        end
        return json.encode(result)
    end

    return M
end
