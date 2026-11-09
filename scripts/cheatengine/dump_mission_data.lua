-- Dump mission data reachable from the mission UI widgets (addresses from story_log F7)
local OUT = [[C:\CCFF7R_dumps\]]
local function dump(addr, size, name)
  local b = readBytes(addr, size, true)
  if not b then print('read failed ' .. name); return end
  local f = io.open(OUT .. name, 'wb')
  for i = 1, #b do f:write(string.char(b[i])) end
  f:close()
  print(string.format('%s  <- %X (%d bytes)', name, addr, #b))
end
local tc  = 0x1BD5D648C80   -- WB_ui_Mission_Treasure_Count_C (live)
local mis = 0x1BD4B144180   -- WB_ui_Mission_C (live)
dump(tc,  0x320, 'w_treasurecount.bin')
dump(mis, 0x520, 'w_mission.bin')
local p1 = readQword(tc + 0x2F8)
local p2 = readQword(mis + 0x2E8)
print(string.format('tc+2F8 = %X   mission+2E8 = %X', p1 or 0, p2 or 0))
if p1 and p1 ~= 0 then dump(p1, 0x8000, 'mission_data_tc.bin') end
if p2 and p2 ~= 0 and p2 ~= p1 then dump(p2, 0x8000, 'mission_data_m.bin') end
