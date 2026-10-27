-- Shared TOML file operations for Luna apps. Keep parsing/comment-preserving writes
-- in the installed TOMLKit process; pure Lua config helpers live in lib/config.lua.
return function(common, json)
    local M = {}
    local script = [=[
import json, os, pathlib, stat, subprocess, sys, tempfile
try:
    import tomlkit
    operation, filename, protected_root, changes, validator = sys.argv[1:]
    path = pathlib.Path(filename)
    if not path.is_absolute():
        raise ValueError("config path must be absolute")
    target = path.resolve()
    exists = target.exists()
    if exists and not target.is_file():
        raise ValueError("config is not a regular file")
    document = tomlkit.parse(target.read_text(encoding="utf-8")) if exists else tomlkit.document()

    # TOML-only values remain in the file but cross the Lua JSON boundary as null.
    def encode(document):
        encoded = json.dumps(document.unwrap(), default=lambda _: None)
        return json.dumps(json.loads(encoded, parse_constant=lambda _: None))

    # Merge tables recursively; arrays/scalars replace whole values. Null has no
    # TOML representation, so it leaves the current setting unchanged.
    def merge(table, patch):
        changed = False
        for key, value in patch.items():
            if value is None:
                continue
            if isinstance(value, dict):
                existing = table.get(key)
                if isinstance(existing, dict):
                    changed = merge(existing, value) or changed
                else:
                    # An empty/null-only patch must not create a new table.
                    nested = tomlkit.table()
                    if not merge(nested, value):
                        continue
                    table[key] = nested
                    changed = True
            else:
                previous = table.get(key)
                if hasattr(previous, "unwrap"):
                    previous = previous.unwrap()
                # Preserve bool/int differences inside nested arrays as well.
                if (key not in table or previous != value
                        or json.dumps(previous, default=str, sort_keys=True)
                        != json.dumps(value, sort_keys=True)):
                    table[key] = value
                    changed = True
        return changed

    if operation == "update":
        patch = json.loads(changes)
        if not isinstance(patch, dict):
            raise ValueError("config updates must be an object")
        changed = merge(document, patch)
        # Apps may validate the actual merged document before any file operation.
        # Pass JSON on stdin; a failed validator leaves even the original bytes intact.
        validator = json.loads(validator)
        if validator:
            result = subprocess.run(validator, input=encode(document), text=True,
                                    capture_output=True, timeout=10)
            if result.returncode:
                raise ValueError(result.stderr.strip() or "config validation failed")
        if changed:
            if protected_root and target.is_relative_to(pathlib.Path(protected_root).resolve()):
                raise ValueError("use a user config outside the Luna checkout")

            # Atomic replacement follows user symlinks without replacing the link.
            # Preserve modes and remove staging files even after a failed write.
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                                 prefix=".luna-toml-", delete=False) as handle:
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

    print(encode(document))
except Exception as error:
    print("TOML config: " + str(error), file=sys.stderr)
    sys.exit(1)
]=]

    local function execute(operation, path, changes, options)
        options = options or {}
        local output, ok = common.capture({ "/usr/bin/python3", "-I", "-c", script,
            operation, path, options.protectedRoot or "",
            json.encode(changes or {}), json.encode(options.validate or json.array({})) })
        assert(ok, "Could not " .. operation .. " TOML config: " .. path)
        return json.decode(output)
    end

    -- Missing files read as an empty document without creating files.
    function M.read(path, options)
        return execute("read", path, nil, options)
    end

    function M.update(path, changes, options)
        return execute("update", path, changes, options)
    end

    return M
end
