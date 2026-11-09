-- CCStoryLogger v4 - Crisis Core Reunion research logger for UE4SS 3.0.x
-- v2: no per-tick object-array scans (fixes choppiness). Objects are looked up once,
--     cached, and only re-found if they become invalid (at most every 10 s).
--     Broken world/level lookup removed.
--
-- Output: UE4SS console + Mods/CCStoryLogger/story_log.txt
-- Keys:   F6 = write a "MARK" line + snapshot

local MOD_DIR  = "Mods/CCStoryLogger/"
local LOG_PATH = MOD_DIR .. "story_log.txt"
local POLL_MS  = 1000          -- widget/event-skip polling interval
local REFIND_MS = 10000        -- minimum time between re-lookups of a missing object

---------------------------------------------------------------- logging
local logFile = io.open(LOG_PATH, "a")
local function log(fmt, ...)
    local ok, msg = pcall(string.format, fmt, ...)
    if not ok then msg = tostring(fmt) end
    local line = string.format("[%s] %s", os.date("%H:%M:%S"), msg)
    print("[CCStoryLogger] " .. line .. "\n")
    if logFile then logFile:write(line, "\n"); logFile:flush() end
end
log("==================== session start (v4) ====================")

---------------------------------------------------------------- helpers
local function valid(o) return o ~= nil and o.IsValid ~= nil and o:IsValid() end
local function safe(fn, default)
    local ok, v = pcall(fn)
    if ok then return v end
    return default
end
local function shortName(o) return safe(function() return o:GetFName():ToString() end, "?") end

-- cached lookup: FindFirstOf only when the cached object is gone, rate-limited
local cache, lastTry = {}, {}
local function nowMs() return os.clock() * 1000 end
local function cached(className)
    local o = cache[className]
    if valid(o) then return o end
    local t = nowMs()
    if lastTry[className] and (t - lastTry[className]) < REFIND_MS then return nil end
    lastTry[className] = t
    o = nil
    pcall(function() o = FindFirstOf(className) end)
    if valid(o) then cache[className] = o; return o end
    cache[className] = nil
    return nil
end

---------------------------------------------------------------- state
local function getEventSkip()
    local m = cached("FairEventSkipManager")
    if not m then return "n/a" end
    return string.format("now=%s term=%s skip=%s",
        tostring(safe(function() return m.m_nowEventIndex end, "?")),
        tostring(safe(function() return m.m_terminateIndex end, "?")),
        tostring(safe(function() return m.m_isEventSkip end, "?")))
end

local WATCH_WIDGETS = {
    { cls = "WB_ui_Loading_Chapter_C",        label = "CHAPTER CARD" },
    { cls = "WB_ui_Notice_Mail_C",            label = "MAIL NOTICE" },
    { cls = "WB_ui_Result_C",                 label = "BATTLE RESULT" },
    { cls = "WB_ui_Mission_Treasure_Count_C", label = "MISSION TREASURE" },
    { cls = "WB_ui_Startend_Mes_C",           label = "START/END MSG" },
    { cls = "WB_ui_GameOver_C",               label = "GAME OVER" },
    { cls = "WB_ui_Saving_C",                 label = "SAVING" },
    { cls = "WB_ui_Mission_C",                label = "MISSION MENU" },
}
local function widgetShown(w)
    local inVp = safe(function() return w:IsInViewport() end, nil)
    local vis  = safe(function() return w:IsVisible() end, nil)
    if inVp == nil and vis == nil then return false end
    return (inVp ~= false) and (vis ~= false)
end

---------------------------------------------------------------- polling
local last = { skip = nil, widgets = {} }

local function snapshot(reason)
    log("---- SNAPSHOT (%s) ----", reason)
    log("  evtSkip : %s", getEventSkip())
end

local function poll()
    local skip = getEventSkip()
    if skip ~= last.skip then log("EVTSKIP %s", skip); last.skip = skip end

    for _, ww in ipairs(WATCH_WIDGETS) do
        local w = cached(ww.cls)
        local shown = w and widgetShown(w) or false
        if shown ~= (last.widgets[ww.cls] or false) then
            log("UI      %s %s", ww.label, shown and "SHOWN" or "hidden")
            last.widgets[ww.cls] = shown
        end
    end
end

LoopAsync(POLL_MS, function()
    ExecuteInGameThread(function()
        local ok, err = pcall(poll)
        if not ok then log("poll error: %s", tostring(err)) end
    end)
    return false
end)

---------------------------------------------------------------- cutscenes
-- v3: NotifyOnNewObject removed (UE4SS StaticConstructObject hook raced the async loader -> crash)
for _, path in ipairs({
    "/Script/Fair.FairLevelSequenceManager:EndLevelSequence",
}) do
    if not pcall(function()
        RegisterHook(path, function() log("SEQEND") end)
    end) then log("hook unavailable: %s", path) end
end

---------------------------------------------------------------- hotkeys
RegisterKeyBind(Key.F6, function()
    ExecuteInGameThread(function()
        log("################ MARK ################")
        snapshot("F6")
    end)
end)

-- F7: log raw addresses of mission UI widgets (for Cheat Engine follow-up)
RegisterKeyBind(Key.F7, function()
    ExecuteInGameThread(function()
        log("---- widget addresses (F7) ----")
        for _, cls in ipairs({ "WB_ui_Mission_C", "WB_ui_Mission_Mission_List_C",
                               "WB_ui_Mission_Category_List_C", "WB_ui_Mission_Treasure_Count_C" }) do
            local objs = nil
            pcall(function() objs = FindAllOf(cls) end)
            if objs then
                for i, o in ipairs(objs) do
                    if valid(o) then
                        log("  %s #%d  addr=%X  %s", cls, i, o:GetAddress(), o:GetFullName())
                    end
                end
            else
                log("  %s: none", cls)
            end
        end
    end)
end)

log("loaded v4. F6 = mark+snapshot, F7 = mission widget addresses")
