-- Dump the shop stock table (found from the shop widget's list builder exe+12B8EA0):
--   container at exe+71AADB8: u32 category, ptr base (+8), ptr data (+0x10), u32 count (+0x18)
--   record = 36 bytes: u32 header + 16 x u16 item ids (0-terminated)
-- Writes dumps\shops.txt and dumps\shops.bin.
local b = getAddress("CCFF7R-Win64-Shipping.exe")
local hdr = b + 0x71AADB8
local cat, data, count = readInteger(hdr), readQword(hdr + 0x10), readInteger(hdr + 0x18)
local out = {string.format("category=%d data=%X count=%d", cat, data, count)}
local raw = readBytes(data, count * 36, true) or {}
for s = 0, count - 1 do
  local r = data + s * 36
  local items = {}
  for k = 0, 15 do
    local id = readSmallInteger(r + 4 + k * 2) & 0xFFFF
    if id ~= 0 then items[#items + 1] = string.format("%04X", id) end
  end
  out[#out + 1] = string.format("shop %2d (id %04X)  header=%08X  %s", s, (cat << 12) | s, readInteger(r), table.concat(items, " "))
end
local dir = os.getenv("USERPROFILE") .. "\\Documents\\CCFF7R AP\\dumps\\"
local f = io.open(dir .. "shops.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close()
local g = io.open(dir .. "shops.bin", "wb")
local parts = {}
for i = 1, #raw, 4096 do parts[#parts + 1] = string.char(table.unpack(raw, i, math.min(i + 4095, #raw))) end
g:write(table.concat(parts)); g:close()
print(table.concat(out, "\n"))
