-- Divide numbered workspaces into contiguous ranges in physical monitor order.
-- Reconcile after layout events settle so hotplug sees final positions and outputs.
local rules = {}
local previous = ""
local first = {}

local function settle_outputs(monitors)
    local pending = {}
    for _, monitor in ipairs(monitors) do
        local current = monitor.active_workspace
        -- Startup can create 11 before the old single-monitor bindings are replaced.
        -- Preserve intentional extra workspaces and any visible special workspace.
        if first[monitor.name] and not monitor.active_special_workspace and current
            and current.id > 10 and current.name == tostring(current.id)
            and current.is_empty and not current.is_persistent then
            table.insert(pending, first[monitor.name])
        end
    end
    if #pending == 0 then
        return
    end

    local focused_monitor = hl.get_active_monitor()
    local focused_window = hl.get_active_window()
    local cursor = hl.get_cursor_pos()

    -- Normal workspace switching creates missing targets and lets Quickshell see
    -- the temporary workspace disappear through its usual lifecycle events.
    for _, workspace in ipairs(pending) do
        hl.dispatch(hl.dsp.focus({ workspace = workspace }))
    end

    local active_window = hl.get_active_window()
    local active_monitor = hl.get_active_monitor()
    if focused_window and focused_window.mapped then
        if not active_window or active_window.address ~= focused_window.address then
            hl.dispatch(hl.dsp.focus({ window = focused_window }))
        end
    elseif focused_monitor and (not active_monitor or active_monitor.name ~= focused_monitor.name) then
        hl.dispatch(hl.dsp.focus({ monitor = focused_monitor }))
    end

    local position = hl.get_cursor_pos()
    if cursor and position and (cursor.x ~= position.x or cursor.y ~= position.y) then
        hl.dispatch(hl.dsp.cursor.move({ x = cursor.x, y = cursor.y }))
    end
end

local function apply()
    local monitors = {}
    for _, monitor in ipairs(hl.get_monitors()) do
        if not monitor.is_mirror then
            table.insert(monitors, monitor)
        end
    end
    table.sort(monitors, function(a, b)
        if a.x ~= b.x then
            return a.x < b.x
        end
        if a.y ~= b.y then
            return a.y < b.y
        end
        return a.name < b.name
    end)
    if #monitors == 0 then
        return
    end

    local names = {}
    for _, monitor in ipairs(monitors) do
        table.insert(names, monitor.name)
    end
    local signature = table.concat(names, "\n")
    if signature == previous then
        -- A rapid disconnect/reconnect can end with the same monitor arrangement.
        settle_outputs(monitors)
        return
    end
    previous = signature

    -- Disable old assignments before installing replacements. Reuse rule handles
    -- when returning to a prior arrangement instead of accumulating duplicate rules.
    for _, rule in pairs(rules) do
        rule:set_enabled(false)
    end
    local targets = {}
    first = {}
    local workspace = 1
    for index, monitor in ipairs(monitors) do
        local count = math.floor(10 / #monitors) + (index <= 10 % #monitors and 1 or 0)
        if count > 0 then
            first[monitor.name] = workspace
        end
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

    settle_outputs(monitors)
end

local pending = false
local function schedule()
    -- Config verification has no outputs or running event loop for a timer.
    if pending or #hl.get_monitors() == 0 then
        return
    end
    pending = true
    hl.timer(function()
        pending = false
        apply()
    end, { timeout = 250, type = "oneshot" })
end

for _, event in ipairs({ "hyprland.start", "config.reloaded", "monitor.added", "monitor.removed", "monitor.layout_changed" }) do
    hl.on(event, schedule)
end
