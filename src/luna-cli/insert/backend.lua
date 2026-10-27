-- Unicode data stays local; curl talks directly to GIPHY without exposing keys in argv.
return function(common, directory)
    local json = dofile(directory .. "/../../../lib/json.lua")
    local config_dir = (os.getenv("XDG_CONFIG_HOME") or os.getenv("HOME") .. "/.config") .. "/luna"
    local M = {}

    local function read(path)
        local file = io.open(path, "rb")
        if not file then
            return nil
        end
        local content = file:read("*a")
        file:close()
        return content
    end

    local function config()
        return json.decode(read(config_dir .. "/insert.json") or "{}")
    end

    local function emit(results, message, more, needs_key)
        common.info('{"results":' .. json.encode(results, true) .. ',"message":' .. json.encode(message or "")
            .. ',"hasMore":' .. tostring(more or false) .. ',"needsKey":' .. tostring(needs_key or false) .. '}')
    end

    local function private_file(content)
        local path, ok = common.capture({ "mktemp", (os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/luna-insert.XXXXXX" })
        assert(ok, "Cannot create temporary insert file")
        path = path:gsub("\n$", "")
        local file = assert(io.open(path, "wb"))
        assert(file:write(content))
        file:close()
        return path
    end

    function M.emoji()
        common.info(assert(read(directory .. "/data/emoji.json"), "Emoji data is missing"))
    end

    local function escape(value)
        return value:gsub("([^%w._~-])", function(c) return string.format("%%%02X", c:byte()) end)
    end

    local function giphy_url(value)
        assert(type(value) == "string", "Invalid GIPHY response")
        local host = value:match("^https://([^/]+)/")
        assert(host and (host == "giphy.com" or host:match("^[%w.-]+%.giphy%.com$")), "Invalid GIPHY URL")
        return value
    end

    function M.giphy(query, offset)
        local key = os.getenv("GIPHY_API_KEY") or ""
        if key:match("^%s*$") then
            key = read(config_dir .. "/giphy.key") or ""
        end
        key = key:match("^%s*(.-)%s*$")
        if key == "" then
            emit({}, "Set up GIPHY to search online GIFs.", false, true)
            return
        end
        assert((utf8.len(query) or 201) <= 50, "GIPHY searches can contain up to 50 characters")
        offset = tonumber(offset or 0)
        assert(offset and offset >= 0 and offset <= 499 and offset % 1 == 0, "Invalid result offset")
        local rating = config().gif_rating or "pg-13"
        assert(({ g = true, pg = true, ["pg-13"] = true, r = true })[rating], "Invalid GIF rating")
        local url = "https://api.giphy.com/v1/gifs/" .. (query == "" and "trending" or "search")
            .. "?api_key=" .. escape(key) .. "&limit=25&offset=" .. offset .. "&rating=" .. rating
            .. (query ~= "" and "&q=" .. escape(query) or "")
        local path = private_file('url = "' .. url .. '"\n')
        local output, ok = common.capture({ "curl", "--silent", "--fail", "--max-time", "12",
            "--max-filesize", "4194304", "--config", path }, true)
        os.remove(path)
        assert(ok, "GIPHY request failed. Check your key, connection, or rate limit.")
        local response, results = json.decode(output), {}
        for _, entry in ipairs(response.data or {}) do
            local images = entry.images
            table.insert(results, { name = entry.title ~= "" and entry.title or "GIF", source = "GIPHY", icon = "film",
                image = giphy_url((images.fixed_width_small_still or images.original_still).url),
                animation = giphy_url((images.downsized or images.original).url),
                download = giphy_url((images.original or images.downsized).url),
                creator = type(entry.username) == "string" and entry.username or "" })
        end
        emit(results, "", offset + #results < math.min(500, (response.pagination or {}).total_count or 0))
    end

    local function paste(data, target, mime, history_data)
        assert(target and target:match("^0x%x+$"), "No application was focused when Luna opened")
        local path = private_file(data)
        local ok = os.execute(common.command({ "wl-copy", "--type", mime }) .. " < " .. common.quote(path) .. " >/dev/null 2>&1")
        if ok then
            local history_path = history_data and private_file(history_data) or path
            os.execute(common.command({ "cliphist", "store" }) .. " < " .. common.quote(history_path) .. " >/dev/null 2>&1")
            if history_data then os.remove(history_path) end
        end
        os.remove(path)
        assert(ok, "Could not restore clipboard")
        common.run({ "sleep", "0.18" })
        local output, focused = common.capture({ "hyprctl", "-j", "activewindow" })
        assert(focused, "Could not check focused application")
        local window = json.decode(output)
        assert(window.address == target, "Copied, but focus changed. Paste manually in the intended app.")
        local terminals = { kitty = true, alacritty = true, foot = true, footclient = true, konsole = true,
            ["org.wezfurlong.wezterm"] = true, ["com.mitchellh.ghostty"] = true, ["org.gnome.terminal"] = true }
        local command = { "wtype", "-M", "ctrl" }
        local terminal = terminals[(window.class or ""):lower()]
        if terminal then
            table.insert(command, "-M")
            table.insert(command, "shift")
        end
        table.insert(command, "-k")
        table.insert(command, "v")
        if terminal then
            table.insert(command, "-m")
            table.insert(command, "shift")
        end
        table.insert(command, "-m")
        table.insert(command, "ctrl")
        common.run(command)
    end

    function M.paste_emoji(value, target)
        local selected = value:sub(1, 1) == "[" and json.decode(value) or { value }
        assert(type(selected) == "table" and #selected > 0, "Choose an emoji")
        local known = {}
        for _, entry in ipairs(json.decode(assert(read(directory .. "/data/emoji.json"))).results) do
            known[entry.emoji] = true
        end
        for _, glyph in ipairs(selected) do
            assert(known[glyph], "Unknown emoji")
        end
        paste(table.concat(selected), target, "text/plain;charset=utf-8")
    end

    function M.paste_giphy(url, target)
        assert(target and target:match("^0x%x+$"), "No application was focused when Luna opened")
        -- Download only the chosen original; keep binary bytes out of shell arguments.
        local data, ok = common.capture({ "curl", "--silent", "--fail", "--max-time", "30",
            "--max-filesize", "26214400", "--proto", "=https", "--url", giphy_url(url) }, true)
        assert(ok, "Could not download GIF (maximum 25 MiB). Try again.")
        assert(#data <= 26214400 and (data:sub(1, 6) == "GIF87a" or data:sub(1, 6) == "GIF89a"),
            "GIPHY did not return a valid GIF")
        -- Browsers ignore a bare image/gif offer but accept a file via text/uri-list.
        -- Keep the actual file for the login session: receivers read it after wl-copy exits.
        local folder = assert(os.getenv("XDG_RUNTIME_DIR"), "No desktop runtime directory") .. "/luna-insert-gifs"
        common.run({ "mkdir", "-p", "-m", "700", "--", folder })
        local path, created = common.capture({ "mktemp", folder .. "/luna-XXXXXX.gif" })
        assert(created, "Could not prepare GIF attachment")
        path = path:gsub("\n$", "")
        local file = assert(io.open(path, "wb"))
        assert(file:write(data))
        file:close()
        local uri = "file://" .. path:gsub("([^%w/._~-])", function(c) return string.format("%%%02X", c:byte()) end)
        paste(uri .. "\r\n", target, "text/uri-list", data)
    end

    return M
end
