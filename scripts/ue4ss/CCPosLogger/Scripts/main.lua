-- CCPosLogger v8 - logs Zack's world position for PopTracker map pins (UE4SS 3.0.x)
--
-- Output: Documents\CCFF7R AP\dumps\pos_log.txt
--     HH:MM:SS  x  y  z  yaw  <map texture>  <actor>          while moving (every >25 units, 4x/s)
--     HH:MM:SS  STOP  x  y  z  yaw  <map texture>  <actor>    after standing still for STOP_MS
-- Chests are logged by the AP client (treasure_log.txt); the two files are joined offline by time.
--
-- How Zack is found: field characters are FairGmChrActor (Zack and NPCs alike; there is no possessed pawn).
-- FindAllOf("FairGmChrActor") is cheap (exact class), so every tick we read all of them and pick the one that
-- has moved the most recently (NPCs mostly stand still). No object scans, no hotkeys (playing on controller):
-- standing still for ~1.5 s writes a STOP line, which serves as the mark.
--
-- v8: crash fix - never keep UObject references between ticks. A cached actor/widget that is destroyed on a
--     screen transition made UE4SS read freed memory (fatal error, 2026-10-19). Only object PATHS are kept;
--     every tick re-resolves them with StaticFindObject, which returns nil once the object is gone.
--     The level-name column (always LV_BootGame) is dropped to avoid GetOuter chains.
-- v7: pick Zack by camera-following (v6's 'moves most' grabbed enemies in battles); last column = level name.
-- v1-v5 history: PlayerController/Pawn/Character lookups all fail in this game; v4/v5 full scans hitched.

local OUT = (os.getenv("USERPROFILE") or "C:") .. "\\Documents\\CCFF7R AP\\dumps\\pos_log.txt"
local POLL_MS, MIN_MOVE, STOP_MS, MAP_REFIND_MS, LIST_MS = 250, 25.0, 1500, 3000, 2000

local f = io.open(OUT, "a")
local function write(line)
    if f then f:write(os.date("%H:%M:%S"), "\t", line, "\n"); f:flush() end
end
write("SESSION start v8")

local function valid(o) return o ~= nil and type(o) == "userdata" and o.IsValid ~= nil and o:IsValid() end
local function safe(fn, d) local ok, v = pcall(fn); if ok then return v end; return d end
local function nm(o) return safe(function() return o:GetFName():ToString() end, "?") end
local function nowMs() return os.clock() * 1000 end
-- "Class /Path/To.Object" -> "/Path/To.Object"
local function pathOf(o)
    local full = safe(function() return o:GetFullName() end, nil)
    if not full then return nil end
    return full:match("^%S+%s+(.+)$") or full
end
local function resolve(path)
    if not path then return nil end
    local o = safe(function() return StaticFindObject(path) end, nil)
    if valid(o) then return o end
    return nil
end

-- Zack = the FairGmChrActor that moves together with the camera (the camera follows him); NPCs and enemies
-- don't track the camera. Per actor: err = decayed |actor delta - camera delta| + distance-to-camera term.
local camPath, lastCamTry = nil, -1e9
local function camLoc()
    local cam = resolve(camPath)
    if not cam then
        camPath = nil
        if nowMs() - lastCamTry < 2000 then return nil end
        lastCamTry = nowMs()
        local o = safe(function() return FindFirstOf("PlayerCameraManager") end, nil)
        if not valid(o) then return nil end
        camPath = pathOf(o); cam = o
    end
    return safe(function() return cam:GetCameraLocation() end, nil)
end

local track = {}          -- name -> { x, y, z, err, a }
local current = nil
local prevCam = nil
local actorPaths, lastList, diagDone = nil, -1e9, false
local function pickZack()
    local fresh = nil
    if not actorPaths or nowMs() - lastList > LIST_MS then
        lastList = nowMs()
        fresh = safe(function() return FindAllOf("FairGmChrActor") end, nil) or {}
        actorPaths = {}
        for _, a in ipairs(fresh) do
            if valid(a) then local p = pathOf(a); if p then actorPaths[#actorPaths + 1] = p end end
        end
    end
    local actors = {}
    for _, p in ipairs(actorPaths) do
        local a = resolve(p)
        if a then actors[#actors + 1] = a end
    end
    if #actors == 0 and #actorPaths > 0 then
        -- paths did not resolve (path format?): use the list fetched this tick (safe within the same tick)
        if not diagDone then diagDone = true; write("DIAG\tStaticFindObject failed for " .. actorPaths[1]) end
        if fresh then for _, a in ipairs(fresh) do if valid(a) then actors[#actors + 1] = a end end end
    end
    if #actors == 0 then return nil end
    local c = camLoc()
    local cdx, cdy, cdz = 0, 0, 0
    if c and prevCam then cdx, cdy, cdz = c.X - prevCam.X, c.Y - prevCam.Y, c.Z - prevCam.Z end
    local camMoved = math.sqrt(cdx * cdx + cdy * cdy + cdz * cdz)
    if camMoved > 3000 then camMoved, cdx, cdy, cdz = 0, 0, 0, 0 end     -- cut/teleport
    if c then prevCam = { X = c.X, Y = c.Y, Z = c.Z } end

    local best, bestM, seen = nil, 1e18, {}
    for _, a in ipairs(actors) do
        if valid(a) then
            local n = nm(a)
            local l = safe(function() return a:K2_GetActorLocation() end, nil)
            if l and (math.abs(l.X) + math.abs(l.Y)) > 1 then
                seen[n] = true
                local t = track[n]
                if not t then t = { err = 300 }; track[n] = t
                elseif camMoved > 5 then
                    local ex, ey, ez = (l.X - t.x) - cdx, (l.Y - t.y) - cdy, (l.Z - t.z) - cdz
                    t.err = t.err * 0.85 + math.sqrt(ex * ex + ey * ey + ez * ez)
                end
                t.x, t.y, t.z, t.yaw = l.X, l.Y, l.Z, safe(function() return a:K2_GetActorRotation().Yaw end, 0)
                local dcam = c and math.sqrt((l.X - c.X) ^ 2 + (l.Y - c.Y) ^ 2 + (l.Z - c.Z) ^ 2) or 0
                t.dcam = dcam
                local m = t.err + dcam * 0.3
                if dcam < 2500 and m < bestM then best, bestM = n, m end
            end
        end
    end
    for n in pairs(track) do if not seen[n] then track[n] = nil end end
    -- hysteresis: keep the current actor unless it vanished, left the camera, or another fits much better
    local cur = current and track[current]
    if cur and cur.dcam and cur.dcam < 2500 and best ~= current and bestM > (cur.err + cur.dcam * 0.3) * 0.5 then
        best = current
    end
    if best ~= current then
        if best then
            local t = track[best]
            write(string.format("ZACK\t%s\terr=%.0f\tdcam=%.0f\tactors=%d", best, t.err, t.dcam or -1, #actors))
        end
        current = best
    end
    return best and track[best] or nil
end


local mapPath, lastMapTry, lastTex = nil, -1e9, "-"
local function mapTexture()
    local mapW = resolve(mapPath)
    if not mapW then
        mapPath = nil
        if nowMs() - lastMapTry < MAP_REFIND_MS then return lastTex end
        lastMapTry = nowMs()
        local o = safe(function() return FindFirstOf("WB_ui_Map_C") end, nil)
        if not valid(o) then return lastTex end
        mapPath = pathOf(o); mapW = o
    end
    return safe(function()
        local r = mapW.Map.Brush.ResourceObject
        if valid(r) then lastTex = nm(r) end
        return lastTex
    end, lastTex)
end

local last, stillSince, stopWritten = {}, nil, false
local function sample()
    local z = pickZack()
    if not z then return end
    local x, y, zz = z.x, z.y, z.z
    local yaw = z.yaw or 0
    local map = mapTexture()
    local moved = last.x == nil or ((x - last.x) ^ 2 + (y - last.y) ^ 2 + (zz - last.z) ^ 2) > MIN_MOVE * MIN_MOVE
    if moved or map ~= last.map then
        write(string.format("%.1f\t%.1f\t%.1f\t%.0f\t%s\t%s", x, y, zz, yaw, map, current or "?"))
        last.x, last.y, last.z, last.map = x, y, zz, map
        stillSince, stopWritten = nowMs(), false
    elseif not stopWritten and stillSince and nowMs() - stillSince >= STOP_MS then
        write(string.format("STOP\t%.1f\t%.1f\t%.1f\t%.0f\t%s\t%s", x, y, zz, yaw, map, current or "?"))
        stopWritten = true
    end
end

local lastErr = -1e9
LoopAsync(POLL_MS, function()
    ExecuteInGameThread(function()
        local ok, err = pcall(sample)
        if not ok and nowMs() - lastErr > 10000 then lastErr = nowMs(); write("ERR\t" .. tostring(err)) end
    end)
    return false
end)

print("[CCPosLogger] v8 logging to " .. OUT .. "\n")
