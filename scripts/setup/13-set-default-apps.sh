#!/usr/bin/env bash
# Apply default/apps.lua after app setup; extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
setup_dir=$(dirname -- "$script_path")
source "$setup_dir/../../lib/common.sh"

config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
if [[ "$config_home" != /* ]]; then
    luna_error 'XDG_CONFIG_HOME must be an absolute path.'
    exit 1
fi
export XDG_CONFIG_HOME="$config_home"

# Validate the whole declarative manifest before touching user preferences. JSON
# carries only data to Python; manifest output is never evaluated as shell code.
preferences_json=$(/usr/bin/lua -E - "$setup_dir/../../default/apps.lua" "$setup_dir/../../lib/json.lua" <<'LUA'
local ok, result = pcall(function()
    local manifest = assert(loadfile(arg[1], "t", {}))()
    assert(type(manifest) == "table", "Expected a key-value table")
    for key, value in pairs(manifest) do
        assert(type(key) == "string"
            and (key == "terminal" or key == "image/*" or key == "audio/*" or key == "video/*"
                or key:match("^[%w!#$&^_.+%-]+/[%w!#$&^_.+%-]+$")),
            "Keys must be terminal, a MIME type, image/*, audio/* or video/*")
        assert(type(value) == "string" and value:match("^[%w_][%w_.+%-]*%.desktop$"),
            "Values must be desktop entry IDs ending in .desktop")
    end
    return dofile(arg[2]).encode(manifest)
end)
if not ok then
    io.stderr:write("Invalid default app manifest: " .. tostring(result) .. "\n")
    os.exit(1)
end
io.write(result, "\n")
LUA
)

/usr/bin/python3 "$setup_dir/app-defaults.py" "$config_home" <<< "$preferences_json"
