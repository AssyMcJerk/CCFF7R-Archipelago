-- CCFF7R jump logger (Cheat Engine Lua). Needs mapjump_gate_test.cea (v2) ENABLED; mj_on can stay 0.
-- Appends every scene-change request to dumps\jump_log.txt with the story state at that moment:
--   time  id  flag  caller  story_count  chapter_byte  current_scene(71B4B64)  active_mission(71B4B9C)
-- Leave it running while you play; stop with: jumpLogTimer.destroy()
local OUT  = [[C:\CCFF7R_dumps\jump_log.txt]]
local base = getAddress('"CCFF7R-Win64-Shipping.exe"')
local seen = readInteger('mj_n') or 0
if jumpLogTimer then jumpLogTimer.destroy() end
local f = io.open(OUT, 'a'); f:write(os.date('%c') .. ' ---- jump logger start\n'); f:close()
jumpLogTimer = createTimer(nil)
jumpLogTimer.Interval = 100
jumpLogTimer.OnTimer = function()
  local n = readInteger('mj_n')
  if not n or n == seen then return end
  if n - seen > 64 then seen = n - 64 end
  local h = getAddress('mj_hist')
  local story, chap = readInteger(base + 0x71B4EF8), readBytes(base + 0x71B4BA4, 1)
  local cur, mis = readInteger(base + 0x71B4B64), readSmallInteger(base + 0x71B4B9C)
  local f = io.open(OUT, 'a')
  for i = seen, n - 1 do
    local e = h + (i % 64) * 16
    f:write(string.format('%s\tid=%d\tflag=%d\tcaller=exe+%X\tstory=%d\tchap=%d\tcur=%d\tmission=%d\n',
      os.date('%H:%M:%S'), readInteger(e), readInteger(e + 4) & 0xFF, readQword(e + 8) - base,
      story, chap, cur, mis))
  end
  f:close()
  seen = n
end
print('jump logger running -> ' .. OUT)
