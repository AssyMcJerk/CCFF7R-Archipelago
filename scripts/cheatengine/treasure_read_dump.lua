-- Dump the treasure_read_logger.cea ring buffer (oldest -> newest) to the Lua output window
-- and to treasure_read_log.txt in the CCFF7R AP folder.
local names = {[0x24A]="AddItem",[0x24C]="AddGil",[0x24E]="AddSP",[0x250]="TreasureIsEnable",
  [0x251]="TreasureEnable",[0x252]="TreasureGetType",[0x253]="TreasureGetAmount",
  [0x254]="TreasureGetId",[0x29F]="MultipleMes",[0x2A1]="AddMultipleMes"}
local buf = getAddress("tr_buf")
local n = readInteger(buf)
local first = math.max(0, n - 4096)
local out = {}
for i = first, n - 1 do
  local e = buf + 0x20 + (i % 4096) * 0x20
  local id = readInteger(e)
  local a1 = readQword(e + 8) or 0
  local a2 = readQword(e + 0x10) or 0
  out[#out+1] = string.format("%5d  %03X %-18s a1=%d (0x%X)  a2=%d (0x%X)",
    i, id, names[id] or "?", a1 & 0xFFFFFFFF, a1, a2 & 0xFFFFFFFF, a2)
end
local text = table.concat(out, "\n")
print(string.format("%d calls logged", n))
print(text)
local f = io.open(os.getenv("USERPROFILE") .. "\\Documents\\CCFF7R AP\\dumps\\treasure_read_log_" .. os.date("%H%M%S") .. ".txt", "w")
if f then f:write(text .. "\n"); f:close(); print("saved to dumps (treasure_read_log_<time>.txt)") end
