-- Dump the loaded CCFF7R-Win64-Shipping.exe image (as mapped in memory) to dumps\module_image.bin.
-- Used for offline disassembly (e.g. the BtlSetFinishGameOver native at exe+13158A0) without a debugger.
-- Reads in 1 MB chunks; unreadable pages are written as zeros.
local name = "CCFF7R-Win64-Shipping.exe"
local base = getAddress(name)
local pe = readInteger(base + 0x3C)
local size = readInteger(base + pe + 0x50)          -- OptionalHeader.SizeOfImage
local path = os.getenv("USERPROFILE") .. "\\Documents\\CCFF7R AP\\dumps\\module_image.bin"
local f = assert(io.open(path, "wb"))
local CH = 0x100000
local bad = 0
for off = 0, size - 1, CH do
  local n = math.min(CH, size - off)
  local b = readBytes(base + off, n, true)
  if b then
    local parts = {}
    for i = 1, #b, 4096 do
      parts[#parts + 1] = string.char(table.unpack(b, i, math.min(i + 4095, #b)))
    end
    f:write(table.concat(parts))
  else
    -- fall back page by page
    for p = 0, n - 1, 0x1000 do
      local pb = readBytes(base + off + p, math.min(0x1000, n - p), true)
      if pb then
        local parts = {}
        for i = 1, #pb, 4096 do parts[#parts + 1] = string.char(table.unpack(pb, i, math.min(i + 4095, #pb))) end
        f:write(table.concat(parts))
      else
        f:write(string.rep("\0", math.min(0x1000, n - p)))
        bad = bad + 1
      end
    end
  end
end
f:close()
print(string.format("dumped %X bytes from %X to %s (%d unreadable pages)", size, base, path, bad))
