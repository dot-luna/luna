-- Divide numbered workspaces into contiguous ranges in physical monitor order.
-- Reconcile after layout events settle so hotplug sees final positions and outputs.
local rules = {}
local previous = ""

local function apply()
    local monitors = {}
    for _, monitor in ipairs(hl.get_monitors()) do
        if not monitor.is_mirror then table.insert(monitors, monitor) end
    end
    table.sort(monitors, function(a, b)
        if a.x ~= b.x then return a.x < b.x end
        if a.y ~= b.y then return a.y < b.y end
        return a.name < b.name
    end)
    if #monitors == 0 then return end

    local names = {}
    for _, monitor in ipairs(monitors) do table.insert(names, monitor.name) end
    local signature = table.concat(names, "\n")
    if signature == previous then return end
    previous = signature

    -- Disable old assignments before installing replacements. Reuse rule handles
    -- when returning to a prior arrangement instead of accumulating duplicate rules.
    for _, rule in pairs(rules) do rule:set_enabled(false) end
    local targets = {}
    local workspace = 1
    for index, monitor in ipairs(monitors) do
        local count = math.floor(10 / #monitors) + (index <= 10 % #monitors and 1 or 0)
        for offset = 1, count do
            local key = workspace .. ":" .. monitor.name
            if rules[key] then
                rules[key]:set_enabled(true)
            else
                rules[key] = hl.workspace_rule({ workspace = tostring(workspace), monitor = monitor.name })
            end
            targets[workspace] = monitor.name
            workspace = workspace + 1
        end
    end

    -- Rules route future workspace creation; move existing workspaces as well.
    for _, current in ipairs(hl.get_workspaces()) do
        local target = targets[current.id]
        if target and current.monitor and current.monitor.name ~= target then
            hl.dispatch(hl.dsp.workspace.move({ workspace = current.id, monitor = target }))
        end
    end
end

local pending = false
local function schedule()
    -- Config verification has no outputs or running event loop for a timer.
    if pending or #hl.get_monitors() == 0 then return end
    pending = true
    hl.timer(function()
        pending = false
        apply()
    end, { timeout = 250, type = "oneshot" })
end

for _, event in ipairs({ "hyprland.start", "config.reloaded", "monitor.added", "monitor.removed", "monitor.layout_changed" }) do
    hl.on(event, schedule)
end
