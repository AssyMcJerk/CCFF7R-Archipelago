-- CCFF7R Reunion - Cheat Engine Lua research snippets
-- Run pieces individually from Table > Show Cheat Table Lua Script (Ctrl+Alt+L).
-- OUT = folder where dumps are written.

local OUT  = [[C:\CCFF7R_dumps\]]
local base = getAddress('"CCFF7R-Win64-Shipping.exe"')

local function dump(addr, size, name)
  local b = readBytes(addr, size, true)
  local f = io.open(OUT .. name, 'wb')
  for i = 1, #b do f:write(string.char(b[i])) end
  f:close()
end

---------------------------------------------------------------- 1. GiveItem test
-- GiveItem(u16 itemId, int count) -> returns amount actually changed
-- Runs on a side thread: fine for testing, not for the real client.
local function giveItem(id, count)
  return executeCodeEx(0, 5000, base + 0x13957E0, id, count)
end
-- print(giveItem(0x2005, 1))   -- 1 Remedy

---------------------------------------------------------------- 2. Script native table
-- Writes index / handler / raw entry bytes. Names are at entry+0x18 (char* into exe).
local function dumpNatives()
  local tbl  = readQword(base + 0x71B8230)
  local b, e = readQword(tbl + 0x10), readQword(tbl + 0x18)
  local n = (e - b) // 8
  local f = io.open(OUT .. 'natives.txt', 'w')
  for i = 0, n - 1 do
    local ent = readQword(b + i * 8)
    if ent and ent ~= 0 then
      local fn   = readQword(ent + 0x20) or 0
      local name = readString(readQword(ent + 0x18) or 0, 128) or '?'
      f:write(string.format('%03X\texe+%X\t%s\n', i, fn - base, name))
    end
  end
  f:close()
end
-- dumpNatives()

---------------------------------------------------------------- 3. Treasure table + game state
local function dumpState()
  dump(readQword(base + 0x71AAD28), 0x1FE0, 'treasure_table.bin')
  dump(base + 0x71B3F00, 0x2000, 'gamestate.bin')
end
-- dumpState()

---------------------------------------------------------------- 4. VM context at last scripted GiveItem
-- Needs giveitem_hook.cea active.
local function dumpVM()
  local ctx, ip = readQword('gi_ctx'), readQword('gi_ip')
  local tag = string.format('%04X', readSmallInteger('gi_lastId'))
  dump(ctx, 0x400, 'vm_ctx_' .. tag .. '.bin')
  dump(ip - 0x400, 0x800, 'vm_ip_' .. tag .. '.bin')
end
-- dumpVM()

---------------------------------------------------------------- 5. Live check readers
local function treasureOpened(idx)
  local byte = readBytes(base + 0x71B4230 + (idx >> 3), 1)
  return (byte >> (idx & 7)) & 1 == 1
end
local function missionCleared(m)          -- 0..299
  return readBytes(base + 0x71B4332 + m * 3, 1) ~= 0
end
local function mailCount() return readSmallInteger(base + 0x71B4B9E) end
local function gil() return readInteger(base + 0x71B3F00 + 0xB0) end
