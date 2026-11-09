-- Chest/scene logger for PopTracker map pins. Pairs with the UE4SS mod CCPosLogger (pos_log.txt).
-- Polls the treasure opened-bits and the current scene every 100 ms and appends to
-- Documents\CCFF7R AP\dumps\chest_log.txt:
--     HH:MM:SS  CHEST <treasure id>  scene=<id>
--     HH:MM:SS  SCENE <id>
-- Read-only: no hooks, no writes to the game. Run it, play, then stop with chestLogStop().
local base = getAddress("CCFF7R-Win64-Shipping.exe")
local BITS = base + 0x71B4230          -- treasure_bits (see game/addresses.py)
local SCENE = BITS + 0x934             -- current_scene
local NBYTES = 0xFC                    -- +0xFC holds the AP rollback canary, skip it

local path = os.getenv("USERPROFILE") .. "\\Documents\\CCFF7R AP\\dumps\\chest_log.txt"
local f = assert(io.open(path, "a"))
local function w(s) f:write(os.date("%H:%M:%S"), "\t", s, "\n"); f:flush(); print(s) end
w("SESSION start")

local prev = readBytes(BITS, NBYTES, true)
local lastScene = readInteger(SCENE)
w("SCENE " .. tostring(lastScene))

if chestLogTimer then chestLogTimer.destroy() end
chestLogTimer = createTimer(nil, false)
chestLogTimer.Interval = 100
chestLogTimer.OnTimer = function()
  local sc = readInteger(SCENE)
  if sc and sc ~= lastScene then lastScene = sc; w("SCENE " .. sc) end
  local cur = readBytes(BITS, NBYTES, true)
  if not cur or not prev then prev = cur; return end
  for i = 1, NBYTES do
    local new = cur[i] & ~prev[i]
    if new ~= 0 then
      for b = 0, 7 do
        if new & (1 << b) ~= 0 then w(string.format("CHEST %d\tscene=%d", (i - 1) * 8 + b, sc or -1)) end
      end
    end
  end
  prev = cur
end
chestLogTimer.Enabled = true

function chestLogStop() chestLogTimer.destroy(); chestLogTimer = nil; w("SESSION stop"); f:close() end
print("chest_pos_logger running -> " .. path .. "   (chestLogStop() to end)")
