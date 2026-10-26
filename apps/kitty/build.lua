-- Keep the theme mapping in a native Kitty template so each setting is editable.
return function(ctx)
    ctx.render("templates/theme.conf", "generated/theme.conf", ctx.theme())
end
