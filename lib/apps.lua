-- Small builder context: read templates, replace named values, and write staged files.
return function(root, source, output, destination, config_dir)
    local common = dofile(root .. "/lib/common.lua")
    common.setup_logging()
    local ctx = {
        root = root, source = source, output = output,
        destination = destination, config_dir = config_dir,
        quote = common.quote, warn = common.warn,
    }

    local function relative(path)
        assert(type(path) == "string" and path ~= "" and path:sub(1, 1) ~= "/"
            and not path:find("[%z%c]"), "Expected a relative app path")
        for part in path:gmatch("[^/]+") do
            assert(part ~= ".." and part ~= ".", "App paths cannot escape their directory")
        end
        return path
    end

    function ctx.read(path)
        local file = assert(io.open(source .. "/" .. relative(path), "rb"))
        local content = assert(file:read("*a"))
        assert(file:close())
        return content
    end

    function ctx.write(path, content)
        local target = output .. "/" .. relative(path)
        assert(os.execute(common.command({ "mkdir", "-p", "--", target:match("^(.*)/") })),
            "Cannot create builder output directory")
        local file = assert(io.open(target, "wb"))
        assert(file:write(content))
        assert(file:close())
    end

    -- Values are literal replacements, never Lua or shell expressions. A missing
    -- name fails the build before any installed configuration is replaced.
    function ctx.render(template, target, values)
        local content = ctx.read(template):gsub("{{%s*([%w_.]+)%s*}}", function(name)
            local value = values
            for part in name:gmatch("[^.]+") do
                value = type(value) == "table" and value[part] or nil
            end
            assert(type(value) == "string" or type(value) == "number",
                "Missing template value: " .. name)
            return tostring(value)
        end)
        ctx.write(target, content)
    end

    local theme
    function ctx.theme()
        theme = theme or dofile(root .. "/lib/theme/resolved.lua")(root).active()
        return theme
    end

    return ctx
end
