-- Dump the shop_logger.cea ring buffer to dumps\shop_log_<time>.txt.
-- For every shop purchase/sale (return address exe+12B9222) it also hex-dumps 0x100 bytes
-- at each caller register that points to readable memory, so we can find the shop / stock tables.
local base = getAddress("CCFF7R-Win64-Shipping.exe")
local SHOP_RET = base + 0x12B9222
local buf = getAddress("sl_buf")
local n = readInteger(buf)
local regs = {"rbx","rbp","rsi","rdi","r12","r13","r14","r15"}
local out = {}
local function hexdump(addr, len)
  local b = readBytes(addr, len, true)
  if not b then return "    (unreadable)" end
  local lines = {}
  for i = 0, len - 1, 16 do
    local row = {}
    for j = 1, 16 do row[#row+1] = string.format("%02X", b[i + j] or 0) end
    lines[#lines+1] = string.format("    +%03X  %s", i, table.concat(row, " "))
  end
  return table.concat(lines, "\n")
end
out[#out+1] = string.format("module base %X, %d GiveItem calls logged", base, n)
for i = math.max(0, n - 512), n - 1 do
  local e = buf + 0x20 + (i % 512) * 0x60
  local id = readInteger(e) & 0xFFFF
  local cnt = readInteger(e + 4)
  if cnt > 0x7FFFFFFF then cnt = cnt - 0x100000000 end
  local ret = readQword(e + 8)
  local src = (ret == SHOP_RET) and "SHOP" or string.format("exe+%X", ret - base)
  out[#out+1] = string.format("#%d  item=0x%04X  count=%d  from=%s", i, id, cnt, src)
  if ret == SHOP_RET then
    for k, r in ipairs(regs) do
      local v = readQword(e + 0x10 + (k - 1) * 8)
      out[#out+1] = string.format("  %s = %X", r, v)
      if v > 0x10000 and v < 0x7FFFFFFFFFFF then out[#out+1] = hexdump(v, 0x100) end
    end
  end
end
local text = table.concat(out, "\n")
print(text)
local path = os.getenv("USERPROFILE") .. "\\Documents\\CCFF7R AP\\dumps\\shop_log_" .. os.date("%H%M%S") .. ".txt"
local f = io.open(path, "w")
if f then f:write(text .. "\n"); f:close(); print("saved " .. path) end
