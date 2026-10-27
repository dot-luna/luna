-- Shared Tableshape schemas for Luna configs. Apps define their own fields;
-- object checks preserve the distinction between JSON objects, arrays, and null.
return function(root)
    local types = dofile(root .. "/lib/vendor/tableshape/init.lua").types
    local config = dofile(root .. "/lib/config.lua")(dofile(root .. "/lib/json.lua"))
    local M = { types = types }

    -- Allow unrelated fields so partial config edits preserve app extensions.
    -- Use :is_optional() on individual fields when defining a partial schema.
    function M.object(fields)
        return types.custom(config.isObject):describe("an object") * types.shape(fields, { open = true })
    end

    return M
end
