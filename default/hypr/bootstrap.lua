-- Load reusable defaults relative to the checkout supplied by the entry point.
return function(root)
    local validate = dofile(root .. "/lib/theme/validate.lua")()
    local theme = dofile(root .. "/default/hypr/theme.lua")(validate)
    theme.apply()
end
