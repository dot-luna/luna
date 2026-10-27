-- Read and update the wallpaper TOML used by both the CLI and Quickshell.
-- TOMLKit preserves comments and unrelated options; only wallpaper.source is changed.
return function(common, module_dir)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config_home = os.getenv("XDG_CONFIG_HOME")
    if not config_home or config_home == "" then
        config_home = home .. "/.config"
    end
    M.path = os.getenv("LUNA_WALLPAPER_CONFIG")
    if not M.path or M.path == "" then
        M.path = config_home .. "/luna/wallpaper.toml"
    end
    local legacy = config_home .. "/luna/wallpaper"

    -- Use the installed parser in a short-lived process. Arguments remain data, even
    -- when a config path or media filename contains spaces, quotes, or shell syntax.
    local script = [=[
import os, pathlib, stat, sys, tempfile
try:
    import tomlkit
    operation, filename, legacy_filename, repository = sys.argv[1:5]
    path = pathlib.Path(filename)
    if not path.is_absolute():
        raise ValueError("config path must be absolute")

    # Follow user symlinks before replacing their target, keeping the link itself.
    target = path.resolve()
    exists = target.exists()
    # Existing documents are the renderer's responsibility during start/restart;
    # malformed TOML must still reach its logged dark fallback instead of blocking launch.
    if operation == "migrate" and exists:
        sys.exit(0)
    if exists and not target.is_file():
        raise ValueError("config is not a regular file")
    document = tomlkit.parse(target.read_text(encoding="utf-8")) if exists else tomlkit.document()
    wallpaper = document.get("wallpaper", {})
    source = wallpaper.get("source", "") if isinstance(wallpaper, dict) else ""
    if not isinstance(source, str) or not source.startswith("/") or any(ord(c) < 32 for c in source):
        source = ""

    # Once TOML exists, even an empty source is authoritative over the old selection.
    if not exists and pathlib.Path(legacy_filename).is_file():
        source = pathlib.Path(legacy_filename).read_text(encoding="utf-8").splitlines()[0:1]
        source = source[0] if source else ""
    if operation == "read":
        print(source)
        sys.exit(0)
    if operation == "migrate" and not source:
        sys.exit(0)

    # Never turn a checked-in reference/default into mutable user state.
    if target.is_relative_to(pathlib.Path(repository).resolve()):
        raise ValueError("use a user config outside the Luna checkout")
    if operation == "write":
        source = sys.argv[5]
    if not isinstance(wallpaper, dict) or "wallpaper" not in document:
        document["wallpaper"] = tomlkit.table()
    document["wallpaper"]["source"] = source

    # Stage beside the destination so replacement is atomic and failed writes leave
    # the previous document intact. Preserve its permissions and remove failed staging.
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".wallpaper-", delete=False) as handle:
            temporary = pathlib.Path(handle.name)
            handle.write(tomlkit.dumps(document))
            handle.flush()
            os.fsync(handle.fileno())
        if exists:
            temporary.chmod(stat.S_IMODE(target.stat().st_mode))
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
except Exception as error:
    print("Wallpaper config: " + str(error), file=sys.stderr)
    sys.exit(1)
]=]

    -- Keep parser failures visible instead of silently falling back to old state.
    local function execute(operation, source)
        local arguments = { "/usr/bin/python3", "-I", "-c", script,
            operation, M.path, legacy, module_dir .. "/../../.." }
        if source then
            table.insert(arguments, source)
        end
        local output, ok = common.capture(arguments)
        assert(ok, "Could not " .. operation .. " wallpaper config: " .. M.path)
        return output:gsub("\n$", "")
    end

    function M.current()
        local source = execute("read")
        return source ~= "" and source or nil
    end

    function M.write(source)
        execute("write", source)
    end

    -- Standalone starts can upgrade the old selection; installation normally seeds TOML.
    function M.migrate()
        execute("migrate")
    end

    return M
end
