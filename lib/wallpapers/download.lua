-- Luna's wallpaper downloads stage HTTP images outside the media library.
-- Filenames come from URLs, never headers; this helper never starts a renderer.
return function(common)
    local M = {}
    local formats = {
        ["image/png"] = "png", ["image/jpeg"] = "jpg", ["image/webp"] = "webp",
        ["image/bmp"] = "bmp", ["image/x-ms-bmp"] = "bmp", ["image/svg+xml"] = "svg",
    }

    function M.is_url(value)
        return value:lower():match("^https?://") ~= nil
    end

    function M.prepare()
        if common.available("curl") then
            return
        end

        assert(common.available("pacman"), "curl is missing and pacman is unavailable; install curl first")
        common.info("Installing curl for wallpaper downloads.")
        local arguments = { "pacman", "-Syu", "--needed", "curl" }
        if not common.is_root() then
            assert(common.available("sudo"), "Installing curl requires sudo")
            table.insert(arguments, 1, "sudo")
        end
        common.run(arguments)
        assert(common.available("curl"), "curl is still unavailable after installation")
    end

    function M.fetch(url, directory, index)
        local payload = directory .. "/payload-" .. index
        common.run({ "curl", "--disable", "--fail", "--location", "--silent", "--show-error",
            "--globoff", "--proto", "=http,https", "--proto-redir", "=http,https",
            "--connect-timeout", "15", "--max-time", "120", "--output", payload, "--url", url })

        -- Infer the format from the bytes so extensionless image endpoints also work.
        local mime, ok = common.capture({ "file", "--brief", "--mime-type", "--", payload })
        local extension = formats[mime:gsub("%s+$", "")]
        assert(ok and extension, "URL did not return a supported image")
        local path = url:match("^[^:]+://[^/]+(/[^?#]*)") or ""
        local name = path:match("([^/]+)$") or "wallpaper-" .. index
        name = name:gsub("%%(%x%x)", function(hex)
            return string.char(tonumber(hex, 16))
        end):gsub("[%c/\\]", "_")
        local stem = name:match("^(.*)%.%w+$") or name
        if stem == "" or stem == "." or stem == ".." then
            stem = "wallpaper-" .. index
        end

        -- Separate staging folders preserve duplicate-name detection across a batch.
        local folder = directory .. "/" .. index
        common.run({ "mkdir", "--", folder })
        local destination = folder .. "/" .. stem .. "." .. extension
        assert(os.rename(payload, destination))
        return destination
    end

    return M
end
